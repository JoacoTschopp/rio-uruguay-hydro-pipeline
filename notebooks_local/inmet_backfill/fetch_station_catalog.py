"""Catalogo de estaciones automaticas INMET dentro de la cuenca del Rio Uruguay.

Descarga el catalogo nacional (apitempo.inmet.gov.br/estacoes/T, requiere User-Agent de
navegador o el servidor corta la conexion TLS -- ver docs/data_sources.md #9.3), lo filtra
al bounding box aproximado de la cuenca y resuelve la sub-cuenca real de cada estacion con
un join espacial (geopandas) contra SIG/subcuencas_modelo.geojson -- mismo metodo que la
Decision 024 uso para validar el inventario ANA de forma independiente.

Escribe estaciones_inmet_catalogo.json, que sync_to_databricks.py sube al Volume y que
DDL_Silver_Gold.ipynb usa para sembrar weather.silver.estacion_subcuenca (mismo patron que
el inventario ANA).

Uso:
    python fetch_station_catalog.py
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point

LOCAL_DIR = Path(__file__).parent
OUTPUT_FILE = LOCAL_DIR / "estaciones_inmet_catalogo.json"
SIG_FILE = LOCAL_DIR.parent.parent / "SIG" / "subcuencas_modelo.geojson"

CATALOG_URL = "https://apitempo.inmet.gov.br/estacoes/T"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Bounding box aproximado de la cuenca (docs/data_sources.md #9.3), usado solo para
# recortar el catalogo nacional antes del join espacial exacto.
BBOX_LAT = (-29.5, -26.5)
BBOX_LON = (-54.5, -49.5)


def fetch_catalog() -> list[dict]:
    response = requests.get(CATALOG_URL, headers={"User-Agent": BROWSER_USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.json()


def filter_bbox(stations: list[dict]) -> list[dict]:
    out = []
    for s in stations:
        try:
            lat = float(s["VL_LATITUDE"])
            lon = float(s["VL_LONGITUDE"])
        except (TypeError, ValueError):
            continue
        if BBOX_LAT[0] <= lat <= BBOX_LAT[1] and BBOX_LON[0] <= lon <= BBOX_LON[1]:
            out.append({**s, "_lat": lat, "_lon": lon})
    return out


def resolve_subcuenca(stations: list[dict]) -> list[dict]:
    subcuencas = gpd.read_file(SIG_FILE)
    points = gpd.GeoDataFrame(
        {"idx": range(len(stations))},
        geometry=[Point(s["_lon"], s["_lat"]) for s in stations],
        crs=subcuencas.crs,
    )
    joined = gpd.sjoin(points, subcuencas[["nombre", "geometry"]], how="left", predicate="within")
    joined = joined.drop_duplicates(subset="idx")
    nombre_by_idx = dict(zip(joined["idx"], joined["nombre"]))

    resolved = []
    for i, s in enumerate(stations):
        resolved.append({
            "codigo_estacao": s["CD_ESTACAO"],
            "nome": s["DC_NOME"],
            "estado": s["SG_ESTADO"],
            "lat": s["_lat"],
            "lon": s["_lon"],
            "altitude_m": s.get("VL_ALTITUDE"),
            "dt_inicio_operacao": s.get("DT_INICIO_OPERACAO"),
            "situacao": s.get("CD_SITUACAO"),
            "subcuenca_nombre": nombre_by_idx.get(i),
        })
    return resolved


def main() -> None:
    print(f"GET {CATALOG_URL}")
    catalog = fetch_catalog()
    print(f"{len(catalog)} estaciones automaticas a nivel nacional")

    in_bbox = filter_bbox(catalog)
    print(f"{len(in_bbox)} estaciones dentro del bounding box de la cuenca")

    resolved = resolve_subcuenca(in_bbox)
    valid_names = {"alta_frontera", "intermedia_paso_libres", "baja_salto_grande"}
    in_basin = [s for s in resolved if s["subcuenca_nombre"] in valid_names]
    print(f"{len(in_basin)} estaciones dentro de alguna de las 3 sub-cuencas (join espacial exacto)")
    for name in ("alta_frontera", "intermedia_paso_libres", "baja_salto_grande"):
        count = sum(1 for s in in_basin if s["subcuenca_nombre"] == name)
        print(f"  {name}: {count}")

    OUTPUT_FILE.write_text(json.dumps(in_basin, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {OUTPUT_FILE} ({len(in_basin)} estaciones)")


if __name__ == "__main__":
    main()
