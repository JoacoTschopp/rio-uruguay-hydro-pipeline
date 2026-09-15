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
    iter_batches_calendar_backward,
    iter_ensemble_forecast_batch_by_day,
    missing_span,
    raw_filename,
    register_archive_dir,
    register_catalogo_fuente,
    load_unavailable_days,
    record_unavailable_day,
    retrieve_bisecting,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

OUT_DIR = Path(__file__).resolve().parent / "local_data" / "ecmwf_volume" / "pf_tigge"
RAW_DIR = OUT_DIR / "raw" / "historic"
JSON_DIR = OUT_DIR / "json"  # mismo folder que el job diario: Bronze lee toda la carpeta
register_catalogo_fuente(JSON_DIR, "ecmwf_pf")  # Decision 046

# Un dia de pf pesa ~272 MB en JSON (50 miembros x 16 pasos); a 1.674 dias eso llego a llenar
# los 953 GB del disco C: y corto el backfill con "No space left on device" (Decision 042). Los
# JSON ya subidos al Volume se archivan afuera, pero la resumibilidad se apoya en la presencia
# del archivo en disco, asi que hay que declarar donde quedaron o el orquestador los re-pide.
# Destino actual del archivado (disco externo de 4 TB, 2026-09-09) y el anterior, que se
# mantiene registrado mientras dure la migracion: durante la copia los archivos estan repartidos
# entre los dos y already_landed() tiene que encontrarlos en cualquiera de ellos.
ARCHIVE_JSON_DIRS = [
    Path(r"D:\rio_uruguay\pf_tigge_json"),
    Path(r"W:\Instaladores\swap\tschopp\pf_tigge_json"),
]
ARCHIVE_JSON_DIR = ARCHIVE_JSON_DIRS[0]  # destino de escritura nueva
for _d in ARCHIVE_JSON_DIRS:
    if _d.exists():
        register_archive_dir(JSON_DIR, _d)

DATASET = "tigge-forecasts"
ORIGIN = "ecmf"
PARAM = "228228"  # tp - total precipitation (codigo TIGGE/MARS), igual que el job diario
STEPS_HOURS = list(range(0, 361, 24))
MEMBERS = list(range(1, 51))
RUN_TIME = "00"

EARLIEST_TIGGE_DATE = date(2006, 10, 1)
TIGGE_LAG_DAYS = 2
# 1 request = 1 trimestre calendario. Era 1 mes (Decision 051).
#
# El costo dominante NO es la descarga sino la espera en la cola de ECDS: 11,6 h por request
# medidas sobre 16 requests, contra ~10 s de transferencia para 72 MB. O sea que el tiempo total
# del backfill lo fija la CANTIDAD de requests, no su tamano: pasar de 1 a 3 meses divide por
# tres los 131 lotes que faltaban.
#
# Por que 3 y no mas: 91 dias x 16 pasos x 50 miembros = ~72.800 "fields", 3x el request mensual
# que ya demostro funcionar (24.800) y todavia por debajo del limite documentado de otros
# datasets CDS (ERA5 horario: 120.000). Un lote anual serian 292.000, fuera de escala -- ver
# Decision 044, donde los tres `400 Client Error` observados cayeron justamente en los lotes
# anuales de `cf`.
#
# Lo que hace viable subir el tamano ahora y no entonces es `retrieve_bisecting` (Decision 049):
# un trimestre que falle ya no bloquea la cadena, se parte en mitades hasta aislar el dia que la
# fuente no entrega. Cuando se fijo BATCH_MONTHS=1 esa red no existia y un lote grande fallido
# costaba el lote entero.
#
# Disco: un trimestre son ~26 GB de JSON en C: antes de sincronizar y archivar. Con
# --sync-every-calls 1 (Decision 050) se drena despues de cada lote, asi que no se acumulan.
#
# Para volver atras: poner 1. La grilla esta alineada al calendario (Decision 044), asi que
# cambiar este numero no re-pide nada ya bajado -- `missing_span` recorta cada lote a los dias
# que realmente faltan.
BATCH_MONTHS = 3
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
    batches = iter_batches_calendar_backward(EARLIEST_TIGGE_DATE, latest, BATCH_MONTHS)
    no_disponibles = load_unavailable_days("pf")

    print(f"Rango objetivo: {EARLIEST_TIGGE_DATE.isoformat()} .. {latest.isoformat()} ({len(batches)} lotes mensuales totales)")

    if dry_run:
        for start, end in batches:
            pending = not (missing_span("pf", start, end, RUN_TIME, JSON_DIR, no_disponibles) is None)
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

        span = None if force_reload else missing_span("pf", start, end, RUN_TIME, JSON_DIR, no_disponibles)
        if not force_reload and span is None:
            print(f"Lote {start.isoformat()}..{end.isoformat()} ya completo, skip")
            continue

        # Se pide solo el tramo faltante, no el lote entero (Decision 044).
        req_start, req_end = (start, end) if force_reload else span
        if (req_start, req_end) != (start, end):
            print(f"Lote {start.isoformat()}..{end.isoformat()} parcial: se pide solo {req_start.isoformat()}..{req_end.isoformat()}")

        print(f"Pidiendo lote {req_start.isoformat()}..{req_end.isoformat()} ({(req_end - req_start).days + 1} dias x {len(MEMBERS)} miembros)...")
        piezas, tramos_fallidos = retrieve_bisecting(
            lambda s, e, dst: _retrieve_batch(client, s, e, area, dst),
            _batch_raw_path, req_start, req_end,
        )
        if not piezas:
            # Ninguna pieza bajo: bloqueo global, no un dia puntual. Se corta -- Decision 030.
            print("Se corta la ejecucion por el fallo anterior (no se reintenta en bucle).")
            failed = True
            break
        for s_bad, e_bad in tramos_fallidos:
            if s_bad == e_bad:
                record_unavailable_day("pf", s_bad, "ECDS devuelve 400 para un request de un solo dia")
                no_disponibles.add(s_bad)
        if tramos_fallidos:
            dias_malos = sum((e - s).days + 1 for s, e in tramos_fallidos)
            print(f"  la fuente no entrega {dias_malos} dia(s) de este lote: "
                  + ", ".join(f"{s.isoformat()}..{e.isoformat()}" for s, e in tramos_fallidos))

        n_days = 0
        n_records = 0
        for pieza_start, pieza_end, raw_path in piezas:
            ds = xr.open_dataset(raw_path, engine="netcdf4", decode_timedelta=False)
            for run_date_iso, records in iter_ensemble_forecast_batch_by_day(
                ds, tipo="pf", source_api="ecmwf_tigge_cdsapi_historic", unit_to_mm_factor=UNIT_TO_MM_FACTOR, area=None
            ):
                json_path = JSON_DIR / raw_filename("pf", date.fromisoformat(run_date_iso), RUN_TIME, "json")
                write_json(records, json_path)
                n_days += 1
                n_records += len(records)
                del records
            ds.close()
        print(f"OK lote {req_start.isoformat()}..{req_end.isoformat()}: {n_days} dias, {n_records} registros")

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
