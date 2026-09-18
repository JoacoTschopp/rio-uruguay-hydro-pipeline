"""Landing (local) - Reconstruccion historica del control forecast ECMWF (cf, TIGGE) via cdsapi.

Mismo dataset/origen/parametro que landing_cf_tigge.py (el job diario), pero pidiendo
un anio calendario completo por request en vez de un dia, para no generar ~7000 requests
individuales contra la cola de TIGGE/ECDS. El archivo TIGGE arranca en 2006-10-01: no hay
datos anteriores en esta fuente (confirmado en la documentacion de ECMWF), por lo que ese
es el limite duro hacia atras, no 2000.

Reglas de seguridad frente a la API (no negociables, ver docs/decisions.md):
- Un solo request a la vez, nunca en paralelo con este mismo script ni con landing_cf_tigge.py
  ni con historic_pf_tigge.py corriendo al mismo tiempo (comparten cuenta/token).
- Como mucho MAX_BATCHES_PER_RUN lotes por ejecucion (por defecto 3): permite frenar,
  revisar y retomar sin dejar un proceso corriendo indefinidamente sin supervision.
- Si un request falla, se corta la ejecucion en el acto (no se reintenta en bucle):
  un fallo persistente (licencia, cuota, credenciales) no debe traducirse en spam de
  requests fallidos contra la cola.
- Resumible por diseño: antes de pedir un lote se chequea si TODOS los dias de ese lote
  ya tienen JSON en disco; si es asi, se saltea sin llamar a la API. Correr este script
  N veces hasta terminar es seguro.

En Databricks este script se convierte 1:1 en notebooks/00_Landing/ECMWF/Historic_ECMWF_CF.ipynb
(mismo patron que landing_cf_tigge.py -> Daily_ECMWF_CF.ipynb), reemplazando JSON_DIR/RAW_DIR
por rutas /Volumes/... y las credenciales por dbutils.secrets.get(scope="ecmwf", ...).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_ecmwf import (  # noqa: E402
    area_to_cds_list,
    batch_fully_landed,
    batch_in_cooldown,
    compute_download_area,
    date_range_str,
    flatten_forecast_batch,
    is_recent_frontier_day,
    iter_batches_calendar_backward,
    load_batch_cooldowns,
    missing_span,
    raw_filename,
    record_batch_cooldown,
    register_catalogo_fuente,
    load_unavailable_days,
    record_unavailable_day,
    retrieve_bisecting,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "cf_tigge"
RAW_DIR = OUT_DIR / "raw" / "historic"
JSON_DIR = OUT_DIR / "json"  # mismo folder que el job diario: Bronze lee toda la carpeta
register_catalogo_fuente(JSON_DIR, "ecmwf_cf")  # Decision 046

DATASET = "tigge-forecasts"
ORIGIN = "ecmf"
PARAM = "228228"  # tp - total precipitation (codigo TIGGE/MARS), igual que el job diario
STEPS_HOURS = list(range(0, 361, 24))
RUN_TIME = "00"

EARLIEST_TIGGE_DATE = date(2006, 10, 1)  # inicio real del archivo TIGGE (no hay datos antes)
TIGGE_LAG_DAYS = 2  # mismo margen que el job diario, para no pisar su ventana
BATCH_MONTHS = 12  # 1 request = 1 anio calendario (~5.840 fields, holgado)
UNIT_TO_MM_FACTOR = 1.0  # tigge-forecasts entrega tp en kg/m2 == mm, igual que el job diario

DEFAULT_MAX_BATCHES_PER_RUN = 3
PAUSE_BETWEEN_REQUESTS_SECONDS = 2

# ECMWF confirmo (2026-08-26) una cinta danada en su archivo MARS (J0018900) que cubre el lote
# anual que en ese momento pedia 2017-08-25..2018-08-24 (AccessError, no un fallo transitorio --
# reintentar no sirve). El rango exacto de cada lote corre ~1 dia por dia respecto de hoy (ver
# EARLIEST_TIGGE_DATE/BATCH_MONTHS), asi que se compara por solapamiento contra una ventana
# generosa, no por igualdad exacta. Se saltea explicitamente en vez de dejar que el orquestador
# corte "cf" para siempre en este lote (Decision 031, aceptado como hueco de cobertura: este
# tramo es solo para calibrar el empalme GEFS/TIGGE, quedan otros ~12 anios de solapamiento).
# Ambito: solo `cf` -- no se confirmo que `pf` pegue contra la misma cinta.
KNOWN_UNAVAILABLE_RANGES: list[tuple[date, date, str]] = [
    (date(2017, 6, 1), date(2018, 11, 30), "Cinta ECMWF danada J0018900 (Decision 031)"),
]


def _known_unavailable_reason(start: date, end: date) -> str | None:
    for bad_start, bad_end, reason in KNOWN_UNAVAILABLE_RANGES:
        if start <= bad_end and end >= bad_start:
            return reason
    return None


def _batch_raw_path(start: date, end: date) -> Path:
    return RAW_DIR / f"ECMWF_CF_{start.isoformat()}_{end.isoformat()}.nc"


def _retrieve_batch(client, start: date, end: date, area: dict, target: Path) -> bool:
    request = {
        "origin": ORIGIN,
        "levtype": "sfc",
        "param": PARAM,
        "type": "cf",
        "step": [str(s) for s in STEPS_HOURS],
        "date": date_range_str(start, end),
        "time": "00:00:00",
        "area": area_to_cds_list(area),
        "grid": [0.25, 0.25],
        "data_format": "netcdf",
    }
    try:
        client.retrieve(DATASET, request, str(target))
        return True
    except Exception as e:
        print(f"  FALLO lote {start.isoformat()}..{end.isoformat()}: {str(e)[:300]}")
        return False


def run(max_batches_per_run: int = DEFAULT_MAX_BATCHES_PER_RUN, dry_run: bool = False, force_reload: bool = False) -> dict:
    """Devuelve {"processed": N, "failed": bool}. `failed=True` es la senal para que el
    caller (run_tigge_backfill.py) NO vuelva a llamar run() de inmediato -- sin esto, un
    lote que falla (ej. la cola de ECDS rechaza el request) queda pendiente para siempre y
    el orquestador lo reintenta en un loop apretado, exactamente el anti-patron "reintentos
    en bucle" que este modulo dice evitar (ver Decision 030, incidente de rate-limit).

    `failed` ya NO se pone en True por un solo lote sin piezas -- ese lote se pone en
    cooldown (common_ecmwf.record_batch_cooldown) y la corrida sigue con el resto de lo
    pendiente. Solo queda en True si, al terminar, no se proceso NADA (bloqueo global real).
    Antes, como la grilla es calendario-descendente (Decision 044) y el cupo por llamada es 1
    (Decision 050), el primer lote de la lista (el frente) fallando cortaba la corrida entera
    y el historico no avanzaba nunca, ni una vez -- hallazgo real, 2026-09-18."""
    latest = date.today() - timedelta(days=TIGGE_LAG_DAYS)
    batches = iter_batches_calendar_backward(EARLIEST_TIGGE_DATE, latest, BATCH_MONTHS)
    no_disponibles = load_unavailable_days("cf")
    en_cooldown = load_batch_cooldowns("cf")

    print(f"Rango objetivo: {EARLIEST_TIGGE_DATE.isoformat()} .. {latest.isoformat()} ({len(batches)} lotes anuales totales)")

    if dry_run:
        for start, end in batches:
            pending = not (missing_span("cf", start, end, RUN_TIME, JSON_DIR, no_disponibles) is None)
            print(f"  {start.isoformat()} .. {end.isoformat()}  {'PENDIENTE' if pending else 'completo'}")
        return {"processed": 0, "failed": False}

    area = compute_download_area(GEOJSON_PATH)
    print(f"Area de descarga calculada: {area}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    import cdsapi
    import xarray as xr

    client = cdsapi.Client()

    processed = 0
    algo_fallo = False
    for start, end in batches:
        if processed >= max_batches_per_run:
            print(f"Limite de {max_batches_per_run} lotes por corrida alcanzado, se corta aca. Volver a correr para continuar.")
            break

        if batch_in_cooldown(start, end, en_cooldown):
            print(f"Lote {start.isoformat()}..{end.isoformat()} en cooldown (fallo sin piezas hace poco), se saltea por ahora")
            continue

        span = None if force_reload else missing_span("cf", start, end, RUN_TIME, JSON_DIR, no_disponibles)
        if not force_reload and span is None:
            print(f"Lote {start.isoformat()}..{end.isoformat()} ya completo, skip")
            continue

        unavailable_reason = _known_unavailable_reason(start, end)
        if unavailable_reason:
            print(f"Lote {start.isoformat()}..{end.isoformat()} saltado (dato no disponible en origen): {unavailable_reason}")
            continue

        # Se pide solo el tramo faltante, no el lote entero (Decision 044).
        req_start, req_end = (start, end) if force_reload else span
        if (req_start, req_end) != (start, end):
            print(f"Lote {start.isoformat()}..{end.isoformat()} parcial: se pide solo {req_start.isoformat()}..{req_end.isoformat()}")

        print(f"Pidiendo lote {req_start.isoformat()}..{req_end.isoformat()} ({(req_end - req_start).days + 1} dias)...")
        piezas, tramos_fallidos = retrieve_bisecting(
            lambda s, e, dst: _retrieve_batch(client, s, e, area, dst),
            _batch_raw_path, req_start, req_end,
        )
        if not piezas:
            # Ni una pieza bajo de este lote puntual: cooldown y se sigue con el resto de lo
            # pendiente en vez de cortar toda la corrida (ver docstring de run() mas arriba).
            print(f"  lote {req_start.isoformat()}..{req_end.isoformat()} sin ninguna pieza, "
                  f"cooldown por unas horas y se sigue con el resto de lo pendiente")
            record_batch_cooldown("cf", start, end)
            algo_fallo = True
            continue
        for s_bad, e_bad in tramos_fallidos:
            if s_bad == e_bad:
                if is_recent_frontier_day(s_bad):
                    print(f"  {s_bad.isoformat()} es un dia reciente (frente), no se marca como no "
                          f"disponible para siempre -- puede que la fuente todavia no lo publico")
                else:
                    record_unavailable_day("cf", s_bad, "ECDS devuelve 400 para un request de un solo dia")
                    no_disponibles.add(s_bad)
        if tramos_fallidos:
            dias_malos = sum((e - s).days + 1 for s, e in tramos_fallidos)
            print(f"  la fuente no entrega {dias_malos} dia(s) de este lote: "
                  + ", ".join(f"{s.isoformat()}..{e.isoformat()}" for s, e in tramos_fallidos))

        n_dias = n_records = 0
        for pieza_start, pieza_end, raw_path in piezas:
            ds = xr.open_dataset(raw_path, engine="netcdf4", decode_timedelta=False)
            by_day = flatten_forecast_batch(ds, tipo="cf", source_api="ecmwf_tigge_cdsapi_historic", unit_to_mm_factor=UNIT_TO_MM_FACTOR, area=None)
            for run_date_iso, records in by_day.items():
                json_path = JSON_DIR / raw_filename("cf", date.fromisoformat(run_date_iso), RUN_TIME, "json")
                write_json(records, json_path)
            n_dias += len(by_day)
            n_records += sum(len(r) for r in by_day.values())
            ds.close()
        print(f"OK lote {req_start.isoformat()}..{req_end.isoformat()}: {n_dias} dias, {n_records} registros")

        processed += 1
        time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)

    if processed == 0 and not algo_fallo:
        print("Nada pendiente para procesar en este lote de trabajo (o limite en 0).")

    failed = algo_fallo and processed == 0
    return {"processed": processed, "failed": failed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES_PER_RUN, help="Maximo de lotes (anios) a pedir en esta corrida")
    parser.add_argument("--dry-run", action="store_true", help="Solo lista los lotes y su estado, sin llamar a la API")
    parser.add_argument("--force-reload", action="store_true", help="Vuelve a pedir lotes aunque ya esten completos")
    args = parser.parse_args()
    run(max_batches_per_run=args.max_batches, dry_run=args.dry_run, force_reload=args.force_reload)
