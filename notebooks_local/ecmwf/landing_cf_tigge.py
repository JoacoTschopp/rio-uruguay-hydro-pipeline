"""Landing (local) - Control forecast ECMWF (cf, TIGGE) via cdsapi / ECMWF Data Stores.

Requiere credenciales en ~/.cdsapirc (url + key). El dataset 'tigge-forecasts'
tiene latencia de archivo: confirmado empiricamente que "ayer" falla y
"hace 2 dias" funciona (ver TIGGE_LAG_DAYS). Se busca hacia atras desde ese
punto por si el lag varia un poco dia a dia.

En Databricks este script se convierte 1:1 en notebooks/00_Landing/ECMWF/Daily_ECMWF_CF.ipynb,
reemplazando JSON_DIR/RAW_DIR por rutas /Volumes/... y las credenciales por
dbutils.secrets.get(scope="ecmwf", key="cdsapi_url"/"cdsapi_key") en vez de ~/.cdsapirc.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_ecmwf import already_landed, area_to_cds_list, compute_download_area, flatten_forecast, raw_filename, write_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "cf_tigge"
RAW_DIR = OUT_DIR / "raw"
JSON_DIR = OUT_DIR / "json"

DATASET = "tigge-forecasts"
ORIGIN = "ecmf"
PARAM = "228228"  # tp - total precipitation (codigo TIGGE/MARS)
STEPS_HOURS = list(range(0, 361, 24))  # 0, 24, 48, ..., 360

TIGGE_LAG_DAYS = 2  # confirmado empiricamente: "ayer" (lag=1) falla, "hace 2 dias" funciona
MAX_LAG_SEARCH = 5  # si el lag crece, buscar hacia atras hasta este limite antes de rendirse
UNIT_TO_MM_FACTOR = 1.0  # confirmado: tigge-forecasts entrega tp en kg/m2 == mm (NO metros)


def _try_retrieve(client, run_date: date, area: dict, target: Path) -> bool:
    request = {
        "origin": ORIGIN,
        "levtype": "sfc",
        "param": PARAM,
        "type": "cf",
        "step": [str(s) for s in STEPS_HOURS],
        "date": run_date.isoformat(),
        "time": "00:00:00",
        "area": area_to_cds_list(area),
        "grid": [0.25, 0.25],
        "data_format": "netcdf",
    }
    try:
        client.retrieve(DATASET, request, str(target))
        return True
    except Exception as e:
        print(f"  {run_date.isoformat()} no disponible todavia: {str(e)[:150]}")
        return False


def run(force_reload: bool = False) -> None:
    import cdsapi

    client = cdsapi.Client()
    area = compute_download_area(GEOJSON_PATH)
    print(f"Area de descarga calculada: {area}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    run_date = None
    for lag in range(TIGGE_LAG_DAYS, MAX_LAG_SEARCH + 1):
        candidate = date.today() - timedelta(days=lag)

        if already_landed("cf", candidate, "00", JSON_DIR) and not force_reload:
            print(f"Ya existe la corrida {candidate} t00 (cf), skip")
            return

        raw_path = RAW_DIR / raw_filename("cf", candidate, "00", "nc")
        print(f"Probando corrida cf de {candidate.isoformat()} (lag={lag} dias)...")
        if _try_retrieve(client, candidate, area, raw_path):
            run_date = candidate
            break

    if run_date is None:
        raise SystemExit(
            f"No se encontro ninguna corrida cf disponible entre lag={TIGGE_LAG_DAYS} y lag={MAX_LAG_SEARCH} dias"
        )

    import xarray as xr

    ds = xr.open_dataset(RAW_DIR / raw_filename("cf", run_date, "00", "nc"), engine="netcdf4", decode_timedelta=False)
    number = int(ds["number"].values) if "number" in ds.coords else None
    records = flatten_forecast(
        ds,
        run_date=run_date,
        run_time="00",
        tipo="cf",
        source_api="ecmwf_tigge_cdsapi",
        unit_to_mm_factor=UNIT_TO_MM_FACTOR,
        area=None,  # la API ya filtro server-side, no hace falta recortar de nuevo
        number=number,
    )
    print(f"Registros aplanados: {len(records)}")

    json_path = JSON_DIR / raw_filename("cf", run_date, "00", "json")
    write_json(records, json_path)
    print(f"OK {json_path.name}: {len(records)} registros")


if __name__ == "__main__":
    run()
