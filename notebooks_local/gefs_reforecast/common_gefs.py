"""Funciones compartidas para el backfill local de GEFS Reforecast v12 (NOAA).

Ver docs/data_sources.md §9.4 y Decision 026/028 en docs/decisions.md antes de tocar este
modulo: documenta el porque de cada decision de diseno de aca (formato de archivo, gotcha de
precipitacion acumulada por bloque, offset entre tramos de resolucion).

Notas de diseno confirmadas empiricamente (no asumidas, ver Decision 028):
- El bucket S3 `noaa-gefs-retrospective` es publico, sin autenticacion: HTTPS GET directo a
  `https://noaa-gefs-retrospective.s3.amazonaws.com/<key>` funciona sin credenciales.
- Cada corrida/miembro tiene DOS archivos GRIB2 para `apcp_sfc`: `Days:1-10/` (grilla 0,25°,
  pasos de 3h, hasta +240h) y `Days:10-16/` (grilla 0,50°, pasos de 6h, desde +246h hasta +384h).
- `apcp_sfc` viene acumulado SOLO en el bloque de 3h/6h mas reciente, no acumulado desde el
  inicio de la corrida (a diferencia de `tp` de TIGGE) — confirmado leyendo valores reales
  (no monotonos entre steps). Hay que hacer `cumsum()` a lo largo del eje `step` para que sea
  comparable a `tp_mm` de cf/pf.
- Los puntos de grilla de 0,50° son un subconjunto exacto de los de 0,25° (mismo origen, factor
  2x) — no hace falta interpolar para empalmar los dos tramos: se puede usar el ultimo valor
  acumulado del tramo de 0,25° como offset del tramo de 0,50°, seleccionando (`reindex`,
  `method="nearest"`, tolerancia chica) los mismos puntos exactos.
- El area de descarga NO se recorta server-side (a diferencia de TIGGE, que si soporta el
  parametro `area` de cdsapi): cada archivo cubre la grilla global. Recortar client-side
  inmediatamente despues de abrir el archivo, antes de cualquier otro procesamiento, es
  obligatorio para no acumular ~950 GB sin usar (ver Decision 026).
- **Gotcha adicional, encontrado al implementar (Decision 028), no documentado en el PDF
  oficial de NOAA:** el archivo `Days:1-10` de cada miembro perturbado (`p01`..`p10`) mezcla
  DOS `dataType` de GRIB2 en un solo archivo: 79 mensajes con `dataType=pf` (steps +6h a +240h)
  y **un solo mensaje con `dataType=cf`** para el primer step (+3h) -- `cfgrib`/`eccodes` no
  puede abrir ese archivo sin `filter_by_keys` porque las claves quedan ambiguas. Verificado
  empiricamente que ese mensaje "cf" del step +3h es identico entre miembros perturbados
  (mismo valor en p01 y p02 en el mismo punto de grilla): es el primer paso de acumulacion,
  compartido entre miembros porque la dispersion del ensemble todavia no crecio, simplemente
  mal etiquetado por el codificador GRIB2 de NOAA. Hay que leer ambos `dataType` y concatenar
  para no perder el step +3h de los miembros perturbados. El tramo `Days:10-16` no tiene este
  problema (siempre `pf` puro para miembros perturbados). El miembro `c00` tampoco (siempre
  `cf` puro, en los dos tramos).
"""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[2]
ECMWF_DIR = REPO_ROOT / "notebooks_local" / "ecmwf"


def _load_common_ecmwf():
    # Carga common_ecmwf.py por ruta exacta (importlib), sin tocar sys.path: insertar
    # ECMWF_DIR en sys.path (como se hacia antes) hace que CUALQUIER modulo con el mismo
    # nombre en ese directorio (ej. sync_to_databricks.py, que ahora existe tanto en
    # notebooks_local/ecmwf/ como aca) le gane por orden de busqueda a la version local de
    # gefs_reforecast/ -- confirmado empiricamente: el sync periodico de un backfill largo
    # de GEFS termino llamando al sync_to_databricks.py de ECMWF por error (ver Decision 030).
    spec = importlib.util.spec_from_file_location("common_ecmwf_for_gefs", ECMWF_DIR / "common_ecmwf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_common_ecmwf = _load_common_ecmwf()
compute_download_area = _common_ecmwf.compute_download_area
normalize_longitude = _common_ecmwf.normalize_longitude
write_json = _common_ecmwf.write_json

BUCKET_BASE = "https://noaa-gefs-retrospective.s3.amazonaws.com"
S3_LIST_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

VARIABLE = "apcp_sfc"
TRAMO_1 = "Days:1-10"
# El segundo tramo se llama distinto segun el horizonte de la corrida (confirmado en el bucket
# real, no documentado en el PDF oficial de NOAA): "Days:10-16" en la corrida diaria estandar
# (5 miembros, horizonte +16d), "Days:10-35" en la corrida extendida semanal (11 miembros,
# horizonte +35d). Probar ambas nombres en orden -- son las unicas dos variantes que existen
# segun la documentacion de NOAA (ver Decision 026/030).
TRAMO_2_CANDIDATES = ["Days:10-16", "Days:10-35"]
MAX_STEP_HOURS = 14 * 24  # el dataset de tesis no usa horizontes mas alla de t+14 (roadmap.md §1)
STANDARD_MEMBERS = ["c00", "p01", "p02", "p03", "p04"]
EXTENDED_MEMBERS = STANDARD_MEMBERS + [f"p{n:02d}" for n in range(5, 11)]  # hasta p10 en corridas de 11 miembros
EARLIEST_GEFS_DATE = date(2000, 1, 1)
LATEST_GEFS_DATE = date(2019, 12, 31)
GRID_REGRID_TOLERANCE_DEG = 0.01


def gefs_key(run_date: date, member: str, tramo: str) -> str:
    yyyymmdd00 = f"{run_date:%Y%m%d}00"
    return f"GEFSv12/reforecast/{run_date.year}/{yyyymmdd00}/{member}/{tramo}/{VARIABLE}_{yyyymmdd00}_{member}.grib2"


def gefs_url(run_date: date, member: str, tramo: str) -> str:
    return f"{BUCKET_BASE}/{gefs_key(run_date, member, tramo)}"


def list_members(session, run_date: date) -> list[str]:
    """Lista los miembros realmente publicados para una fecha (5 la mayoria de los dias,
    hasta 11 en la corrida extendida semanal), vía el listado S3 con delimiter -- no asume
    que siempre sean 5, ni que la corrida extendida caiga un dia fijo de la semana."""
    prefix = f"GEFSv12/reforecast/{run_date.year}/{run_date:%Y%m%d}00/"
    resp = session.get(BUCKET_BASE, params={"list-type": "2", "prefix": prefix, "delimiter": "/"}, timeout=30)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    members = []
    for cp in root.findall("s3:CommonPrefixes/s3:Prefix", S3_LIST_NS):
        # ".../{yyyymmdd00}/{member}/" -> {member}
        parts = cp.text.rstrip("/").split("/")
        members.append(parts[-1])
    return sorted(members)


def download_file(session, url: str, dest: Path, max_retries: int = 4) -> bool:
    """Descarga a un archivo local temporal. False si el objeto no existe (404) -- no es un
    error, ese miembro/tramo no se publico para esa fecha. Reintenta con backoff exponencial
    ante errores transitorios (timeout, 5xx, conexion resetada) -- necesario en modo concurrente
    (varios workers pegandole a S3 en simultaneo pueden gatillar `503 SlowDown` ocasional en el
    bucket publico, a diferencia de TIGGE/ECDS donde "no reintentar" es la regla por compartir
    token/cola con un solo usuario; aca no hay cuenta ni cola que proteger)."""
    import time as _time

    import requests as _requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=180, stream=True)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
            return True
        except (_requests.exceptions.RequestException, OSError):
            if attempt == max_retries - 1:
                raise
            _time.sleep(2 ** attempt)
    return False


def _crop(ds, area: dict):
    west360 = area["west"] % 360
    east360 = area["east"] % 360
    return ds.sel(latitude=slice(area["north"], area["south"]), longitude=slice(west360, east360))


def _open_tramo1(path: Path, member: str):
    """Abre el archivo `Days:1-10` de `apcp_sfc`. Para `c00` es un `xr.open_dataset` directo
    (archivo `dataType=cf` puro). Para miembros perturbados hay que pedir explicitamente
    `dataType='pf'` y `dataType='cf'` por separado -- ver el gotcha documentado en el docstring
    del modulo. Sin esto, `cfgrib` tira `multiple values for unique key` porque el archivo
    mezcla ambos tipos.

    **El split entre `pf`/`cf` no es fijo (confirmado al diagnosticar un fallo real, ver
    Decision 030):** la mayoria de las fechas trae 79 mensajes `pf` (+6h a +240h) + 1 mensaje
    `cf` (+3h, ver el gotcha del docstring del modulo), pero algunas fechas traen los 80 steps
    completos como `pf` sin ningun mensaje `cf` en absoluto -- filtrar por `dataType='cf'` en
    esos casos da un dataset vacio (sin dimension `step`), y `xr.concat` con eso tira
    `ValueError: coordinate 'step' not present in all datasets`. Se chequea si `ds_cf` tiene
    datos antes de concatenar; si no tiene, se usa `ds_pf` solo.

    Devuelve (dataset, lista_de_datasets_a_cerrar): el dataset final puede ser un `xr.concat`
    derivado (no cerrable directamente), asi que el caller tiene que cerrar los originales por
    separado -- necesario para no filtrar memoria en una corrida larga (ver Decision 030)."""
    import xarray as xr

    if member == "c00":
        ds = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": ""})
        return ds, [ds]

    ds_pf = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": "", "filter_by_keys": {"dataType": "pf"}})
    ds_cf = xr.open_dataset(path, engine="cfgrib", backend_kwargs={"indexpath": "", "filter_by_keys": {"dataType": "cf"}})

    if "step" not in ds_cf.dims:
        ds_cf.close()
        return ds_pf, [ds_pf]
    if "step" not in ds_pf.dims:
        ds_pf.close()
        return ds_cf, [ds_cf]

    merged = xr.concat([ds_cf, ds_pf], dim="step").sortby("step")
    return merged, [ds_pf, ds_cf]


def _step_hours_from_timedelta(step_val) -> int:
    import numpy as np

    return int(step_val / np.timedelta64(1, "h"))


def flatten_member_day(
    session,
    run_date: date,
    member: str,
    area: dict,
    tmp_dir: Path,
    source_api: str = "gefs_reforecast_v12_s3",
) -> Optional[list[dict]]:
    """Descarga los dos tramos de `apcp_sfc` para (run_date, member), recorta al area, acumula
    (`cumsum`) con offset entre tramos, aplana a records comparables a `tp_mm` de TIGGE, y borra
    los .grib2 temporales. Devuelve None si el miembro no existe para esa fecha (404 en el
    primer tramo -- ninguna corrida tiene el tramo 2 sin el tramo 1).

    Dos cosas necesarias para una corrida larga (miles de dias, confirmado empiricamente,
    ver Decision 030): (1) cerrar explicitamente cada `xr.Dataset` abierto (`ds.close()`) --
    sin esto, en un `ProcessPoolExecutor` que reutiliza el mismo worker para muchas tareas
    seguidas, la memoria de cada apertura de GRIB2 se va acumulando hasta un `MemoryError`
    de a poco, no en el primer request; (2) indexar la grilla con arrays de numpy (`.values`
    una sola vez + indices enteros) en vez de `.sel(latitude=lat, longitude=lon)` por cada
    punto -- el `.sel()` punto a punto es ~2 ordenes de magnitud mas lento que indexar un
    array ya materializado, y en 80-104 steps x ~1000 puntos de grilla eso es la diferencia
    entre minutos y segundos por dia."""
    import numpy as np

    tmp_dir.mkdir(parents=True, exist_ok=True)
    raw_paths = []
    to_close = []
    try:
        url1 = gefs_url(run_date, member, TRAMO_1)
        path1 = tmp_dir / f"{VARIABLE}_{run_date:%Y%m%d}00_{member}_d1_10.grib2"
        if not download_file(session, url1, path1):
            return None
        raw_paths.append(path1)

        ds1, ds1_originals = _open_tramo1(path1, member)
        to_close.extend(ds1_originals)
        sub1 = _crop(ds1, area)
        cum1 = sub1["tp"].cumsum(dim="step")
        # xr.concat (miembros perturbados, ver _open_tramo1) no garantiza el orden de las
        # dimensiones -- confirmado empiricamente que puede devolver (lat, lon, step) en vez de
        # (step, lat, lon). Forzar el orden antes de leer .values evita indexar el eje
        # equivocado (fallaba con IndexError intermitente, solo en miembros perturbados).
        cum1 = cum1.transpose("step", "latitude", "longitude")
        cum1_vals = cum1.values  # (step, lat, lon), materializa una sola vez
        lats1 = cum1.latitude.values
        lons1 = cum1.longitude.values
        lons1_norm = np.array([normalize_longitude(float(lon)) for lon in lons1])

        run_time_str = "00"
        extracted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []

        for step_idx, step_val in enumerate(cum1.step.values):
            step_hours = _step_hours_from_timedelta(step_val)
            valid_dt = datetime.combine(run_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=step_hours)
            slice_2d = cum1_vals[step_idx]
            for i, lat in enumerate(lats1):
                for j, lon_norm in enumerate(lons1_norm):
                    value = float(slice_2d[i, j])
                    if value != value:  # NaN check sin depender de math/np aca
                        continue
                    records.append({
                        "run_date": run_date.isoformat(),
                        "run_time": run_time_str,
                        "step_hours": int(step_hours),
                        "valid_datetime": valid_dt.isoformat(),
                        "valid_date": valid_dt.date().isoformat(),
                        "latitude": float(lat),
                        "longitude": float(lon_norm),
                        "tp_mm": value,
                        "member": member,
                        "tramo": TRAMO_1,
                        "tipo": "gefs",
                        "source_api": source_api,
                        "extracted_at": extracted_at,
                    })

        path2 = tmp_dir / f"{VARIABLE}_{run_date:%Y%m%d}00_{member}_d10_plus.grib2"
        tramo2_name = None
        for candidate in TRAMO_2_CANDIDATES:
            if download_file(session, gefs_url(run_date, member, candidate), path2):
                tramo2_name = candidate
                break

        if tramo2_name is not None:
            import xarray as xr

            raw_paths.append(path2)
            ds2 = xr.open_dataset(path2, engine="cfgrib", backend_kwargs={"indexpath": ""})
            to_close.append(ds2)
            sub2 = _crop(ds2, area)

            offset = cum1.isel(step=-1).reindex(
                latitude=sub2.latitude, longitude=sub2.longitude,
                method="nearest", tolerance=GRID_REGRID_TOLERANCE_DEG,
            )
            cum2 = (sub2["tp"].cumsum(dim="step") + offset).transpose("step", "latitude", "longitude")
            cum2_vals = cum2.values
            lats2 = cum2.latitude.values
            lons2 = cum2.longitude.values
            lons2_norm = np.array([normalize_longitude(float(lon)) for lon in lons2])

            for step_idx, step_val in enumerate(cum2.step.values):
                step_hours = _step_hours_from_timedelta(step_val)
                if step_hours > MAX_STEP_HOURS:
                    # Corte en t+14 (roadmap.md §1): en corridas extendidas (Days:10-35) no
                    # hace falta bajar/aplanar los steps entre +14 y +35 dias, no se usan.
                    continue
                valid_dt = datetime.combine(run_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=step_hours)
                slice_2d = cum2_vals[step_idx]
                for i, lat in enumerate(lats2):
                    for j, lon_norm in enumerate(lons2_norm):
                        value = float(slice_2d[i, j])
                        if value != value:
                            continue
                        records.append({
                            "run_date": run_date.isoformat(),
                            "run_time": run_time_str,
                            "step_hours": int(step_hours),
                            "valid_datetime": valid_dt.isoformat(),
                            "valid_date": valid_dt.date().isoformat(),
                            "latitude": float(lat),
                            "longitude": float(lon_norm),
                            "tp_mm": value,
                            "member": member,
                            "tramo": tramo2_name,
                            "tipo": "gefs",
                            "source_api": source_api,
                            "extracted_at": extracted_at,
                        })

        return records
    finally:
        for ds in to_close:
            try:
                ds.close()
            except Exception:
                pass
        for p in raw_paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


__all__ = [
    "compute_download_area",
    "gefs_key",
    "gefs_url",
    "list_members",
    "download_file",
    "flatten_member_day",
    "write_json",
    "EARLIEST_GEFS_DATE",
    "LATEST_GEFS_DATE",
    "STANDARD_MEMBERS",
]
