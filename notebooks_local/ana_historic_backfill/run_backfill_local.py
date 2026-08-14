"""Backfill historico ANA corriendo 100% local (sin consumir computo de Databricks).

Reemplaza la ejecucion en el job `ANA_Historic_Backfill` (removido de databricks.yml):
misma logica que tenia el notebook `Historic_ANA.ipynb` (mismo endpoint autenticado,
mismo batching de 5 estaciones, mismo criterio de corte por estacion), pero corriendo
como proceso local monitoreable, escribiendo JSON localmente y subiendolos al Volume de
Databricks en lotes via `databricks fs cp` (ver sync_to_databricks.py). Databricks queda
reservado solo para el job diario (`All_Estacoes_ANA_Daily`), que ya lee todo el folder
`json/` del Volume sin importar el origen del archivo.

Retoma desde `historic_backfill_state.json` si existe (bajado del Volume con
`databricks fs cat` antes de cancelar el run en Databricks, ver docs/decisions.md
Decision 016). Si no existe, hay que generarlo primero con `bootstrap_target_stations.py`.

Uso:
    python run_backfill_local.py                  # corre hasta agotar todas o llegar al piso
    python run_backfill_local.py --max-windows 20  # corta despues de N ventanas (resumible)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import lock

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
LOCAL_DIR = Path(__file__).parent
STATE_FILE = LOCAL_DIR / "historic_backfill_state.json"
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"
LOG_FILE = LOCAL_DIR / "logs" / "backfill.log"

logger = logging.getLogger("ana_backfill")

BASE_URL = "https://www.ana.gov.br/hidrowebservice"
LOGIN_ENDPOINT = "/EstacoesTelemetricas/OAUth/v1"
SERIE_TELEMETRICA_ENDPOINT = "/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v2"
DEFAULT_TIMEOUT = 60

FLOOR_DATE = date(2000, 1, 1)
WINDOW_DAYS = 30
STATION_BATCH_SIZE = 5  # igual que Daily_ANA.ipynb: "reducido de 10 a 5" tras saturar la API
REQUEST_DELAY_SECONDS = 0.5


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


class AnaApiError(RuntimeError):
    """Errores especificos del webservice de la ANA."""


def create_session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def log_api_ana(session: requests.Session) -> str:
    usuario = os.environ.get("USER_API_ANA")
    password = os.environ.get("PASS_API_ANA")
    if not usuario or not password:
        raise AnaApiError("Configura USER_API_ANA y PASS_API_ANA en el .env o el entorno")
    url = f"{BASE_URL}{LOGIN_ENDPOINT}"
    response = session.get(url, headers={"Identificador": usuario, "Senha": password}, timeout=DEFAULT_TIMEOUT)
    try:
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise AnaApiError(f"Error autenticando con ANA: {exc}") from exc
    try:
        token = payload["items"]["tokenautenticacao"]
    except (KeyError, TypeError) as exc:
        raise AnaApiError("La respuesta de login no contiene el token esperado") from exc
    if not isinstance(token, str) or not token:
        raise AnaApiError("Token de autenticacion vacio o invalido")
    return token


def consultar_serie_batch(
    session: requests.Session, token: str, codigos: list[str], data_busca: str, intervalo: str = "DIAS_30"
) -> Optional[list[dict]]:
    """None = 401 (token vencido), senal para reautenticar y reintentar en el loop principal."""
    url = f"{BASE_URL}{SERIE_TELEMETRICA_ENDPOINT}"
    params = {
        "Codigos_Estacoes": ",".join(str(c) for c in codigos),
        "Tipo Filtro Data": "DATA_LEITURA",
        "Range Intervalo de busca": intervalo,
        "Data de Busca (yyyy-MM-dd)": data_busca,
    }
    response = session.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=DEFAULT_TIMEOUT)
    if response.status_code == 401:
        return None
    try:
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise AnaApiError(f"Error consultando serie historica: {exc}") from exc
    items = payload.get("items")
    return items if isinstance(items, list) else []


def _chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _has_real_value(item: dict) -> bool:
    return any(item.get(k) not in (None, "", "null") for k in ("Cota_Adotada", "Chuva_Adotada", "Vazao_Adotada"))


def raw_filename(window_start: date, window_end: date) -> str:
    return f"ANA_HIST_{window_start.isoformat()}_{window_end.isoformat()}.json"


def load_state() -> dict:
    if not STATE_FILE.exists():
        raise AnaApiError(
            f"No existe {STATE_FILE}. Genera el estado inicial primero con bootstrap_target_stations.py "
            "o baja el historic_backfill_state.json desde el Volume de Databricks."
        )
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run(max_windows: int) -> None:
    state = load_state()
    active_stations: list[str] = state["active_stations"]
    window_end = date.fromisoformat(state["next_window_end"])
    exhausted_stations: dict[str, str] = state.get("exhausted_stations", {})

    logger.info(
        f"Estado inicial: {len(active_stations)} activas, {len(exhausted_stations)} agotadas, "
        f"retomando en ventana que termina {window_end}"
    )

    if not active_stations:
        logger.info("No hay estaciones activas: backfill completo para este lote de estaciones.")
        return

    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    session = create_session()
    token = log_api_ana(session)
    logger.info("Login OK")

    processed = 0
    t_start = time.time()

    while active_stations and window_end >= FLOOR_DATE and processed < max_windows:
        window_start = max(FLOOR_DATE, date.fromordinal(window_end.toordinal() - WINDOW_DAYS + 1))
        data_busca = window_end.isoformat()

        window_records: list[dict] = []
        codigos_con_datos: set[str] = set()

        for batch in _chunked(active_stations, STATION_BATCH_SIZE):
            items = consultar_serie_batch(session, token, batch, data_busca)
            if items is None:
                token = log_api_ana(session)
                items = consultar_serie_batch(session, token, batch, data_busca)
                if items is None:
                    raise AnaApiError("401 persistente tras reautenticar")
            for item in items:
                if _has_real_value(item):
                    window_records.append(item)
                    codigos_con_datos.add(str(item.get("codigoestacao")))
            time.sleep(REQUEST_DELAY_SECONDS)

        if window_records:
            filepath = OUTPUT_JSON_DIR / raw_filename(window_start, window_end)
            filepath.write_text(json.dumps(window_records, ensure_ascii=False, indent=2), encoding="utf-8")

        sin_datos = [c for c in active_stations if c not in codigos_con_datos]
        for codigo in sin_datos:
            exhausted_stations[codigo] = window_end.isoformat()
        active_stations = [c for c in active_stations if c in codigos_con_datos]

        elapsed = time.time() - t_start
        processed += 1
        logger.info(
            f"[{processed}/{max_windows}] ventana {window_start}..{window_end}: "
            f"{len(window_records)} registros, {len(codigos_con_datos)} con datos, "
            f"{len(sin_datos)} se agotaron, {len(active_stations)} activas "
            f"(elapsed={elapsed/60:.1f}min)"
        )

        window_end = date.fromordinal(window_start.toordinal() - 1)
        save_state(
            {
                "active_stations": active_stations,
                "next_window_end": window_end.isoformat(),
                "exhausted_stations": exhausted_stations,
            }
        )

    if not active_stations:
        logger.info("Todas las estaciones objetivo se agotaron: backfill completo.")
    elif window_end < FLOOR_DATE:
        logger.info(f"Se llego al piso {FLOOR_DATE} con {len(active_stations)} estaciones todavia activas.")
    else:
        logger.info(f"Limite de {max_windows} ventanas alcanzado, quedan {len(active_stations)} activas. Volver a correr para continuar.")


def run_with_lock(max_windows: int) -> None:
    """Envuelve run() con el lock de un solo proceso (ver lock.py) para que la tarea
    programada de Windows y el boton 'start' del dashboard Gradio nunca corran dos
    backfills en paralelo pisandose el estado."""
    if not lock.acquire("run_backfill_local"):
        info = lock.read_lock()
        logger.warning(f"Ya hay un backfill corriendo (pid={info.get('pid') if info else '?'}), no se inicia otro.")
        return
    try:
        run(max_windows)
    finally:
        lock.release()


def _configure_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


if __name__ == "__main__":
    _configure_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-windows", type=int, default=100_000, help="Corte por corrida (default: practicamente ilimitado)")
    args = parser.parse_args()
    try:
        run_with_lock(args.max_windows)
    except AnaApiError as exc:
        logger.error(str(exc))
        raise SystemExit(f"✗ {exc}")
