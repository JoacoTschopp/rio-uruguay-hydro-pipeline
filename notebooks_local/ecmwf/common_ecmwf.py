"""Funciones compartidas para la ingesta de pronostico ECMWF (cf via cdsapi/tigge-forecasts,
fc via ecmwf.opendata). Pensado para correr igual en local (pruebas) y en Databricks
(solo cambian los paths /Volumes/... y el origen de credenciales).

Notas de diseno importantes (confirmadas empiricamente en esta sesion, no asumidas):
- cf (tigge-forecasts via cdsapi): la API SI respeta el parametro "area" server-side.
  Longitud devuelta en convencion 0-360. Unidad de "tp": kg/m**2 (equivalente a mm,
  NO metros - no requiere conversion).
- fc (ecmwf.opendata): la API IGNORA "area" (server-side no soportado, imprime un warning
  y devuelve la grilla global) - hay que recortar al bounding box del lado del cliente
  inmediatamente despues de descargar, antes de aplanar a JSON (si no, un solo dia
  generaria ~10 millones de registros). Longitud ya en -180/180. Unidad de "tp": metros
  (SI requiere conversion x1000 a mm).
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

GRID_DEG = 0.25


def _geojson_total_bounds(geojson_path: str | Path) -> tuple[float, float, float, float]:
    """Bounds (lon_min, lat_min, lon_max, lat_max) de un FeatureCollection en CRS84,
    leido a mano (sin geopandas): evita cargar GDAL/PROJ en el mismo proceso que cfgrib
    (eccodes) en Daily_ECMWF_FC, una dependencia nativa menos en un proceso ya sensible
    a conflictos de librerias (ver docs/decisions.md sobre el crash de cfgrib en si)."""
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    minx = miny = math.inf
    maxx = maxy = -math.inf

    def walk(coords):
        nonlocal minx, miny, maxx, maxy
        if isinstance(coords[0], (int, float)):
            x, y = coords[0], coords[1]
            minx, maxx = min(minx, x), max(maxx, x)
            miny, maxy = min(miny, y), max(maxy, y)
        else:
            for c in coords:
                walk(c)

    for feature in data["features"]:
        walk(feature["geometry"]["coordinates"])

    return minx, miny, maxx, maxy


def compute_download_area(geojson_path: str | Path, grid_deg: float = GRID_DEG, margin_cells: int = 1) -> dict:
    """Calcula el area minima (N/O/S/E) que cubre el geojson, redondeada a la grilla + margen.

    Evita bajar "todo el mundo": el area se deriva de los limites reales del
    geojson de las 3 sub-cuencas, no de un bbox fijo hardcodeado.
    """
    minx, miny, maxx, maxy = _geojson_total_bounds(geojson_path)
    margin = grid_deg * margin_cells

    north = math.ceil((maxy + margin) / grid_deg) * grid_deg
    south = math.floor((miny - margin) / grid_deg) * grid_deg
    west = math.floor((minx - margin) / grid_deg) * grid_deg
    east = math.ceil((maxx + margin) / grid_deg) * grid_deg

    return {"north": round(north, 4), "west": round(west, 4), "south": round(south, 4), "east": round(east, 4)}


def area_to_mars_string(area: dict) -> str:
    return f"{area['north']}/{area['west']}/{area['south']}/{area['east']}"


def area_to_cds_list(area: dict) -> list[float]:
    """cdsapi espera [N, O, S, E]."""
    return [area["north"], area["west"], area["south"], area["east"]]


def normalize_longitude(lon: float) -> float:
    """Convierte de convencion 0-360 (TIGGE/cdsapi) a -180/180 (resto del proyecto)."""
    return lon - 360 if lon > 180 else lon


def point_in_bbox(lat: float, lon: float, area: dict) -> bool:
    lon_norm = normalize_longitude(lon)
    return (area["south"] <= lat <= area["north"]) and (area["west"] <= lon_norm <= area["east"])


def raw_filename(tipo: str, run_date: date, run_time: str, ext: str) -> str:
    return f"ECMWF_{tipo.upper()}_{run_date:%Y_%m_%d}_t{run_time}.{ext}"


# Archivos ya subidos al Volume que se movieron fuera del disco principal para liberar espacio
# (Decision 042). La resumibilidad de TIGGE se apoya en la PRESENCIA del JSON en disco -- no hay
# archivo de estado como en GEFS -- asi que mover un JSON sin avisar aca hace que el orquestador
# lo crea pendiente y lo vuelva a pedir a ECDS. Cada entrada mapea el directorio de trabajo a su
# archivo externo; `already_landed` da por aterrizado el dia que aparezca en cualquiera de los dos.
# El sync sigue mirando SOLO el directorio de trabajo, asi que nada de lo archivado se re-sube.
ARCHIVE_DIRS: dict[Path, list[Path]] = {}


def register_archive_dir(json_dir: Path, archive_dir: Path) -> None:
    """Declara un directorio donde pueden estar los JSON movidos de `json_dir`.

    Admite VARIOS destinos por `json_dir` y se consultan todos. Esto no es un lujo: durante
    una migracion de archivo (W: -> D:, 2026-09-09) los archivos estan reales mitad en el
    origen y mitad en el destino. Si solo valiera el ultimo registrado, already_landed()
    devolveria False para todo lo todavia no movido y el backfill re-pediria a ECDS cientos
    de dias ya bajados -- el accidente que casi pasa en agosto (Decision 042). Registrando
    ambos, cualquier instante intermedio de la migracion es seguro."""
    clave = Path(json_dir).resolve()
    destino = Path(archive_dir)
    dirs = ARCHIVE_DIRS.setdefault(clave, [])
    if destino not in dirs:
        dirs.append(destino)


_CATALOGO_CACHE: dict[str, set] = {}


def _dias_en_catalogo(fuente: str) -> Optional[set]:
    """Dias cubiertos segun el catalogo (Decision 046), cacheados por proceso.

    Devuelve None si el catalogo no esta disponible; el caller entonces cae al chequeo
    directo sobre disco. Degradar asi es deliberado: que falte el indice tiene que costar
    lentitud, nunca una re-descarga."""
    if fuente in _CATALOGO_CACHE:
        return _CATALOGO_CACHE[fuente]
    db = Path(__file__).resolve().parents[1] / "catalogo.db"
    if not db.exists():
        return None
    try:
        import sqlite3

        cx = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        dias = {
            date.fromisoformat(r[0])
            for r in cx.execute(
                "SELECT fecha FROM archivos WHERE fuente=? AND (en_volumen=1 OR ubicacion<>'')",
                (fuente,),
            )
        }
        cx.close()
    except Exception:
        return None
    _CATALOGO_CACHE[fuente] = dias
    return dias


CATALOGO_FUENTE: dict[Path, str] = {}


def register_catalogo_fuente(json_dir: Path, fuente: str) -> None:
    """Asocia un directorio de landing con su nombre de fuente en el catalogo."""
    CATALOGO_FUENTE[Path(json_dir).resolve()] = fuente


def already_landed(tipo: str, run_date: date, run_time: str, json_dir: Path) -> bool:
    nombre = raw_filename(tipo, run_date, run_time, "json")
    # 1) disco local: barato (C:) y siempre al dia, incluso para lo recien descargado.
    if (json_dir / nombre).exists():
        return True
    # 2) catalogo: evita golpear el disco externo por USB dia por dia. Solo se consulta para
    #    lo que ya no esta en local, que es justamente lo archivado.
    fuente = CATALOGO_FUENTE.get(Path(json_dir).resolve())
    if fuente:
        dias = _dias_en_catalogo(fuente)
        if dias is not None:
            return run_date in dias
    # 3) sin catalogo, el comportamiento de siempre.
    return any((d / nombre).exists() for d in ARCHIVE_DIRS.get(Path(json_dir).resolve(), []))


def flatten_forecast(
    ds,
    run_date: date,
    run_time: str,
    tipo: str,
    source_api: str,
    unit_to_mm_factor: float,
    area: Optional[dict] = None,
    number: Optional[int] = None,
) -> list[dict]:
    """Aplana un xarray.Dataset (netcdf de cdsapi o grib2 de opendata) a records planos.

    - unit_to_mm_factor: 1.0 para cf (ya viene en kg/m2 == mm), 1000.0 para fc (viene en m).
    - area: si se pasa, filtra localmente a ese bbox (necesario para fc, que la API
      no recorta server-side). Para cf no hace falta (la API ya recorto).
    """
    tp = ds["tp"]
    lats = ds["latitude"].values
    lons = ds["longitude"].values

    if "step" in tp.dims:
        steps = ds["step"].values
    else:
        steps = [tp["step"].values] if "step" in tp.coords else [None]
        tp = tp.expand_dims("step") if "step" not in tp.dims else tp

    extracted_at = datetime.now(timezone.utc).isoformat()
    records: list[dict] = []

    for step_idx, step_val in enumerate(steps):
        step_hours = _step_to_hours(step_val)
        valid_dt = _compute_valid_datetime(run_date, run_time, step_hours)
        slice_2d = tp.isel(step=step_idx).values if "step" in tp.dims else tp.values

        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                lon_norm = normalize_longitude(float(lon))
                if area is not None and not point_in_bbox(float(lat), lon_norm, area):
                    continue
                value = slice_2d[i, j]
                if value is None:
                    continue
                value_f = float(value)
                if math.isnan(value_f):
                    continue
                record = {
                    "run_date": run_date.isoformat(),
                    "run_time": run_time,
                    "step_hours": int(step_hours),
                    "valid_datetime": valid_dt.isoformat(),
                    "valid_date": valid_dt.date().isoformat(),
                    "latitude": float(lat),
                    "longitude": lon_norm,
                    "tp_mm": value_f * unit_to_mm_factor,
                    "tipo": tipo,
                    "source_api": source_api,
                    "extracted_at": extracted_at,
                }
                if number is not None:
                    record["number"] = number
                records.append(record)

    return records


def flatten_ensemble_forecast(
    ds,
    run_date: date,
    run_time: str,
    tipo: str,
    source_api: str,
    unit_to_mm_factor: float,
    area: Optional[dict] = None,
) -> list[dict]:
    """Igual que flatten_forecast, pero para datasets con una dimension real 'number'
    (varios miembros del ensemble, ej. pf) en vez de un unico valor pasado por parametro.
    Genera un record por combinacion (number, step, lat, lon).
    """
    tp = ds["tp"]
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    numbers = ds["number"].values

    if "step" in tp.dims:
        steps = ds["step"].values
    else:
        steps = [tp["step"].values] if "step" in tp.coords else [None]
        tp = tp.expand_dims("step") if "step" not in tp.dims else tp

    extracted_at = datetime.now(timezone.utc).isoformat()
    records: list[dict] = []

    for number_idx, number_val in enumerate(numbers):
        tp_member = tp.isel(number=number_idx)

        for step_idx, step_val in enumerate(steps):
            step_hours = _step_to_hours(step_val)
            valid_dt = _compute_valid_datetime(run_date, run_time, step_hours)
            slice_2d = tp_member.isel(step=step_idx).values if "step" in tp_member.dims else tp_member.values

            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    lon_norm = normalize_longitude(float(lon))
                    if area is not None and not point_in_bbox(float(lat), lon_norm, area):
                        continue
                    value = slice_2d[i, j]
                    if value is None:
                        continue
                    value_f = float(value)
                    if math.isnan(value_f):
                        continue
                    records.append({
                        "run_date": run_date.isoformat(),
                        "run_time": run_time,
                        "step_hours": int(step_hours),
                        "valid_datetime": valid_dt.isoformat(),
                        "valid_date": valid_dt.date().isoformat(),
                        "latitude": float(lat),
                        "longitude": lon_norm,
                        "number": int(number_val),
                        "tp_mm": value_f * unit_to_mm_factor,
                        "tipo": tipo,
                        "source_api": source_api,
                        "extracted_at": extracted_at,
                    })

    return records


def _step_to_hours(step_val) -> int:
    if step_val is None:
        return 0
    # netcdf (cdsapi): step viene en horas (float). grib (opendata): step viene como timedelta64.
    try:
        import numpy as np

        if isinstance(step_val, np.timedelta64):
            return int(step_val / np.timedelta64(1, "h"))
    except ImportError:
        pass
    return int(step_val)


def _compute_valid_datetime(run_date: date, run_time: str, step_hours: int) -> datetime:
    from datetime import timedelta

    run_dt = datetime.combine(run_date, datetime.strptime(run_time, "%H").time(), tzinfo=timezone.utc)
    return run_dt + timedelta(hours=step_hours)


def write_json(records: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


# --- Reconstruccion historica (requests multi-fecha en un solo lote) ---------------
#
# Un unico request de cdsapi puede pedir un rango de fechas ("date": "YYYY-MM-DD/to/YYYY-MM-DD")
# en vez de un solo dia. Esto es clave para no generar miles de requests individuales
# (uno por dia) contra la cola de TIGGE/ECDS: se agrupa en lotes (1 anio para cf, 1 mes
# para pf, ver historic_cf_tigge.py / historic_pf_tigge.py) y se aplana por lote, pero
# se sigue escribiendo un JSON por dia (mismo nombre que generaria el job diario), para
# que Bronze (que lee toda la carpeta json/ sin cambios) no note la diferencia.


def date_range_str(start: date, end: date) -> str:
    """Sintaxis de rango de fechas del portal ECMWF Data Stores (ecds.ecmwf.int): "start/end",
    sin "/to/" (esa era la sintaxis MARS clasica, la API nueva la rechaza con 400 Bad Request:
    'Date ranges must be of the form "start_date/end_date"')."""
    return f"{start.isoformat()}/{end.isoformat()}"


def _reftime_dim_name(tp) -> Optional[str]:
    """Encuentra la dimension de fecha/hora base (distinta de step/number/lat/lon) en un
    request multi-fecha. cdsapi/xarray suele nombrarla 'time'; se busca de forma generica
    por si cambia, en vez de asumir el nombre."""
    known = {"step", "number", "latitude", "longitude"}
    for d in tp.dims:
        if d not in known:
            return d
    return None


def _reftime_to_run_date_time(value) -> tuple[date, str]:
    """Convierte un valor datetime64 (dimension de fecha base) a (run_date, run_time 'HH')."""
    import numpy as np

    ts = value if not isinstance(value, np.datetime64) else value.astype("datetime64[s]").item()
    return ts.date(), f"{ts.hour:02d}"


def flatten_forecast_batch(
    ds,
    tipo: str,
    source_api: str,
    unit_to_mm_factor: float,
    area: Optional[dict] = None,
) -> dict[str, list[dict]]:
    """Igual que flatten_forecast, pero para un dataset que cubre varias fechas base
    (un lote historico). Devuelve {run_date.isoformat(): records} para poder escribir
    un JSON por dia, igual que el job diario."""
    tp = ds["tp"]
    lats = ds["latitude"].values
    lons = ds["longitude"].values

    reftime_dim = _reftime_dim_name(tp)
    if reftime_dim is None:
        # Un solo dia en el lote: mismo comportamiento que flatten_forecast.
        run_date, run_time = date.today(), "00"
        if "time" in ds.coords:
            run_date, run_time = _reftime_to_run_date_time(ds["time"].values)
        records = flatten_forecast(ds, run_date, run_time, tipo, source_api, unit_to_mm_factor, area=area)
        return {run_date.isoformat(): records}

    reftimes = ds[reftime_dim].values
    steps = ds["step"].values if "step" in tp.dims else [None]

    out: dict[str, list[dict]] = {}
    for rt_idx, rt_val in enumerate(reftimes):
        run_date, run_time = _reftime_to_run_date_time(rt_val)
        tp_day = tp.isel({reftime_dim: rt_idx})
        extracted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []
        for step_idx, step_val in enumerate(steps):
            step_hours = _step_to_hours(step_val)
            valid_dt = _compute_valid_datetime(run_date, run_time, step_hours)
            slice_2d = tp_day.isel(step=step_idx).values if "step" in tp_day.dims else tp_day.values
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    lon_norm = normalize_longitude(float(lon))
                    if area is not None and not point_in_bbox(float(lat), lon_norm, area):
                        continue
                    value = slice_2d[i, j]
                    if value is None:
                        continue
                    value_f = float(value)
                    if math.isnan(value_f):
                        continue
                    records.append({
                        "run_date": run_date.isoformat(),
                        "run_time": run_time,
                        "step_hours": int(step_hours),
                        "valid_datetime": valid_dt.isoformat(),
                        "valid_date": valid_dt.date().isoformat(),
                        "latitude": float(lat),
                        "longitude": lon_norm,
                        "tp_mm": value_f * unit_to_mm_factor,
                        "tipo": tipo,
                        "source_api": source_api,
                        "extracted_at": extracted_at,
                    })
        out[run_date.isoformat()] = records
    return out


def flatten_ensemble_forecast_batch(
    ds,
    tipo: str,
    source_api: str,
    unit_to_mm_factor: float,
    area: Optional[dict] = None,
) -> dict[str, list[dict]]:
    """Igual que flatten_forecast_batch, pero recorriendo tambien la dimension real
    'number' (miembros del ensemble), para lotes historicos de pf."""
    tp = ds["tp"]
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    numbers = ds["number"].values

    reftime_dim = _reftime_dim_name(tp)
    if reftime_dim is None:
        run_date, run_time = date.today(), "00"
        if "time" in ds.coords:
            run_date, run_time = _reftime_to_run_date_time(ds["time"].values)
        records = flatten_ensemble_forecast(ds, run_date, run_time, tipo, source_api, unit_to_mm_factor, area=area)
        return {run_date.isoformat(): records}

    reftimes = ds[reftime_dim].values
    steps = ds["step"].values if "step" in tp.dims else [None]

    out: dict[str, list[dict]] = {}
    for rt_idx, rt_val in enumerate(reftimes):
        run_date, run_time = _reftime_to_run_date_time(rt_val)
        tp_day = tp.isel({reftime_dim: rt_idx})
        extracted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []
        for number_idx, number_val in enumerate(numbers):
            tp_member = tp_day.isel(number=number_idx)
            for step_idx, step_val in enumerate(steps):
                step_hours = _step_to_hours(step_val)
                valid_dt = _compute_valid_datetime(run_date, run_time, step_hours)
                slice_2d = tp_member.isel(step=step_idx).values if "step" in tp_member.dims else tp_member.values
                for i, lat in enumerate(lats):
                    for j, lon in enumerate(lons):
                        lon_norm = normalize_longitude(float(lon))
                        if area is not None and not point_in_bbox(float(lat), lon_norm, area):
                            continue
                        value = slice_2d[i, j]
                        if value is None:
                            continue
                        value_f = float(value)
                        if math.isnan(value_f):
                            continue
                        records.append({
                            "run_date": run_date.isoformat(),
                            "run_time": run_time,
                            "step_hours": int(step_hours),
                            "valid_datetime": valid_dt.isoformat(),
                            "valid_date": valid_dt.date().isoformat(),
                            "latitude": float(lat),
                            "longitude": lon_norm,
                            "number": int(number_val),
                            "tp_mm": value_f * unit_to_mm_factor,
                            "tipo": tipo,
                            "source_api": source_api,
                            "extracted_at": extracted_at,
                        })
        out[run_date.isoformat()] = records
    return out


def iter_ensemble_forecast_batch_by_day(
    ds,
    tipo: str,
    source_api: str,
    unit_to_mm_factor: float,
    area: Optional[dict] = None,
):
    """Igual que flatten_ensemble_forecast_batch, pero como generador que devuelve un dia
    (reftime) por vez en vez de acumular el lote completo en un dict antes de devolver nada.

    Necesario para pf: un lote de 31 dias x 50 miembros x 16 steps x ~975 puntos de grilla
    genera ~24M records simultaneos si se materializan todos antes de escribir el primer
    JSON (~15-20 GB de objetos dict de Python) y tira OOM en el compute serverless. Escribiendo
    y descartando cada dia apenas se genera, el pico de memoria queda acotado a un dia
    (~780.000 records), sin cambiar el request a la API ni el archivo de salida."""
    tp = ds["tp"]
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    numbers = ds["number"].values

    reftime_dim = _reftime_dim_name(tp)
    if reftime_dim is None:
        run_date, run_time = date.today(), "00"
        if "time" in ds.coords:
            run_date, run_time = _reftime_to_run_date_time(ds["time"].values)
        yield run_date.isoformat(), flatten_ensemble_forecast(
            ds, run_date, run_time, tipo, source_api, unit_to_mm_factor, area=area
        )
        return

    reftimes = ds[reftime_dim].values
    steps = ds["step"].values if "step" in tp.dims else [None]

    for rt_idx, rt_val in enumerate(reftimes):
        run_date, run_time = _reftime_to_run_date_time(rt_val)
        tp_day = tp.isel({reftime_dim: rt_idx})
        extracted_at = datetime.now(timezone.utc).isoformat()
        records: list[dict] = []
        for number_idx, number_val in enumerate(numbers):
            tp_member = tp_day.isel(number=number_idx)
            for step_idx, step_val in enumerate(steps):
                step_hours = _step_to_hours(step_val)
                valid_dt = _compute_valid_datetime(run_date, run_time, step_hours)
                slice_2d = tp_member.isel(step=step_idx).values if "step" in tp_member.dims else tp_member.values
                for i, lat in enumerate(lats):
                    for j, lon in enumerate(lons):
                        lon_norm = normalize_longitude(float(lon))
                        if area is not None and not point_in_bbox(float(lat), lon_norm, area):
                            continue
                        value = slice_2d[i, j]
                        if value is None:
                            continue
                        value_f = float(value)
                        if math.isnan(value_f):
                            continue
                        records.append({
                            "run_date": run_date.isoformat(),
                            "run_time": run_time,
                            "step_hours": int(step_hours),
                            "valid_datetime": valid_dt.isoformat(),
                            "valid_date": valid_dt.date().isoformat(),
                            "latitude": float(lat),
                            "longitude": lon_norm,
                            "number": int(number_val),
                            "tp_mm": value_f * unit_to_mm_factor,
                            "tipo": tipo,
                            "source_api": source_api,
                            "extracted_at": extracted_at,
                        })
        yield run_date.isoformat(), records


def iter_batches_backward(earliest: date, latest: date, step_months: int):
    """OBSOLETA -- usar iter_batches_calendar_backward. Se conserva solo para no romper
    codigo viejo que la importe.

    Genera lotes [start, end] desde el mas reciente hacia el mas antiguo, de tamanio
    step_months, anclando TODAS las fronteras en 'latest'. Ese anclaje es el defecto que
    documenta la Decision 044: como 'latest' se deriva de date.today(), la grilla entera
    se corre un dia por dia, el lote del borde deja de estar completo y se vuelve a pedir
    un mes entero para ganar un solo dia."""
    from dateutil.relativedelta import relativedelta

    batches = []
    end = latest
    while end >= earliest:
        start = end - relativedelta(months=step_months) + timedelta(days=1)
        if start < earliest:
            start = earliest
        batches.append((start, end))
        end = start - timedelta(days=1)
    return batches


def period_start(d: date, step_months: int) -> date:
    """Primer dia del periodo de step_months meses que contiene a 'd', contando periodos
    desde enero del anio 0. Con step_months=1 da el primero del mes; con 12, el 1 de enero."""
    idx = ((d.year * 12 + (d.month - 1)) // step_months) * step_months
    return date(idx // 12, idx % 12 + 1, 1)


def iter_batches_calendar_backward(earliest: date, latest: date, step_months: int):
    """Genera lotes [start, end] del mas reciente al mas antiguo, alineados a fronteras de
    calendario (mes con step_months=1, anio con step_months=12), acotados a [earliest, latest].

    A diferencia de iter_batches_backward, la grilla NO depende de 'latest': correr 'latest'
    un dia solo agranda el ultimo lote, no mueve ninguna frontera. Eso es lo que impide que
    un backfill que corre todos los dias vuelva a pedir un mes entero cada vez que cambia la
    fecha del sistema (Decision 044)."""
    from dateutil.relativedelta import relativedelta

    batches = []
    start = period_start(latest, step_months)
    while True:
        end = min(latest, start + relativedelta(months=step_months) - timedelta(days=1))
        batches.append((max(start, earliest), end))
        if start <= earliest:
            break
        start -= relativedelta(months=step_months)
    return batches


def days_in_range(start: date, end: date):
    n = (end - start).days
    for i in range(n + 1):
        yield start + timedelta(days=i)


def retrieve_bisecting(retrieve, raw_path_for, start: date, end: date, min_days: int = 1):
    """Pide [start, end]; si el request falla, parte el tramo al medio y reintenta cada mitad,
    hasta granularidad `min_days`. Devuelve (piezas_ok, tramos_fallidos), donde piezas_ok son
    tuplas (s, e, path) ya descargadas.

    Por que existe (Decision 049): ECDS rechaza con 400 algunos rangos por dias puntuales que
    no puede servir, y con el lote entero como unidad un solo dia malo tiraba abajo los ~120
    dias buenos que lo rodeaban -- y como la grilla de la Decision 044 es estable, el mismo
    request fallaba identico en cada corrida, en loop y sin avanzar nunca.

    Bisecar es autolimitado (log2 del tramo) y conserva el dato bueno. Ademas distingue solo
    con el resultado los dos tipos de falla: si NINGUNA pieza baja, el problema es global
    (cola rate-limited, credenciales, red) y el caller debe cortar como siempre (Decision 030);
    si bajo aunque sea una, el bloqueo no era global y los tramos fallidos son dias que la
    fuente no entrega."""
    pendientes = [(start, end)]
    ok: list[tuple[date, date, Path]] = []
    fallidos: list[tuple[date, date]] = []
    while pendientes:
        s, e = pendientes.pop(0)
        destino = raw_path_for(s, e)
        if retrieve(s, e, destino):
            ok.append((s, e, destino))
            continue
        n = (e - s).days + 1
        if n <= min_days:
            fallidos.append((s, e))
            continue
        mitad = s + timedelta(days=n // 2 - 1)
        print(f"  tramo {s.isoformat()}..{e.isoformat()} fallo, se parte en {n // 2} + {n - n // 2} dias")
        pendientes.insert(0, (mitad + timedelta(days=1), e))
        pendientes.insert(0, (s, mitad))
    return ok, fallidos


def batch_fully_landed(tipo: str, start: date, end: date, run_time: str, json_dir: Path) -> bool:
    return all(already_landed(tipo, d, run_time, json_dir) for d in days_in_range(start, end))


UNAVAILABLE_DAYS_PATH = Path(__file__).resolve().parent / "tigge_unavailable_days.json"


def load_unavailable_days(tipo: str, path: Path = UNAVAILABLE_DAYS_PATH) -> set:
    """Dias que la fuente demostro no poder servir: un request de UN SOLO dia fallo.

    No es una preferencia sobre el dataset, es un hecho sobre el origen -- y queda registrado
    en un archivo auditable en vez de hardcodeado, con la fecha en que se comprobo. Sin esto,
    un dia que ECDS no entrega bloquea su lote para siempre: el bisect lo aisla, el lote queda
    sin piezas, el caller corta la fuente y la corrida siguiente repite todo igual
    (Decision 049)."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {date.fromisoformat(d) for d in data.get(tipo, {})}


def record_unavailable_day(tipo: str, day: date, reason: str, path: Path = UNAVAILABLE_DAYS_PATH) -> None:
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.setdefault(tipo, {})[day.isoformat()] = {
        "comprobado": datetime.now(timezone.utc).isoformat(),
        "motivo": reason[:300],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def missing_span(tipo: str, start: date, end: date, run_time: str, json_dir: Path, ignorar: set | None = None):
    """Devuelve (primer_faltante, ultimo_faltante) dentro del lote, o None si esta completo.

    Pedirle a la API solo ese tramo en vez del lote entero es la otra mitad del arreglo de
    la Decision 044: batch_fully_landed es todo-o-nada, asi que un lote al que le falta un
    solo dia se re-descargaba completo. El tramo es contiguo por construccion (min..max);
    si los faltantes estuvieran salteados se re-baja algun dia ya presente, acotado siempre
    al tamanio del lote."""
    ignorar = ignorar or set()
    faltantes = [d for d in days_in_range(start, end)
                 if d not in ignorar and not already_landed(tipo, d, run_time, json_dir)]
    if not faltantes:
        return None
    return faltantes[0], faltantes[-1]
