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
    compute_download_area,
    date_range_str,
    flatten_forecast_batch,
    iter_batches_backward,
    raw_filename,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "cf_tigge"
RAW_DIR = OUT_DIR / "raw" / "historic"
JSON_DIR = OUT_DIR / "json"  # mismo folder que el job diario: Bronze lee toda la carpeta

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
        "format": "netcdf",
    }
    try:
        client.retrieve(DATASET, request, str(target))
        return True
    except Exception as e:
        print(f"  FALLO lote {start.isoformat()}..{end.isoformat()}: {str(e)[:300]}")
        return False


def run(max_batches_per_run: int = DEFAULT_MAX_BATCHES_PER_RUN, dry_run: bool = False, force_reload: bool = False) -> None:
    latest = date.today() - timedelta(days=TIGGE_LAG_DAYS)
    batches = iter_batches_backward(EARLIEST_TIGGE_DATE, latest, BATCH_MONTHS)

    print(f"Rango objetivo: {EARLIEST_TIGGE_DATE.isoformat()} .. {latest.isoformat()} ({len(batches)} lotes anuales totales)")

    if dry_run:
        for start, end in batches:
            pending = not batch_fully_landed("cf", start, end, RUN_TIME, JSON_DIR)
            print(f"  {start.isoformat()} .. {end.isoformat()}  {'PENDIENTE' if pending else 'completo'}")
        return

    area = compute_download_area(GEOJSON_PATH)
    print(f"Area de descarga calculada: {area}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    import cdsapi
    import xarray as xr

    client = cdsapi.Client()

    processed = 0
    for start, end in batches:
        if processed >= max_batches_per_run:
            print(f"Limite de {max_batches_per_run} lotes por corrida alcanzado, se corta aca. Volver a correr para continuar.")
            break

        if not force_reload and batch_fully_landed("cf", start, end, RUN_TIME, JSON_DIR):
            print(f"Lote {start.isoformat()}..{end.isoformat()} ya completo, skip")
            continue

        print(f"Pidiendo lote {start.isoformat()}..{end.isoformat()} ({(end - start).days + 1} dias)...")
        raw_path = _batch_raw_path(start, end)
        if not _retrieve_batch(client, start, end, area, raw_path):
            print("Se corta la ejecucion por el fallo anterior (no se reintenta en bucle).")
            break

        ds = xr.open_dataset(raw_path, engine="netcdf4", decode_timedelta=False)
        by_day = flatten_forecast_batch(ds, tipo="cf", source_api="ecmwf_tigge_cdsapi_historic", unit_to_mm_factor=UNIT_TO_MM_FACTOR, area=None)
        for run_date_iso, records in by_day.items():
            json_path = JSON_DIR / raw_filename("cf", date.fromisoformat(run_date_iso), RUN_TIME, "json")
            write_json(records, json_path)
        print(f"OK lote {start.isoformat()}..{end.isoformat()}: {len(by_day)} dias, {sum(len(r) for r in by_day.values())} registros")

        processed += 1
        time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)

    if processed == 0:
        print("Nada pendiente para procesar en este lote de trabajo (o limite en 0).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES_PER_RUN, help="Maximo de lotes (anios) a pedir en esta corrida")
    parser.add_argument("--dry-run", action="store_true", help="Solo lista los lotes y su estado, sin llamar a la API")
    parser.add_argument("--force-reload", action="store_true", help="Vuelve a pedir lotes aunque ya esten completos")
    args = parser.parse_args()
    run(max_batches_per_run=args.max_batches, dry_run=args.dry_run, force_reload=args.force_reload)
