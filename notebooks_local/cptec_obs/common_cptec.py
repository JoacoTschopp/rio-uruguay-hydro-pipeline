"""Funciones compartidas para el landing local de las observaciones en grilla de CPTEC/INPE:
MERGE (precipitacion diaria, satelite GPM-IMERG + pluviometros, 0,1 grado) y SAMeT
(temperatura diaria TMAX/TMED/TMIN, observaciones + ERA5 corregido por lapse rate, 0,05 grado).

Ver docs/data_sources.md §9.6 (MERGE) y §9.7 (SAMeT) y la Decision 033 en docs/decisions.md
antes de tocar este modulo: documentan el porque de cada decision de diseno de aca (ventana
12Z-12Z de MERGE, regeneracion posterior de ambos productos, Parquet en vez de JSON, recorte
al bounding box en Landing y asignacion a sub-cuenca en Silver).

Notas de diseno confirmadas empiricamente contra los servidores reales (2026-08-26):
- HTTP abierto, sin registro, con `Last-Modified` confiable: `ftp.cptec.inpe.br` sirve MERGE y
  SAMeT directo (a diferencia de los modelos NWP, que redirigen a `dataserver.cptec.inpe.br`).
- MERGE diario = acumulado 12Z(D-1) -> 12Z(D) (paper Rozante 2024 + verificado sumando los
  horarios: corr 0,95 contra la ventana 13Z(D-1)..12Z(D), 0,62 contra el dia calendario UTC).
  El GRIB2 trae DOS mensajes: el primero es la precipitacion (CPTEC lo etiqueta como
  `rdp`/"Precipitation from radar", categoria 15 parametro 5) y el segundo es NEST, la cantidad
  de pluviometros por punto de grilla (mal etiquetado como `prmsl`). Se identifican por orden,
  no por nombre.
- MERGE se publica ~02:40 UTC de D+1 (IMERG Late, 14 h de latencia tras 12Z) y se REGENERA
  una vez, en los primeros dias del mes siguiente (pluviometros completos). Ademas toda la base
  se reconstruyo el 2025-05-04/06 (V07B, `MERGE_NEW_1998_2024.tar.gz`). Por eso cada registro
  guarda `source_last_modified` y Bronze actualiza cuando llega una version mas nueva.
- SAMeT TMED/TMAX de D se publican ~03:05 UTC de D+1 y TMIN de D a las ~17:05 UTC del mismo D
  (preliminar: observaciones + pronostico); se REGENERAN ~7 dias despues con ERA5 (READ-ME
  oficial). Toda la base se regenero el 2022-06-01. Los NetCDF traen `tmed|tmax|tmin` y `nobs`
  (observaciones usadas por punto), fill -9.99e+08; los NaN dentro del bounding box son solo
  oceano (esquina SE), las tres sub-cuencas quedan 100% cubiertas.
- Grilla MERGE: 1001x924 puntos, lon 239,95..339,95 E (convencion 0-360), lat -60,05..32,25;
  grilla SAMeT: 1001x1381, lon -83..-33, lat -56..13. Ambas cubren la cuenca completa.
- El recorte se hace client-side al bounding box de las 3 sub-cuencas (mismo
  `compute_download_area()` que ECMWF/GEFS, con la grilla de cada producto): 5.244 puntos
  MERGE y 20.792 puntos SAMeT por dia. La asignacion punto -> sub-cuenca (poligono real) NO se
  hace aca: la resuelve Silver con `weather.silver.grid_subcuenca`, sembrada desde el JSON que
  genera build_grid_subcuenca.py (mismo criterio que `estacion_subcuenca`).
- Salida en Parquet (un archivo por producto y dia), no JSON: SAMeT son ~20.800 filas/dia x
  ~9.700 dias; en JSON aplanado eso pesa ~25 GB, en Parquet ~3 GB. Spark lo lee nativo.
"""

from __future__ import annotations

import importlib.util
import time
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
ECMWF_DIR = REPO_ROOT / "notebooks_local" / "ecmwf"
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"


def _load_common_ecmwf():
    # Carga por ruta exacta (importlib), sin tocar sys.path -- mismo motivo que common_gefs.py:
    # insertar ECMWF_DIR en sys.path hace que sync_to_databricks.py de ecmwf/ le gane al local.
    spec = importlib.util.spec_from_file_location("common_ecmwf_for_cptec", ECMWF_DIR / "common_ecmwf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_common_ecmwf = _load_common_ecmwf()
compute_download_area = _common_ecmwf.compute_download_area
normalize_longitude = _common_ecmwf.normalize_longitude

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MERGE_BASE_URL = "https://ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/DAILY"
SAMET_BASE_URL = "https://ftp.cptec.inpe.br/modelos/tempo/SAMeT/DAILY"
MERGE_FIRST_DATE = date(1998, 1, 2)  # primer archivo real del archivo (MERGE_CPTEC_19980102.grib2)
SAMET_FIRST_DATE = date(2000, 1, 1)
MERGE_GRID_DEG = 0.1
SAMET_GRID_DEG = 0.05
SAMET_VARS = ("TMED", "TMAX", "TMIN")
SAMET_FILL = -9.99e08
SOURCE_API_MERGE = "cptec_merge_gpm_daily"
SOURCE_API_SAMET = "cptec_samet_daily"
SOURCES = ("merge", "samet")


def merge_url(d: date) -> str:
    return f"{MERGE_BASE_URL}/{d:%Y}/{d:%m}/MERGE_CPTEC_{d:%Y%m%d}.grib2"


def samet_url(d: date, var: str) -> str:
    return f"{SAMET_BASE_URL}/{var}/{d:%Y}/{d:%m}/SAMeT_CPTEC_{var}_{d:%Y%m%d}.nc"


def parquet_name(source: str, d: date) -> str:
    """Nombre del Parquet por producto y dia. La fecha va en el nombre para que Bronze pueda
    filtrar la ventana incremental por nombre de archivo sin abrir los 10.000+ archivos."""
    return f"{source.upper()}_{d:%Y_%m_%d}.parquet"


def first_date(source: str) -> date:
    return MERGE_FIRST_DATE if source == "merge" else SAMET_FIRST_DATE


def grid_deg(source: str) -> float:
    return MERGE_GRID_DEG if source == "merge" else SAMET_GRID_DEG


def download_area(source: str) -> dict:
    """Bounding box de las 3 sub-cuencas redondeado a la grilla del producto, +1 celda de margen
    (mismo helper que ECMWF/GEFS, ver notebooks_local/ecmwf/common_ecmwf.py)."""
    return compute_download_area(GEOJSON_PATH, grid_deg=grid_deg(source), margin_cells=1)


# --- HTTP --------------------------------------------------------------------------------


class Fetched:
    __slots__ = ("url", "content", "last_modified")

    def __init__(self, url: str, content: bytes, last_modified: Optional[datetime]):
        self.url = url
        self.content = content
        self.last_modified = last_modified


def _parse_last_modified(headers) -> Optional[datetime]:
    raw = headers.get("Last-Modified")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def new_session():
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": BROWSER_USER_AGENT})
    return session


def fetch(session, url: str, max_retries: int = 4, timeout: int = 120) -> Optional[Fetched]:
    """GET completo en memoria (los archivos pesan 0,4-1,8 MB). None si 404 (el dia no existe
    en el archivo, no es error). Reintenta con backoff ante errores transitorios: el servidor
    de CPTEC devuelve 500/ECONNRESET esporadicos (visto en la investigacion del 2026-08-26)."""
    import requests

    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return Fetched(url, resp.content, _parse_last_modified(resp.headers))
        except (requests.exceptions.RequestException, OSError):
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return None


def head_last_modified(session, url: str, timeout: int = 60) -> Optional[datetime]:
    """Solo la cabecera, para decidir si un dia ya descargado fue regenerado por CPTEC."""
    resp = session.head(url, timeout=timeout, allow_redirects=True)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _parse_last_modified(resp.headers)


# --- Decodificacion -------------------------------------------------------------------------


class Grid2D:
    """Campo 2D con sus ejes: `lat` (1D, cualquier orden), `lon` (1D, normalizada a -180/180),
    `values` (lat x lon), `extra` (segundo campo de la misma grilla: NEST o nobs)."""

    __slots__ = ("lat", "lon", "values", "extra")

    def __init__(self, lat, lon, values, extra):
        self.lat = np.asarray(lat, dtype="float64")
        self.lon = np.asarray(lon, dtype="float64")
        self.values = np.asarray(values, dtype="float64")
        self.extra = None if extra is None else np.asarray(extra, dtype="float64")


def decode_merge_eccodes(content: bytes) -> Grid2D:
    """Decodifica el GRIB2 diario de MERGE con ecCodes (entorno local). Mensaje 1 =
    precipitacion (kg/m2 == mm), mensaje 2 = NEST (pluviometros por punto). Usa los arrays
    `latitudes`/`longitudes` que expone ecCodes por punto, asi no depende del scanning mode.

    En Databricks serverless ecCodes/cfgrib abortan el kernel (Decision 013); alla el notebook
    de landing usa otro decodificador (ver Daily_CPTEC_Obs.ipynb) que produce este mismo Grid2D."""
    import eccodes

    messages = []
    offset = 0
    while offset < len(content):
        gid = eccodes.codes_new_from_message(content[offset:])
        if gid is None:
            break
        try:
            total_length = eccodes.codes_get(gid, "totalLength")
            ni = eccodes.codes_get(gid, "Ni")
            nj = eccodes.codes_get(gid, "Nj")
            vals = np.asarray(eccodes.codes_get_values(gid), dtype="float64").reshape(nj, ni)
            # Los faltantes NO vienen por bitmap sino por "missing value management" del
            # empaquetado complejo (template 5.3): ecCodes los devuelve como `missingValue`
            # (9999). Confirmado con NEST: los puntos sin pluviometro son 9999, no 0 -- sin este
            # reemplazo todos los puntos quedaban con "pluviometro" (bug encontrado en el test).
            missing = eccodes.codes_get(gid, "missingValue")
            vals = np.where(vals == missing, np.nan, vals)
            lats = np.asarray(eccodes.codes_get_double_array(gid, "latitudes")).reshape(nj, ni)[:, 0]
            lons = np.asarray(eccodes.codes_get_double_array(gid, "longitudes")).reshape(nj, ni)[0, :]
            messages.append((lats, lons, vals))
        finally:
            eccodes.codes_release(gid)
        offset += int(total_length)

    if not messages:
        raise ValueError("GRIB2 de MERGE sin mensajes")
    lat, lon, prec = messages[0]
    nest = messages[1][2] if len(messages) > 1 else None
    lon = np.array([normalize_longitude(float(x)) for x in lon])
    return Grid2D(lat, lon, prec, nest)


def decode_samet_netcdf(content: bytes, var: str) -> Grid2D:
    """Decodifica un NetCDF diario de SAMeT (variable `tmed|tmax|tmin` + `nobs`) en memoria.
    netCDF4 acepta `memory=bytes`, no hace falta escribir a disco."""
    import netCDF4

    ds = netCDF4.Dataset("inmemory.nc", mode="r", memory=content)
    try:
        lat = np.asarray(ds.variables["lat"][:], dtype="float64")
        lon = np.asarray(ds.variables["lon"][:], dtype="float64")
        main = np.ma.filled(ds.variables[var.lower()][:].astype("float64"), np.nan)
        nobs = np.ma.filled(ds.variables["nobs"][:].astype("float64"), np.nan) if "nobs" in ds.variables else None
    finally:
        ds.close()
    main = np.squeeze(main)
    main = np.where(main <= SAMET_FILL * 0.5, np.nan, main)  # fill explicito ademas de la mascara
    if nobs is not None:
        nobs = np.squeeze(nobs)
        nobs = np.where(nobs <= SAMET_FILL * 0.5, np.nan, nobs)
    if main.shape != (len(lat), len(lon)):
        raise ValueError(f"SAMeT {var}: shape {main.shape} no coincide con lat/lon ({len(lat)}, {len(lon)})")
    return Grid2D(lat, lon, main, nobs)


# --- Recorte y aplanado (vectorizado) -----------------------------------------------------


def crop_indices(lat: np.ndarray, lon: np.ndarray, area: dict):
    ilat = np.where((lat >= area["south"] - 1e-6) & (lat <= area["north"] + 1e-6))[0]
    ilon = np.where((lon >= area["west"] - 1e-6) & (lon <= area["east"] + 1e-6))[0]
    if len(ilat) == 0 or len(ilon) == 0:
        raise ValueError(f"El recorte al area {area} no deja ningun punto de grilla")
    return ilat, ilon


def _round_coord(values: np.ndarray) -> np.ndarray:
    # Las coordenadas de CPTEC vienen con ruido de flotante (-52.99999999999999): se redondean a
    # 3 decimales para que la clave (fecha, latitude, longitude) del MERGE de Bronze y el join
    # contra grid_subcuenca sean estables.
    return np.round(values, 3)


def flatten_merge(fecha: date, grid: Grid2D, area: dict, source_file: str,
                  source_last_modified: Optional[datetime], extracted_at: datetime):
    """Tabla pyarrow con una fila por punto de grilla dentro del area. Columnas alineadas con
    `weather.bronze.merge_precip_grid` (ver DDL_CPTEC_Obs.ipynb)."""
    import pyarrow as pa

    ilat, ilon = crop_indices(grid.lat, grid.lon, area)
    sub = grid.values[np.ix_(ilat, ilon)]
    nest = grid.extra[np.ix_(ilat, ilon)] if grid.extra is not None else np.full(sub.shape, np.nan)
    lon2d, lat2d = np.meshgrid(_round_coord(grid.lon[ilon]), _round_coord(grid.lat[ilat]))
    keep = ~np.isnan(sub)
    n = int(keep.sum())
    nest_col = nest[keep]
    nest_int = np.where(np.isnan(nest_col), 0, nest_col).astype("int32")
    return pa.table({
        "fecha": pa.array([fecha] * n, type=pa.date32()),
        "latitude": pa.array(lat2d[keep], type=pa.float64()),
        "longitude": pa.array(lon2d[keep], type=pa.float64()),
        "prec_mm": pa.array(sub[keep], type=pa.float64()),
        "nest": pa.array(nest_int, type=pa.int32()),
        "source_file": pa.array([source_file] * n, type=pa.string()),
        "source_last_modified": pa.array([source_last_modified] * n, type=pa.timestamp("us", tz="UTC")),
        "source_api": pa.array([SOURCE_API_MERGE] * n, type=pa.string()),
        "extracted_at": pa.array([extracted_at] * n, type=pa.timestamp("us", tz="UTC")),
    })


def flatten_samet(fecha: date, grids: dict, area: dict, source_files: dict,
                  last_modified: dict, extracted_at: datetime):
    """Una fila por punto de grilla con las tres variables juntas (tmed/tmax/tmin + nobs de cada
    una). `grids` mapea `TMED|TMAX|TMIN` -> Grid2D o None si ese archivo no existe para el dia.
    Se descartan los puntos sin ninguna de las tres (oceano). Columnas alineadas con
    `weather.bronze.samet_temp_grid`."""
    import pyarrow as pa

    ref = next((g for g in grids.values() if g is not None), None)
    if ref is None:
        raise ValueError("SAMeT: ningun archivo disponible para el dia")
    for var, g in grids.items():
        if g is not None and (g.values.shape != ref.values.shape or not np.allclose(g.lat, ref.lat) or not np.allclose(g.lon, ref.lon)):
            raise ValueError(f"SAMeT {var}: grilla distinta a la de referencia")

    ilat, ilon = crop_indices(ref.lat, ref.lon, area)
    lon2d, lat2d = np.meshgrid(_round_coord(ref.lon[ilon]), _round_coord(ref.lat[ilat]))
    cols = {}
    nobs_cols = {}
    any_valid = np.zeros(lat2d.shape, dtype=bool)
    for var in SAMET_VARS:
        g = grids.get(var)
        if g is None:
            cols[var] = np.full(lat2d.shape, np.nan)
            nobs_cols[var] = np.full(lat2d.shape, np.nan)
            continue
        cols[var] = g.values[np.ix_(ilat, ilon)]
        nobs_cols[var] = g.extra[np.ix_(ilat, ilon)] if g.extra is not None else np.full(lat2d.shape, np.nan)
        any_valid |= ~np.isnan(cols[var])

    keep = any_valid
    n = int(keep.sum())
    present = [v for v in SAMET_VARS if grids.get(v) is not None]
    source_file = ",".join(source_files[v] for v in present)
    lm_values = [last_modified[v] for v in present if last_modified.get(v) is not None]
    lm = max(lm_values) if lm_values else None

    def temp_col(var):
        return pa.array(cols[var][keep], type=pa.float64())

    def nobs_col(var):
        arr = nobs_cols[var][keep]
        return pa.array(np.where(np.isnan(arr), 0, arr).astype("int32"), type=pa.int32())

    return pa.table({
        "fecha": pa.array([fecha] * n, type=pa.date32()),
        "latitude": pa.array(lat2d[keep], type=pa.float64()),
        "longitude": pa.array(lon2d[keep], type=pa.float64()),
        "tmed_c": temp_col("TMED"),
        "tmax_c": temp_col("TMAX"),
        "tmin_c": temp_col("TMIN"),
        "nobs_tmed": nobs_col("TMED"),
        "nobs_tmax": nobs_col("TMAX"),
        "nobs_tmin": nobs_col("TMIN"),
        "source_file": pa.array([source_file] * n, type=pa.string()),
        "source_last_modified": pa.array([lm] * n, type=pa.timestamp("us", tz="UTC")),
        "source_api": pa.array([SOURCE_API_SAMET] * n, type=pa.string()),
        "extracted_at": pa.array([extracted_at] * n, type=pa.timestamp("us", tz="UTC")),
    })


def write_parquet(table, out_path: Path) -> None:
    import pyarrow.parquet as pq

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(out_path)


# --- Procesamiento de un dia (usado por el backfill local) -------------------------------


def process_merge_day(session, d: date, area: dict, out_dir: Path) -> dict:
    fetched = fetch(session, merge_url(d))
    if fetched is None:
        return {"status": "not_found"}
    grid = decode_merge_eccodes(fetched.content)
    table = flatten_merge(d, grid, area, f"MERGE_CPTEC_{d:%Y%m%d}.grib2", fetched.last_modified,
                          datetime.now(timezone.utc))
    out = out_dir / parquet_name("merge", d)
    write_parquet(table, out)
    return {
        "status": "done",
        "rows": table.num_rows,
        "last_modified": fetched.last_modified.isoformat() if fetched.last_modified else None,
        "file": out.name,
    }


def process_samet_day(session, d: date, area: dict, out_dir: Path) -> dict:
    grids, files, lms = {}, {}, {}
    for var in SAMET_VARS:
        fetched = fetch(session, samet_url(d, var))
        if fetched is None:
            grids[var] = None
            continue
        grids[var] = decode_samet_netcdf(fetched.content, var)
        files[var] = f"SAMeT_CPTEC_{var}_{d:%Y%m%d}.nc"
        lms[var] = fetched.last_modified
    if all(g is None for g in grids.values()):
        return {"status": "not_found"}
    table = flatten_samet(d, grids, area, files, lms, datetime.now(timezone.utc))
    out = out_dir / parquet_name("samet", d)
    write_parquet(table, out)
    present = [v for v in SAMET_VARS if grids[v] is not None]
    lm_values = [lms[v] for v in present if lms.get(v) is not None]
    return {
        "status": "done" if len(present) == len(SAMET_VARS) else "partial",
        "rows": table.num_rows,
        "vars": present,
        "last_modified": max(lm_values).isoformat() if lm_values else None,
        "file": out.name,
    }


def process_day(source: str, d: date, area: dict, out_dir: Path, session=None) -> dict:
    session = session or new_session()
    if source == "merge":
        return process_merge_day(session, d, area, out_dir)
    if source == "samet":
        return process_samet_day(session, d, area, out_dir)
    raise ValueError(f"source desconocido: {source}")


__all__ = [
    "SOURCES", "SAMET_VARS", "MERGE_FIRST_DATE", "SAMET_FIRST_DATE", "GEOJSON_PATH",
    "merge_url", "samet_url", "parquet_name", "first_date", "grid_deg", "download_area",
    "new_session", "fetch", "head_last_modified",
    "Grid2D", "decode_merge_eccodes", "decode_samet_netcdf",
    "flatten_merge", "flatten_samet", "write_parquet",
    "process_merge_day", "process_samet_day", "process_day",
]
