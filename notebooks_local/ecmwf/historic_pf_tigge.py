"""Landing (local) - Reconstruccion historica del ensemble perturbado ECMWF (pf, TIGGE) via cdsapi.

Igual que historic_cf_tigge.py, pero pidiendo un mes calendario por request (no un anio):
con 50 miembros, un lote anual tendria ~292.000 "fields" (365 dias x 16 steps x 50 miembros),
un orden de magnitud grande y arriesgado para un solo request. Un lote mensual da ~24.000
fields, comparable al limite documentado de otros datasets CDS (ERA5 horario: 120.000).

Mismas reglas de seguridad frente a la API que historic_cf_tigge.py: un request a la vez,
tope de lotes por corrida, corte inmediato ante el primer fallo, resumible por diseño.
No correr al mismo tiempo que historic_cf_tigge.py, landing_cf_tigge.py ni landing_pf_tigge.py
(comparten cuenta/token con la misma cola de TIGGE/ECDS).

En Databricks este script se convierte 1:1 en notebooks/00_Landing/ECMWF/Historic_ECMWF_PF.ipynb.
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
    compute_download_area,
    date_range_str,
    iter_batches_backward,
    iter_ensemble_forecast_batch_by_day,
    raw_filename,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "pf_tigge"
RAW_DIR = OUT_DIR / "raw" / "historic"
JSON_DIR = OUT_DIR / "json"  # mismo folder que el job diario: Bronze lee toda la carpeta

DATASET = "tigge-forecasts"
ORIGIN = "ecmf"
PARAM = "228228"  # tp - total precipitation (codigo TIGGE/MARS), igual que el job diario
STEPS_HOURS = list(range(0, 361, 24))
MEMBERS = list(range(1, 51))
RUN_TIME = "00"

EARLIEST_TIGGE_DATE = date(2006, 10, 1)
TIGGE_LAG_DAYS = 2
BATCH_MONTHS = 1  # 1 request = 1 mes calendario (50 miembros multiplican los "fields")
UNIT_TO_MM_FACTOR = 1.0

DEFAULT_MAX_BATCHES_PER_RUN = 3
PAUSE_BETWEEN_REQUESTS_SECONDS = 2


def _batch_raw_path(start: date, end: date) -> Path:
    return RAW_DIR / f"ECMWF_PF_{start.isoformat()}_{end.isoformat()}.nc"


def _retrieve_batch(client, start: date, end: date, area: dict, target: Path) -> bool:
    request = {
        "origin": ORIGIN,
        "levtype": "sfc",
        "param": PARAM,
        "type": "pf",
        "number": [str(n) for n in MEMBERS],
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
    """Devuelve {"processed": N, "failed": bool} -- ver el docstring de la misma funcion en
    historic_cf_tigge.py (Decision 030, incidente de rate-limit: el caller necesita saber si
    hubo un fallo para no reintentar en bucle)."""
    latest = date.today() - timedelta(days=TIGGE_LAG_DAYS)
    batches = iter_batches_backward(EARLIEST_TIGGE_DATE, latest, BATCH_MONTHS)

    print(f"Rango objetivo: {EARLIEST_TIGGE_DATE.isoformat()} .. {latest.isoformat()} ({len(batches)} lotes mensuales totales)")

    if dry_run:
        for start, end in batches:
            pending = not batch_fully_landed("pf", start, end, RUN_TIME, JSON_DIR)
            print(f"  {start.isoformat()} .. {end.isoformat()}  {'PENDIENTE' if pending else 'completo'}")
        return {"processed": 0, "failed": False}

    area = compute_download_area(GEOJSON_PATH)
    print(f"Area de descarga calculada: {area}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    import cdsapi
    import xarray as xr

    client = cdsapi.Client()

    processed = 0
    failed = False
    for start, end in batches:
        if processed >= max_batches_per_run:
            print(f"Limite de {max_batches_per_run} lotes por corrida alcanzado, se corta aca. Volver a correr para continuar.")
            break

        if not force_reload and batch_fully_landed("pf", start, end, RUN_TIME, JSON_DIR):
            print(f"Lote {start.isoformat()}..{end.isoformat()} ya completo, skip")
            continue

        print(f"Pidiendo lote {start.isoformat()}..{end.isoformat()} ({(end - start).days + 1} dias x {len(MEMBERS)} miembros)...")
        raw_path = _batch_raw_path(start, end)
        if not _retrieve_batch(client, start, end, area, raw_path):
            print("Se corta la ejecucion por el fallo anterior (no se reintenta en bucle).")
            failed = True
            break

        ds = xr.open_dataset(raw_path, engine="netcdf4", decode_timedelta=False)
        n_days = 0
        n_records = 0
        for run_date_iso, records in iter_ensemble_forecast_batch_by_day(
            ds, tipo="pf", source_api="ecmwf_tigge_cdsapi_historic", unit_to_mm_factor=UNIT_TO_MM_FACTOR, area=None
        ):
            json_path = JSON_DIR / raw_filename("pf", date.fromisoformat(run_date_iso), RUN_TIME, "json")
            write_json(records, json_path)
            n_days += 1
            n_records += len(records)
            del records
        ds.close()
        print(f"OK lote {start.isoformat()}..{end.isoformat()}: {n_days} dias, {n_records} registros")

        processed += 1
        time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)

    if processed == 0 and not failed:
        print("Nada pendiente para procesar en este lote de trabajo (o limite en 0).")

    return {"processed": processed, "failed": failed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES_PER_RUN, help="Maximo de lotes (meses) a pedir en esta corrida")
    parser.add_argument("--dry-run", action="store_true", help="Solo lista los lotes y su estado, sin llamar a la API")
    parser.add_argument("--force-reload", action="store_true", help="Vuelve a pedir lotes aunque ya esten completos")
    args = parser.parse_args()
    run(max_batches_per_run=args.max_batches, dry_run=args.dry_run, force_reload=args.force_reload)
