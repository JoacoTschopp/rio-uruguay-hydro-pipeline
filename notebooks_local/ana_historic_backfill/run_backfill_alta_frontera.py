"""Backfill historico dirigido a las 22 estaciones de `alta_frontera` (grupo A, historia
profunda de nivel), para traer `Chuva_Adotada` anterior a 2026-03-03 -- el hueco que la
Decision 023 documento como "0 dias de lluvia en 26 anios" y que la Decision 024 identifico
como artefacto del pipeline, no limitacion real de la fuente.

Motivo de existir como script separado en vez de reusar run_backfill_local.py tal cual: ese
script excluye deliberadamente estas 22 estaciones de su universo objetivo (Decision 015 --
"deja fuera intencionalmente las 22 estaciones ya profundas"), porque su historia de NIVEL ya
estaba cargada por otro mecanismo (Historic_Nivel_ANA.ipynb, que ademas hardcodea
Chuva_Adotada=None al leer el CSV historico -- ver notebooks/00_Landing/ANA_Hidrico/Historic_Nivel_ANA.ipynb
cell-2). Nunca se le pidio a la API en vivo la lluvia historica de estas estaciones puntuales.

Confirmado contra la API real antes de escribir este script (`probe_chuva_alta_frontera.py`,
2026-08-21): la ventana 2026-02-15 devuelve Chuva_Adotada real para 7/22 estaciones, 2024-06-15
para 8/22, 2020-06-15 para 7/22, 2015-06-15 para 7/22, 2010-06-15 solo para 74100000 (624
registros horarios), y 2005-06-15 devuelve 0 items para las 22 -- la fuente real se agota ahi,
no antes. Los timestamps historicos son horarios (`YYYY-MM-DD HH:00:00.0`), distintos de los
timestamps `YYYY-MM-DD 12:00:00` que uso la carga historica de nivel via CSV -- no hay colision
de claves en el MERGE de `ETL_Bronze_ANA.ipynb` (codigoestacao + Data_Hora_Medicao), asi que
este backfill inserta filas nuevas sin pisar ni duplicar el nivel ya cargado.

Misma mecanica que run_backfill_local.py (ventanas de 30 dias hacia atras, lotes de 5
estaciones, dropout por estacion sin readings reales en la ventana), pero con:
  - Universo fijo: las 22 estaciones de alta_frontera (no calculado contra Bronze).
  - Arranca en 2026-03-02 (el dia antes de que el job diario expandido empiece a cubrirlas).
  - Estado y output en archivos propios, para no pisar el backfill del grupo B (ya completo:
    0 activas, 361 agotadas, ver historic_backfill_state.json).

Uso:
    python run_backfill_alta_frontera.py                  # corre hasta agotar todas o piso 2000
    python run_backfill_alta_frontera.py --max-windows 20  # corta despues de N ventanas
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
STATE_FILE = LOCAL_DIR / "alta_frontera_backfill_state.json"
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"  # mismo folder que run_backfill_local.py: sync_to_databricks.py sube todo junto
LOG_FILE = LOCAL_DIR / "logs" / "backfill_alta_frontera.log"

logger = logging.getLogger("ana_backfill_alta_frontera")

BASE_URL = "https://www.ana.gov.br/hidrowebservice"
LOGIN_ENDPOINT = "/EstacoesTelemetricas/OAUth/v1"
SERIE_TELEMETRICA_ENDPOINT = "/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v2"
DEFAULT_TIMEOUT = 60

FLOOR_DATE = date(2000, 1, 1)
START_WINDOW_END = date(2026, 3, 2)  # el dia antes de que el job diario expandido las cubra
WINDOW_DAYS = 30
STATION_BATCH_SIZE = 5
REQUEST_DELAY_SECONDS = 0.5

# Las 22 estaciones de alta_frontera (weather.silver.estacion_subcuenca, consultado 2026-08-21;
# ver tambien probe_chuva_alta_frontera.py, que uso la misma lista).
STATIONS_ALTA_FRONTERA = [
    "70100000", "70200000", "70300000", "70500000", "71200000", "71250000", "71300000",
    "71350001", "72430000", "72630000", "72680000", "72715000", "72810000", "72849000",
    "73300000", "73350000", "73600000", "73765000", "73770000", "73900000", "73960000",
    "74100000",
]


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
    return f"ANA_HIST_AF_{window_start.isoformat()}_{window_end.isoformat()}.json"


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {
            "active_stations": list(STATIONS_ALTA_FRONTERA),
            "next_window_end": START_WINDOW_END.isoformat(),
            "exhausted_stations": {},
        }
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
        logger.info("No hay estaciones activas: backfill completo para alta_frontera.")
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
        logger.info("Todas las estaciones de alta_frontera se agotaron: backfill completo.")
    elif window_end < FLOOR_DATE:
        logger.info(f"Se llego al piso {FLOOR_DATE} con {len(active_stations)} estaciones todavia activas.")
    else:
        logger.info(f"Limite de {max_windows} ventanas alcanzado, quedan {len(active_stations)} activas. Volver a correr para continuar.")


def run_with_lock(max_windows: int) -> None:
    if not lock.acquire("run_backfill_alta_frontera"):
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
        raise SystemExit(f"ERROR: {exc}")
