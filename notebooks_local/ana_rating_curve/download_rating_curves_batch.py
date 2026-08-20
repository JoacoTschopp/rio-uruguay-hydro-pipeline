"""Barrido multi-estacion de curvas de aforo (curva-chave) y aforos reales, para TODAS
las estaciones ANA con medicion de nivel (no solo el target 74100000).

Fase 1 del plan docs/rating_curve_discharge_plan.md. Reutiliza request/normalizacion de
download_rating_curve.py y agrega lo que ese script no tiene: estado resumible,
reautenticacion ante 401, lock compartido con el backfill historico (nunca en paralelo,
misma cuenta/token de ANA), logging a archivo, y barrido de N estaciones en una corrida.

Ventanas de curva-chave calibradas en el Paso 0 (ver docs/rating_curve_discharge_plan.md
§2.1 y §3.3): el endpoint filtra por `Data_Ultima_Alteracao` (fecha de modificacion del
registro en el sistema de ANA), no por vigencia de la curva. Se usan 5 ventanas de 365
dias cubriendo desde el 1-ene de hace 4 anios hasta hoy (con margen de seguridad sobre el
piso observado de ~3.5 anios). Una estacion sin datos en esas 5 ventanas se considera
`sin_curva` (validado: 3/3 estaciones de control dieron `[]` tanto en estas ventanas como
en un barrido completo 1950-2026).

Los aforos (medicoes reais) se piden desde 2000-01-01 (Decision D4 del plan), en ventanas
de 365 dias (~27 por estacion) -- ese SI es un rango largo porque los aforos reales estan
espaciados en el tiempo real de la medicion, no filtrados por Data_Ultima_Alteracao.

Uso:
    # grupo A completo (22 estaciones), curvas + aforos
    python download_rating_curves_batch.py --group A

    # grupo B, solo curvas (aforos van en pasada aparte, no bloqueante)
    python download_rating_curves_batch.py --group B --skip-aforos --max-stations 100

    # reintentar solo lo que quedo pendiente o lo que fallo con error
    python download_rating_curves_batch.py --group B --skip-aforos --only-missing

    # regenerar el reporte de cobertura sin pegarle a la API
    python download_rating_curves_batch.py --report-only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

LOCAL_DIR = Path(__file__).parent
REPO_ROOT = LOCAL_DIR.resolve().parents[1]

sys.path.insert(0, str(LOCAL_DIR))
import download_rating_curve as drc  # noqa: E402  (create_session, log_api_ana, normalize_*, evaluate_curve_accuracy, AnaApiError, date_windows)

sys.path.insert(0, str(REPO_ROOT / "notebooks_local" / "ana_historic_backfill"))
import lock  # noqa: E402  (mismo backfill.lock: nunca corre en paralelo con run_backfill_local.py)

OUTPUT_DIR = LOCAL_DIR / "output"
RAW_JSON_DIR = OUTPUT_DIR / "raw_json"
SEGMENTS_CSV = OUTPUT_DIR / "segmentos_curva_ALL.csv"
AFOROS_CSV = OUTPUT_DIR / "aforos_ALL.csv"
COVERAGE_CSV = OUTPUT_DIR / "reporte_cobertura_curvas.csv"
STATE_FILE = LOCAL_DIR / "rating_curve_state.json"
ESTACIONES_NIVEL_FILE = LOCAL_DIR / "estaciones_nivel.json"
GRUPO_A_GEOJSON = REPO_ROOT / "SIG" / "estaciones_ana_nivel_historico.geojson"
LOG_FILE = LOCAL_DIR / "logs" / "rating_curve.log"

AFOROS_FLOOR = date(2000, 1, 1)
REQUEST_DELAY_SECONDS = 0.5
MAPE_SOSPECHOSA_THRESHOLD = 0.20

logger = logging.getLogger("ana_rating_curve_batch")


def curve_windows(today: date) -> list[tuple[date, date]]:
    """5 ventanas de 365 dias, (hoy.año-4)-01-01 -> hoy. Ver docstring del modulo."""
    start = date(today.year - 4, 1, 1)
    return drc.date_windows(start, today, max_days=365)


# ---------------------------------------------------------------------------
# Universo de estaciones y grupos (plan §3.2)
# ---------------------------------------------------------------------------

def load_universe() -> list[str]:
    if not ESTACIONES_NIVEL_FILE.exists():
        raise drc.AnaApiError(
            f"No existe {ESTACIONES_NIVEL_FILE}. Se genera con la query SQL de "
            "docs/rating_curve_discharge_plan.md §3.2 contra weather.bronze.ana_rio_uruguai."
        )
    return json.loads(ESTACIONES_NIVEL_FILE.read_text(encoding="utf-8"))


def load_grupo_a() -> list[str]:
    data = json.loads(GRUPO_A_GEOJSON.read_text(encoding="utf-8"))
    return [f["properties"]["codigoestacao"] for f in data["features"]]


def resolve_target_stations(args: argparse.Namespace) -> list[str]:
    if args.stations:
        return [s.strip() for s in args.stations.split(",") if s.strip()]
    universo = load_universe()
    grupo_a = set(load_grupo_a())
    if args.group == "A":
        return [c for c in universo if c in grupo_a]
    if args.group == "B":
        return [c for c in universo if c not in grupo_a]
    return universo


# ---------------------------------------------------------------------------
# Estado resumible
# ---------------------------------------------------------------------------

def _empty_state() -> dict:
    return {"pendientes": [], "hechas": [], "sin_curva": [], "con_error": {}, "aforos_hechas": []}


def load_state() -> dict:
    if not STATE_FILE.exists():
        return _empty_state()
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    for key, default in _empty_state().items():
        state.setdefault(key, default)
    return state


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_pendientes(state: dict, target: list[str], only_missing: bool) -> None:
    """Actualiza state['pendientes'] contra el universo objetivo de esta corrida.
    only_missing=True: agrega a pendientes los codigos de target que no esten ya en
    hechas/sin_curva/con_error (permite correr de nuevo tras ampliar el universo sin
    reprocesar lo ya resuelto). only_missing=False: reemplaza pendientes por target
    completo (fuerza reprocesar todo lo pedido, ignora resultados previos de la corrida)."""
    resueltas = set(state["hechas"]) | set(state["sin_curva"]) | set(state["con_error"].keys())
    if only_missing:
        ya_pendientes = set(state["pendientes"])
        nuevos = [c for c in target if c not in resueltas and c not in ya_pendientes]
        state["pendientes"].extend(nuevos)
    else:
        state["pendientes"] = list(target)


# ---------------------------------------------------------------------------
# Requests con reautenticacion (401) y reintentos ante errores transitorios
# (la API de ANA devuelve 417/502/503 de forma intermitente, ver Decision 016)
# ---------------------------------------------------------------------------

def auth_with_retries(session: requests.Session, attempts: int = 10) -> str:
    """attempts=10 con backoff hasta 60s: la API de ANA tiene caidas sostenidas de varios
    minutos (504 en cascada), no solo errores puntuales -- ver Decision 017."""
    last_exc: Optional[Exception] = None
    for i in range(attempts):
        try:
            return drc.log_api_ana(session)
        except (drc.AnaApiError, requests.RequestException) as exc:
            last_exc = exc
            wait = min(60, 3 * (i + 1))
            logger.warning(f"Login a ANA fallo (intento {i + 1}/{attempts}): {exc}. Reintentando en {wait}s...")
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def fetch_with_reauth(session: requests.Session, token_holder: dict, endpoint: str, params: dict) -> list[dict]:
    url = f"{drc.BASE_URL}{endpoint}"
    for attempt in range(4):
        headers = {"Authorization": f"Bearer {token_holder['token']}"}
        try:
            response = session.get(url, headers=headers, params=params, timeout=drc.DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            if attempt == 3:
                raise drc.AnaApiError(f"Error de red consultando {endpoint}: {exc}") from exc
            time.sleep(3 * (attempt + 1))
            continue
        if response.status_code == 401:
            logger.info("Token vencido (401), reautenticando...")
            token_holder["token"] = auth_with_retries(session)
            continue
        if response.status_code in (417, 429, 500, 502, 503, 504):
            if attempt == 3:
                response.raise_for_status()
            time.sleep(3 * (attempt + 1))
            continue
        try:
            response.raise_for_status()
            payload = response.json()
        except (ValueError, requests.RequestException) as exc:
            raise drc.AnaApiError(f"Error consultando {endpoint}: {exc}") from exc
        items = payload.get("items")
        return items if isinstance(items, list) else []
    raise drc.AnaApiError(f"Reintentos agotados consultando {endpoint}")


def fetch_curve_for_station(session: requests.Session, token_holder: dict, station: str, today: date) -> list[dict]:
    all_items: list[dict] = []
    for start, end in curve_windows(today):
        params = {
            "Código da Estação": station,
            "Data Inicial (yyyy-MM-dd)": start.isoformat(),
            "Data Final (yyyy-MM-dd)": end.isoformat(),
        }
        items = fetch_with_reauth(session, token_holder, drc.RATING_CURVE_ENDPOINT, params)
        all_items.extend(items)
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_items


def fetch_aforos_for_station(session: requests.Session, token_holder: dict, station: str, today: date) -> list[dict]:
    all_items: list[dict] = []
    for start, end in drc.date_windows(AFOROS_FLOOR, today):
        params = {
            "Código da Estação": station,
            "Tipo Filtro Data": "DATA_LEITURA",
            "Data Inicial (yyyy-MM-dd)": start.isoformat(),
            "Data Final (yyyy-MM-dd)": end.isoformat(),
        }
        items = fetch_with_reauth(session, token_holder, drc.DISCHARGE_MEASUREMENTS_ENDPOINT, params)
        all_items.extend(items)
        time.sleep(REQUEST_DELAY_SECONDS)
    return all_items


# ---------------------------------------------------------------------------
# Persistencia incremental (append a los consolidados, raw JSON por estacion)
# ---------------------------------------------------------------------------

def _append_csv(df: pd.DataFrame, path: Path) -> None:
    if df.empty:
        return
    df.to_csv(path, mode="a", header=not path.exists(), index=False)


def _write_raw(station: str, kind: str, items: list[dict]) -> None:
    RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_JSON_DIR / f"{kind}_{station}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run(target: list[str], only_missing: bool, max_stations: int, skip_aforos: bool) -> None:
    state = load_state()
    sync_pendientes(state, target, only_missing)

    if not state["pendientes"]:
        logger.info("No hay estaciones pendientes para este universo objetivo.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = drc.create_session()
    token_holder = {"token": auth_with_retries(session)}
    logger.info("Login OK")

    today = date.today()
    processed = 0
    t_start = time.time()

    while state["pendientes"] and processed < max_stations:
        station = state["pendientes"][0]
        try:
            curve_items = fetch_curve_for_station(session, token_holder, station, today)
            _write_raw(station, "curva", curve_items)
            segments = drc.normalize_rating_curve_segments(curve_items, station)

            if segments.empty:
                state["sin_curva"].append(station)
                logger.info(f"[{processed + 1}] {station}: sin curva (0 segmentos en {len(curve_windows(today))} ventanas)")
            else:
                _append_csv(segments.drop(columns=["raw"]), SEGMENTS_CSV)
                n_vigencias = segments["rating_curve_id"].nunique()
                state["hechas"].append(station)
                logger.info(f"[{processed + 1}] {station}: {len(segments)} segmentos, {n_vigencias} vigencias")

                if not skip_aforos and station not in state["aforos_hechas"]:
                    aforos_items = fetch_aforos_for_station(session, token_holder, station, today)
                    _write_raw(station, "aforos", aforos_items)
                    measurements = drc.normalize_discharge_measurements(aforos_items, station)
                    _append_csv(measurements, AFOROS_CSV)
                    state["aforos_hechas"].append(station)
                    if not measurements.empty:
                        acc = drc.evaluate_curve_accuracy(segments, measurements)
                        mape = acc["mape"]
                        flag = " <- SOSPECHOSA (MAPE>20%)" if mape is not None and mape > MAPE_SOSPECHOSA_THRESHOLD else ""
                        logger.info(f"    aforos: {len(measurements)}, MAPE={mape}{flag}")
                    else:
                        logger.info("    aforos: 0 desde 2000-01-01 (sin_validacion)")

            state["pendientes"].pop(0)
        except drc.AnaApiError as exc:
            state["con_error"][station] = str(exc)
            state["pendientes"].pop(0)
            logger.error(f"[{processed + 1}] {station}: ERROR - {exc}")

        processed += 1
        elapsed = time.time() - t_start
        if processed % 5 == 0 or not state["pendientes"]:
            logger.info(
                f"progreso: {processed} procesadas esta corrida, {len(state['pendientes'])} pendientes, "
                f"elapsed={elapsed / 60:.1f}min"
            )
        save_state(state)

    logger.info(
        f"Corrida terminada: {processed} procesadas. "
        f"hechas={len(state['hechas'])} sin_curva={len(state['sin_curva'])} "
        f"con_error={len(state['con_error'])} pendientes={len(state['pendientes'])}"
    )


def run_with_lock(target: list[str], only_missing: bool, max_stations: int, skip_aforos: bool) -> None:
    """Comparte backfill.lock con run_backfill_local.py (mismo lock.py importado desde
    ana_historic_backfill): nunca deben correr al mismo tiempo, comparten cuenta/token
    de la API de ANA (ver plan §3.3, paso 3-5)."""
    if not lock.acquire("download_rating_curves_batch"):
        info = lock.read_lock()
        logger.warning(
            f"Ya hay un proceso ANA corriendo (pid={info.get('pid') if info else '?'}, "
            f"label={info.get('label') if info else '?'}), no se inicia el barrido de curvas."
        )
        return
    try:
        run(target, only_missing, max_stations, skip_aforos)
    finally:
        lock.release()


# ---------------------------------------------------------------------------
# Reporte de cobertura (plan §3.3 paso 6)
# ---------------------------------------------------------------------------

def build_coverage_report() -> pd.DataFrame:
    state = load_state()
    rows = []

    segments_all = pd.read_csv(SEGMENTS_CSV) if SEGMENTS_CSV.exists() else pd.DataFrame()
    aforos_all = pd.read_csv(AFOROS_CSV) if AFOROS_CSV.exists() else pd.DataFrame()
    if not segments_all.empty:
        segments_all["valid_from_dt"] = pd.to_datetime(segments_all["valid_from"], errors="coerce")
        segments_all["valid_to_dt"] = pd.to_datetime(segments_all["valid_to"], errors="coerce")
    if not aforos_all.empty:
        aforos_all["measurement_datetime"] = pd.to_datetime(aforos_all["measurement_datetime"], errors="coerce")

    all_stations = sorted(set(state["hechas"]) | set(state["sin_curva"]) | set(state["con_error"].keys()))
    floor_ts = pd.Timestamp(AFOROS_FLOOR)

    for station in all_stations:
        if station in state["con_error"]:
            rows.append({"codigoestacao": station, "veredicto": "con_error", "detalle_error": state["con_error"][station]})
            continue
        if station in state["sin_curva"]:
            rows.append({"codigoestacao": station, "veredicto": "sin_curva"})
            continue

        seg = segments_all[segments_all["station_code"].astype(str) == str(station)] if not segments_all.empty else pd.DataFrame()
        afo = aforos_all[aforos_all["station_code"].astype(str) == str(station)] if not aforos_all.empty else pd.DataFrame()

        n_vigencias = seg["rating_curve_id"].nunique() if not seg.empty else 0
        vigencias = seg.drop_duplicates("rating_curve_id").sort_values("valid_from_dt") if not seg.empty else seg

        gaps_post_2000 = 0
        if len(vigencias) > 1:
            prev_end = None
            for _, v in vigencias.iterrows():
                if prev_end is not None and pd.notna(v["valid_from_dt"]) and pd.notna(prev_end):
                    gap_days = (v["valid_from_dt"] - prev_end).days
                    if gap_days > 1 and v["valid_from_dt"] >= floor_ts:
                        gaps_post_2000 += 1
                prev_end = v["valid_to_dt"] if pd.notna(v["valid_to_dt"]) else prev_end

        n_aforos = len(afo)
        mape = None
        if not seg.empty and not afo.empty:
            acc = drc.evaluate_curve_accuracy(seg, afo)
            mape = acc["mape"]

        if n_vigencias == 0:
            veredicto = "sin_curva"
        elif gaps_post_2000 > 0:
            veredicto = "usable_con_huecos"
        elif n_aforos == 0:
            veredicto = "usable_sin_validacion"
        elif mape is not None and mape > MAPE_SOSPECHOSA_THRESHOLD:
            veredicto = "sospechosa"
        else:
            veredicto = "usable"

        rows.append(
            {
                "codigoestacao": station,
                "n_vigencias": n_vigencias,
                "vigencia_min": seg["valid_from"].min() if not seg.empty else None,
                "vigencia_max": seg["valid_to"].max() if not seg.empty else None,
                "huecos_vigencia_post_2000": gaps_post_2000,
                "cota_min_cm": seg["stage_min_cm"].min() if not seg.empty else None,
                "cota_max_cm": seg["stage_max_cm"].max() if not seg.empty else None,
                "n_aforos_desde_2000": n_aforos,
                "aforo_datetime_min": afo["measurement_datetime"].min() if not afo.empty else None,
                "aforo_datetime_max": afo["measurement_datetime"].max() if not afo.empty else None,
                "mape_validacion": mape,
                "veredicto": veredicto,
            }
        )

    report = pd.DataFrame(rows)
    report.to_csv(COVERAGE_CSV, index=False)
    return report


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--group", choices=["A", "B"], help="Grupo de estaciones (A=historia profunda, B=resto). Ignorado si se pasa --stations.")
    parser.add_argument("--stations", help="Lista explicita de codigos separados por coma, sobreescribe --group")
    parser.add_argument("--max-stations", type=int, default=100_000, help="Corte por corrida (default: practicamente ilimitado)")
    parser.add_argument("--only-missing", action="store_true", help="Solo agrega a pendientes lo que no este ya resuelto, sin reprocesar")
    parser.add_argument("--skip-aforos", action="store_true", help="Solo descarga curvas, no aforos (para la segunda pasada de aforos, correr sin este flag)")
    parser.add_argument("--report-only", action="store_true", help="Solo regenera el reporte de cobertura a partir de lo ya descargado, sin pegarle a la API")
    args = parser.parse_args()

    _configure_logging()

    if args.report_only:
        report = build_coverage_report()
        print(f"Reporte escrito en {COVERAGE_CSV} ({len(report)} estaciones)")
        return

    if not args.stations and not args.group:
        raise SystemExit("Especifica --group {A,B} o --stations, o usa --report-only")

    target = resolve_target_stations(args)
    logger.info(f"Universo objetivo de esta corrida: {len(target)} estaciones")

    try:
        run_with_lock(target, args.only_missing, args.max_stations, args.skip_aforos)
    except drc.AnaApiError as exc:
        logger.error(str(exc))
        raise SystemExit(f"✗ {exc}")


if __name__ == "__main__":
    main()
