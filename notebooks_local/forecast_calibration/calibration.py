"""Calibracion de precipitacion pronosticada GEFS Reforecast v12 (miembro `c00`) contra
TIGGE `cf` (ECMWF), por sub-cuenca y por horizonte, sobre los dias de solapamiento real
2006-10 -> 2019-12 (Decision 021, Fase 4 de `docs/roadmap.md`).

Contexto de diseno (no repetir en el codigo, ver `docs/decisions.md`):

- GEFS termina alrededor de 2019, TIGGE cubre 2006-10 -> hoy. El tramo 2000-2006 solo tiene
  GEFS; el tramo 2020->hoy solo tiene TIGGE. El solapamiento 2006-10->2019-12 es el UNICO
  tramo donde ambas fuentes pronostican la misma fecha, y es lo que se usa para calibrar
  (Decision 021).
- Solo se sincroniza el miembro de control `c00` de GEFS a Databricks (Decision 034) -- la
  comparacion correcta es GEFS `c00` vs TIGGE `cf`, ambos son el determinista/control de cada
  sistema (no hace falta pedir `pf`).
- `tp_mm` en ambas fuentes Bronze ya viene acumulado desde el inicio de la corrida (para GEFS,
  la acumulacion del incremento nativo por bloque de 3h/6h se hace en Landing, ver
  `notebooks_local/gefs_reforecast/common_gefs.py` y Decision 026/029) -- este modulo no
  vuelve a acumular nada, solo resta cumulativos en pasos de 24h para obtener el pronostico
  DIARIO de cada horizonte.
- Los `step_hours` de ambas fuentes caen en multiplos exactos de 24h para los horizontes que
  interesan (1..7 y 14, Decision 019): TIGGE publica en grilla de 6h (0,6,...,360), GEFS en
  grilla de 3h hasta el dia 10 y de 6h despues (verificado contra Bronze real, ver el reporte
  de la Decision 035) -- ambos incluyen exactamente los pasos 0,24,48,...,168,...,312,336. No
  hace falta interpolar entre pasos para llegar a un horizonte diario.
- La regla de negocio (agregacion por sub-cuenca, correccion de sesgo) vive en Silver/local,
  nunca en Landing/Bronze (Decision 011, repetida en R8/R9 de `gold_consolidation_contract.md`).
  Este modulo es puro pandas, sin dependencia de Spark, para poder testearlo offline (Fase 1
  goldexport establecio ese patron con `test_export_gold_dataset.py`).

Uso esperado (ver `run_calibration_check.py` para el pull de datos reales):

    tagged_gefs = tag_points(gefs_points_df)          # agrega subcuenca_nombre
    tagged_tigge = tag_points(tigge_points_df)        # agrega subcuenca_nombre (o ya viene tageado)
    gefs_daily = daily_horizon_precip(tagged_gefs, source='gefs_c00')
    tigge_daily = daily_horizon_precip(tagged_tigge, source='tigge_cf')
    gefs_agg = aggregate_by_subcuenca(gefs_daily)
    tigge_agg = aggregate_by_subcuenca(tigge_daily)
    bias = compute_bias_table(gefs_agg, tigge_agg)
    gefs_calibrated = apply_bias(gefs_agg, bias)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Los 8 horizontes de la Decision 019 (enmienda). No se materializan features de t+8..t+13:
# t+14 se define como la precipitacion pronosticada DEL dia 14 (incremento entre el
# cumulativo de step=312h y el de step=336h), no como el acumulado de toda la semana 2.
HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"
BUFFER_DEG = 0.15  # mismo buffer que ETL_Silver_ECMWF_CF.ipynb (~15km, medio ancho de celda 0.25 grados)
METRIC_CRS = 32721  # UTM 21S, igual que el resto del proyecto


def horizon_steps(horizon: int) -> tuple[int, int]:
    """Devuelve (step_prev_hours, step_target_hours) para el horizonte diario `horizon`.

    horizon=1..7: precipitacion del dia `horizon` = cumulativo(24*horizon) - cumulativo(24*(horizon-1)).
    horizon=14: precipitacion del dia 14 = cumulativo(336) - cumulativo(312) (no el acumulado
    de toda la segunda semana -- ver docstring del modulo).
    """
    if horizon not in HORIZONS:
        raise ValueError(f"horizon {horizon} no es uno de los definidos en la Decision 019: {HORIZONS}")
    return (horizon - 1) * 24, horizon * 24


def tag_points(
    pdf: pd.DataFrame,
    geojson_path: Path = GEOJSON_PATH,
    buffer_deg: float = BUFFER_DEG,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
) -> pd.DataFrame:
    """Etiqueta cada punto de grilla unico de `pdf` con subcuenca_id/subcuenca_nombre,
    mismo criterio (buffer + sjoin within) que `tag_points()` en
    `notebooks/04_Silver/ETL_Silver_ECMWF_CF.ipynb`. Puntos fuera de las 3 sub-cuencas
    (con buffer) quedan con subcuenca_nombre NaN y se descartan en `daily_horizon_precip`.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    sub = gpd.read_file(geojson_path)[["fid", "nombre", "geometry"]].rename(
        columns={"fid": "subcuenca_id", "nombre": "subcuenca_nombre"}
    )
    sub_buffered = sub.copy()
    sub_buffered["geometry"] = sub.to_crs(METRIC_CRS).buffer(buffer_deg * 111000).to_crs(4326)

    uniq = pdf[[lat_col, lon_col]].drop_duplicates()
    gdf_pts = gpd.GeoDataFrame(
        uniq, geometry=[Point(lo, la) for la, lo in zip(uniq[lat_col], uniq[lon_col])], crs=4326
    )
    joined = gpd.sjoin(gdf_pts, sub_buffered, how="left", predicate="within").drop_duplicates(
        subset=[lat_col, lon_col], keep="first"
    )
    tags = joined[[lat_col, lon_col, "subcuenca_id", "subcuenca_nombre"]]
    return pdf.merge(tags, on=[lat_col, lon_col], how="left")


def daily_horizon_precip(
    tagged_df: pd.DataFrame,
    point_cols: tuple[str, ...] = ("latitude", "longitude"),
    run_date_col: str = "run_date",
    step_col: str = "step_hours",
    value_col: str = "tp_mm",
) -> pd.DataFrame:
    """Convierte una serie de `tp_mm` acumulado-desde-el-inicio-de-la-corrida (long format,
    una fila por run_date x punto x step) en precipitacion DIARIA por horizonte
    (una fila por run_date x punto x horizonte, columna `precip_mm`).

    Requiere que existan en `tagged_df` los steps 0,24,48,...,168 y 312,336 (o al menos los
    necesarios para los horizontes presentes); si faltan, ese (run_date, punto, horizonte)
    sale del resultado (no se inventa un valor).
    """
    id_cols = list(point_cols) + ["subcuenca_id", "subcuenca_nombre"]
    pivot = tagged_df.pivot_table(
        index=[run_date_col] + id_cols, columns=step_col, values=value_col, aggfunc="first"
    )

    rows = []
    for horizon in HORIZONS:
        prev_step, target_step = horizon_steps(horizon)
        prev = 0.0 if prev_step == 0 else pivot.get(prev_step)
        target = pivot.get(target_step)
        if target is None:
            continue
        if prev_step != 0 and prev is None:
            continue
        precip = target - (prev if prev_step != 0 else 0.0)
        rows.append(
            precip.rename("precip_mm").reset_index().assign(horizon_days=horizon)
        )

    if not rows:
        return pd.DataFrame(columns=[run_date_col] + id_cols + ["horizon_days", "precip_mm"])

    out = pd.concat(rows, ignore_index=True)
    out = out.dropna(subset=["subcuenca_nombre"]).copy()
    # Un punto puede existir en el pivot para un step pero no para otro -- ej. GEFS: los
    # puntos de la grilla 0,25 grados (tramo Days:1-10) que no son subconjunto de la grilla
    # 0,5 grados (tramo Days:10-16/35) no tienen step=336, asi que su horizonte 14 da NaN.
    # Se descarta esa fila puntual (no ese punto entero: sigue aportando a los horizontes
    # 1..7) en vez de dejarla como NaN silencioso que despues infla `n_points` en
    # `aggregate_by_subcuenca` sin aportar al promedio.
    out = out.dropna(subset=["precip_mm"]).copy()
    # precipitacion nunca negativa: un cumulativo no monotono es un problema de datos, no una
    # lluvia negativa real -- se clampea a 0 y se deja documentado, no se descarta la fila.
    out["precip_mm"] = out["precip_mm"].clip(lower=0.0)
    return out[[run_date_col, "subcuenca_nombre", "horizon_days", "precip_mm"] + [c for c in id_cols if c not in ("subcuenca_id", "subcuenca_nombre")]]


def aggregate_by_subcuenca(
    daily_df: pd.DataFrame, run_date_col: str = "run_date"
) -> pd.DataFrame:
    """Agrega el pronostico diario por horizonte a un solo valor por (run_date, subcuenca,
    horizonte): media simple sobre los puntos de grilla dentro de la sub-cuenca (mismo
    criterio que el agregado de lluvia observada por estacion en R8, Decision 023 --
    promedio simple, sin ponderar por distancia ni por sub-region interna)."""
    return (
        daily_df.groupby([run_date_col, "subcuenca_nombre", "horizon_days"], as_index=False)
        .agg(precip_mm=("precip_mm", "mean"), n_points=("precip_mm", "size"))
    )


def compute_bias_table(
    gefs_agg: pd.DataFrame,
    tigge_agg: pd.DataFrame,
    method: str = "additive",
    run_date_col: str = "run_date",
    min_days: int = 1,
) -> pd.DataFrame:
    """Calcula el sesgo de GEFS c00 contra TIGGE cf por (subcuenca, horizonte), medido
    UNICAMENTE sobre los `run_date` donde ambas fuentes tienen dato real para ese
    (subcuenca, horizonte) -- nunca se fabrica un dia de solapamiento que no existe.

    method='additive' (default): bias_mm = media(tigge - gefs) sobre los dias de
    solapamiento. Elegido como metodo principal en vez de un factor multiplicativo porque
    la serie de precipitacion diaria agregada por sub-cuenca es fuertemente cero-inflada
    (dias sin lluvia pronosticada) y un cociente por dia queda indefinido o inestable
    exactamente en esos dias -- el sesgo aditivo no tiene ese problema, es estable con
    pocas muestras (que es la situacion real hoy, con el solapamiento todavia
    incompleto -- ver Decision 035) y es directamente interpretable en mm.

    method='multiplicative': factor = suma(tigge) / suma(gefs) sobre el solapamiento
    (cociente de sumas, no media de cocientes por dia, para no dividir por cero en dias
    secos). Se deja implementado para cuando el solapamiento completo (13 anios) este
    disponible y se pueda re-evaluar cual metodo generaliza mejor; no es el default.

    Devuelve una fila por (subcuenca, horizonte) con el sesgo, el tamano de muestra
    (`n_days`) y las medias de cada fuente, para que el consumidor pueda decidir si confiar
    en un sesgo estimado con muy pocos dias.
    """
    merged = gefs_agg.merge(
        tigge_agg,
        on=[run_date_col, "subcuenca_nombre", "horizon_days"],
        suffixes=("_gefs", "_tigge"),
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame(
            columns=["subcuenca_nombre", "horizon_days", "method", "bias_mm", "factor",
                     "n_days", "mean_gefs_mm", "mean_tigge_mm"]
        )

    def _agg(group: pd.DataFrame) -> pd.Series:
        n_days = group[run_date_col].nunique()
        mean_gefs = group["precip_mm_gefs"].mean()
        mean_tigge = group["precip_mm_tigge"].mean()
        bias_mm = (group["precip_mm_tigge"] - group["precip_mm_gefs"]).mean()
        sum_gefs = group["precip_mm_gefs"].sum()
        sum_tigge = group["precip_mm_tigge"].sum()
        factor = (sum_tigge / sum_gefs) if sum_gefs > 0 else np.nan
        return pd.Series(
            {
                "n_days": n_days,
                "mean_gefs_mm": mean_gefs,
                "mean_tigge_mm": mean_tigge,
                "bias_mm": bias_mm,
                "factor": factor,
            }
        )

    stats = merged.groupby(["subcuenca_nombre", "horizon_days"]).apply(_agg, include_groups=False).reset_index()
    stats = stats[stats["n_days"] >= min_days].copy()
    stats["method"] = method
    stats["bias_mm"] = stats["bias_mm"] if method == "additive" else stats["bias_mm"]
    return stats[["subcuenca_nombre", "horizon_days", "method", "bias_mm", "factor", "n_days", "mean_gefs_mm", "mean_tigge_mm"]]


def apply_bias(
    gefs_agg: pd.DataFrame,
    bias_table: pd.DataFrame,
    method: str = "additive",
    run_date_col: str = "run_date",
) -> pd.DataFrame:
    """Aplica el sesgo calculado por `compute_bias_table` a la serie completa de GEFS c00
    (no solo al solapamiento). Un (subcuenca, horizonte) sin fila en `bias_table` (nunca
    hubo un dia de solapamiento real para calibrarlo) queda con `bias_mm=0`/`factor=1` y
    `calibrado=False`, para que el consumidor pueda distinguir "corregido" de "sin
    evidencia para corregir" -- no se inventa un sesgo por interpolacion entre horizontes
    o sub-cuencas vecinas.
    """
    cols = ["subcuenca_nombre", "horizon_days", "bias_mm", "factor", "n_days"]
    bias_lookup = bias_table[bias_table["method"] == method][cols] if not bias_table.empty else pd.DataFrame(columns=cols)

    out = gefs_agg.merge(bias_lookup, on=["subcuenca_nombre", "horizon_days"], how="left")
    out["calibrado"] = out["bias_mm"].notna()
    out["bias_mm"] = out["bias_mm"].fillna(0.0)
    out["factor"] = out["factor"].fillna(1.0)

    if method == "additive":
        out["precip_calibrado_mm"] = (out["precip_mm"] + out["bias_mm"]).clip(lower=0.0)
    elif method == "multiplicative":
        out["precip_calibrado_mm"] = (out["precip_mm"] * out["factor"]).clip(lower=0.0)
    else:
        raise ValueError(f"method desconocido: {method}")

    return out.drop(columns=["bias_mm", "factor", "n_days"])
