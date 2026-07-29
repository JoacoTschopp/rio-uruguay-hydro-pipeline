"""Landing (local) - Perturbed forecast ECMWF (pf, TIGGE ensemble) via cdsapi / ECMWF Data Stores.

Igual que landing_cf_tigge.py pero con los 50 miembros perturbados del ensemble
(type="pf", number=1..50) en vez del control. Mismo dataset, mismo origen, misma
latencia de archivo confirmada empiricamente (TIGGE_LAG_DAYS=2).

En Databricks este script se convierte 1:1 en notebooks/00_Landing/ECMWF/Daily_ECMWF_PF.ipynb,
reemplazando JSON_DIR/RAW_DIR por rutas /Volumes/... y las credenciales por
dbutils.secrets.get(scope="ecmwf", key="cdsapi_url"/"cdsapi_key") en vez de ~/.cdsapirc.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_ecmwf import already_landed, area_to_cds_list, compute_download_area, flatten_ensemble_forecast, raw_filename, write_json  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "pf_tigge"
RAW_DIR = OUT_DIR / "raw"
JSON_DIR = OUT_DIR / "json"

DATASET = "tigge-forecasts"
ORIGIN = "ecmf"
PARAM = "228228"  # tp - total precipitation (codigo TIGGE/MARS), mismo parametro que cf
STEPS_HOURS = list(range(0, 361, 24))  # 0, 24, 48, ..., 360
MEMBERS = list(range(1, 51))  # ensemble TIGGE ecmf: 50 miembros perturbados

TIGGE_LAG_DAYS = 2  # confirmado empiricamente (igual que cf): "ayer" falla, "hace 2 dias" funciona
MAX_LAG_SEARCH = 5
UNIT_TO_MM_FACTOR = 1.0  # confirmado: tigge-forecasts entrega tp en kg/m2 == mm (igual que cf)


def _try_retrieve(client, run_date: date, area: dict, target: Path) -> bool:
    request = {
        "origin": ORIGIN,
        "levtype": "sfc",
        "param": PARAM,
        "type": "pf",
        "number": [str(n) for n in MEMBERS],
        "step": [str(s) for s in STEPS_HOURS],
        "date": run_date.isoformat(),
        "time": "00:00:00",
        "area": area_to_cds_list(area),
        "grid": [0.25, 0.25],
        "format": "netcdf",
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

        if already_landed("pf", candidate, "00", JSON_DIR) and not force_reload:
            print(f"Ya existe la corrida {candidate} t00 (pf), skip")
            return

        raw_path = RAW_DIR / raw_filename("pf", candidate, "00", "nc")
        print(f"Probando corrida pf de {candidate.isoformat()} (lag={lag} dias, {len(MEMBERS)} miembros)...")
        if _try_retrieve(client, candidate, area, raw_path):
            run_date = candidate
            break

    if run_date is None:
        raise SystemExit(
            f"No se encontro ninguna corrida pf disponible entre lag={TIGGE_LAG_DAYS} y lag={MAX_LAG_SEARCH} dias"
        )

    import xarray as xr

    ds = xr.open_dataset(RAW_DIR / raw_filename("pf", run_date, "00", "nc"), engine="netcdf4", decode_timedelta=False)
    records = flatten_ensemble_forecast(
        ds,
        run_date=run_date,
        run_time="00",
        tipo="pf",
        source_api="ecmwf_tigge_cdsapi",
        unit_to_mm_factor=UNIT_TO_MM_FACTOR,
        area=None,  # la API ya filtro server-side, no hace falta recortar de nuevo
    )
    print(f"Registros aplanados: {len(records)}")

    json_path = JSON_DIR / raw_filename("pf", run_date, "00", "json")
    write_json(records, json_path)
    print(f"OK {json_path.name}: {len(records)} registros")


if __name__ == "__main__":
    run()
