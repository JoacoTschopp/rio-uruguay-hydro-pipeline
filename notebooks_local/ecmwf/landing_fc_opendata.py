"""Landing (local) - Pronostico determinista ECMWF (fc, HRES) via Open Data.

Sin autenticacion, tiempo real (4 corridas/dia). La API no soporta recorte de
area server-side (se ignora silenciosamente), por eso se recorta al bounding
box localmente antes de escribir el JSON.

En Databricks este script se convierte 1:1 en notebooks/00_Landing/ECMWF/Daily_ECMWF_FC.ipynb,
reemplazando JSON_DIR/RAW_DIR por rutas /Volumes/... y sin cambios de credenciales
(esta fuente no necesita ninguna).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_ecmwf import already_landed, compute_download_area, flatten_forecast, raw_filename, write_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "fc_opendata"
RAW_DIR = OUT_DIR / "raw"
JSON_DIR = OUT_DIR / "json"

STEPS_HOURS = list(range(0, 361, 24))  # 0, 24, 48, ..., 360 (todos los horizontes diarios, 15 dias)
STREAM = "oper"
TYPE = "fc"
PARAM = "tp"
UNIT_TO_MM_FACTOR = 1000.0  # confirmado: Open Data entrega tp en metros


def run(force_reload: bool = False) -> None:
    from ecmwf.opendata import Client
    import xarray as xr

    client = Client(source="ecmwf")

    latest_run = client.latest(stream=STREAM, type=TYPE, param=PARAM)
    run_date = latest_run.date()
    run_time = f"{latest_run.hour:02d}"

    print(f"Corrida mas reciente disponible: {latest_run.isoformat()}")

    if already_landed(TYPE, run_date, run_time, JSON_DIR) and not force_reload:
        print(f"Ya existe la corrida {run_date} t{run_time} (fc), skip")
        return

    area = compute_download_area(GEOJSON_PATH)
    print(f"Area de descarga calculada: {area}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / raw_filename(TYPE, run_date, run_time, "grib2")

    print(f"Descargando steps {STEPS_HOURS} -> {raw_path}")
    client.retrieve(
        stream=STREAM,
        type=TYPE,
        param=PARAM,
        step=STEPS_HOURS,
        target=str(raw_path),
    )

    ds = xr.open_dataset(raw_path, engine="cfgrib", decode_timedelta=True)
    records = flatten_forecast(
        ds,
        run_date=run_date,
        run_time=run_time,
        tipo=TYPE,
        source_api="ecmwf_opendata",
        unit_to_mm_factor=UNIT_TO_MM_FACTOR,
        area=area,
    )
    print(f"Registros aplanados y recortados al bbox: {len(records)}")

    json_path = JSON_DIR / raw_filename(TYPE, run_date, run_time, "json")
    write_json(records, json_path)
    print(f"OK {json_path.name}: {len(records)} registros")


if __name__ == "__main__":
    run()
