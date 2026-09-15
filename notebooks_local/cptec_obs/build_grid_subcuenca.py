"""Genera grid_subcuenca.json: la asignacion de cada punto de grilla de MERGE (0,1 grado) y de
SAMeT (0,05 grado) dentro del bounding box de descarga a su sub-cuenca, por union espacial
(centro de celda dentro del poligono) contra SIG/subcuencas_modelo.geojson.

Es el equivalente en grilla de `weather.silver.estacion_subcuenca` (Decision 024): Landing baja
el bounding box completo (5.244 puntos MERGE, 20.792 SAMeT) y Silver decide que puntos entran a
cada sub-cuenca con este catalogo, en vez de recortar por poligono en Landing (Decision 011:
reglas de negocio en Silver). Los puntos fuera de las tres sub-cuencas no aparecen en el JSON.

Las coordenadas se toman de un archivo REAL de cada producto (no de constantes) y se redondean
igual que en common_cptec.flatten_* (3 decimales), para que el join (latitude, longitude) en
Silver sea exacto. DDL_CPTEC_Obs.ipynb siembra weather.silver.grid_subcuenca desde el JSON
subido al Volume (sync_to_databricks.py --catalogo).

Uso:
    python build_grid_subcuenca.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np

LOCAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LOCAL_DIR))
from common_cptec import (  # noqa: E402
    GEOJSON_PATH,
    crop_indices,
    decode_merge_eccodes,
    decode_samet_netcdf,
    download_area,
    fetch,
    merge_url,
    new_session,
    samet_url,
)

OUTPUT_FILE = LOCAL_DIR / "grid_subcuenca.json"
GRID_NAMES = {"merge": "merge_0p1", "samet": "samet_0p05"}


def _reference_grid(session, source: str, lookback_days: int = 10):
    """Baja un archivo reciente del producto para leer los ejes reales de la grilla."""
    for lag in range(2, 2 + lookback_days):
        d = date.today() - timedelta(days=lag)
        if source == "merge":
            fetched = fetch(session, merge_url(d))
            if fetched is not None:
                return decode_merge_eccodes(fetched.content)
        else:
            fetched = fetch(session, samet_url(d, "TMED"))
            if fetched is not None:
                return decode_samet_netcdf(fetched.content, "TMED")
    raise RuntimeError(f"No se pudo bajar ningun archivo reciente de {source} para leer la grilla")


def main() -> None:
    import geopandas as gpd
    from shapely import contains_xy

    gdf = gpd.read_file(GEOJSON_PATH)
    polys = {row["nombre"]: row.geometry for _, row in gdf.iterrows()}
    print(f"Sub-cuencas: {list(polys)}")

    session = new_session()
    records = []
    for source in ("merge", "samet"):
        grid = _reference_grid(session, source)
        area = download_area(source)
        ilat, ilon = crop_indices(grid.lat, grid.lon, area)
        lat = np.round(grid.lat[ilat], 3)
        lon = np.round(grid.lon[ilon], 3)
        lon2d, lat2d = np.meshgrid(lon, lat)
        assigned = np.full(lat2d.shape, None, dtype=object)
        for name, poly in polys.items():
            inside = contains_xy(poly, lon2d, lat2d)
            overlap = inside & (assigned != None)  # noqa: E711
            if overlap.any():
                print(f"  aviso: {int(overlap.sum())} puntos de {source} caen en mas de una sub-cuenca; se conserva la primera")
                inside &= assigned == None  # noqa: E711
            assigned[inside] = name
        counts = Counter(assigned[assigned != None])  # noqa: E711
        print(f"[{source}] area {area}: {lat2d.size} puntos en el bbox, asignados {sum(counts.values())}: {dict(counts)}")
        for i in range(lat2d.shape[0]):
            for j in range(lat2d.shape[1]):
                if assigned[i, j] is not None:
                    records.append({
                        "grilla": GRID_NAMES[source],
                        "latitude": float(lat2d[i, j]),
                        "longitude": float(lon2d[i, j]),
                        "subcuenca": assigned[i, j],
                    })

    OUTPUT_FILE.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    print(f"{len(records)} puntos escritos en {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
