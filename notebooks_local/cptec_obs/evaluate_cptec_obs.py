"""Evaluacion local del archivo MERGE/SAMeT descargado por download_cptec_obs.py: cobertura
temporal, densidad de observaciones dentro de la cuenca, series diarias por sub-cuenca y
comparacion contra los agregados por estacion (ANA/INMET) del snapshot local de Gold.

Produce:
  * evaluation/merge_subcuenca_daily.csv y evaluation/samet_subcuenca_daily.csv -- la misma
    agregacion que hace ETL_Silver_CPTEC_Grid_Daily.ipynb (media areal por sub-cuenca), calculada
    en local para poder evaluar antes de subir nada a Databricks.
  * docs/cptec_obs_evaluation.md -- el reporte versionado con los numeros (base de la Decision 033
    y del capitulo de datos de la tesis).

La asignacion punto -> sub-cuenca sale de grid_subcuenca.json (build_grid_subcuenca.py), igual
que en Silver. El snapshot de Gold es el cache de notebooks_local/gold_export/ (se baja con
export_gold_dataset.py --refresh); si no existe, la comparacion se omite.

Uso:
    python evaluate_cptec_obs.py [--skip-aggregate]   # --skip-aggregate reusa los CSV ya generados
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

LOCAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = LOCAL_DIR.parents[1]
OUTPUT_DIR = LOCAL_DIR / "output_parquet"
EVAL_DIR = LOCAL_DIR / "evaluation"
CATALOGO_FILE = LOCAL_DIR / "grid_subcuenca.json"
GOLD_CACHE = REPO_ROOT / "notebooks_local" / "gold_export" / "cache" / "training_dataset_v0.parquet"
REPORT_FILE = REPO_ROOT / "docs" / "cptec_obs_evaluation.md"

sys.path.insert(0, str(LOCAL_DIR))
from common_cptec import MERGE_FIRST_DATE, SAMET_FIRST_DATE  # noqa: E402

GRID_NAMES = {"merge": "merge_0p1", "samet": "samet_0p05"}
SUBCUENCAS = ["alta_frontera", "intermedia_paso_libres", "baja_salto_grande"]


def load_grid(source: str) -> pd.DataFrame:
    records = json.loads(CATALOGO_FILE.read_text(encoding="utf-8"))
    df = pd.DataFrame([r for r in records if r["grilla"] == GRID_NAMES[source]])
    return df[["latitude", "longitude", "subcuenca"]]


def aggregate_source(source: str) -> pd.DataFrame:
    """Lee archivo por archivo (200 M filas de SAMeT no entran en memoria de una) y agrega
    por sub-cuenca con la misma regla que Silver: media areal de los puntos dentro del poligono."""
    import pyarrow.parquet as pq

    grid = load_grid(source)
    expected = grid.groupby("subcuenca").size().rename("puntos_esperados")
    files = sorted((OUTPUT_DIR / source).glob(f"{source.upper()}_*.parquet"))
    if not files:
        raise RuntimeError(f"No hay Parquet en {OUTPUT_DIR / source}; corre download_cptec_obs.py primero")
    print(f"[{source}] agregando {len(files)} dias...")
    rows = []
    for i, f in enumerate(files, 1):
        pdf = pq.read_table(f).to_pandas()
        pdf = pdf.merge(grid, on=["latitude", "longitude"], how="inner")
        if pdf.empty:
            continue
        lm = pdf["source_last_modified"].iloc[0]
        fecha = pdf["fecha"].iloc[0]
        if source == "merge":
            g = pdf.groupby("subcuenca").agg(
                prec_media_mm=("prec_mm", "mean"), prec_max_mm=("prec_mm", "max"),
                puntos=("prec_mm", "count"), puntos_con_pluviometro=("nest", lambda s: int((s > 0).sum())),
                pluviometros=("nest", "sum"),
            )
        else:
            g = pdf.groupby("subcuenca").agg(
                temp_media_c=("tmed_c", "mean"), temp_max_c=("tmax_c", "mean"), temp_min_c=("tmin_c", "mean"),
                temp_max_abs_c=("tmax_c", "max"), temp_min_abs_c=("tmin_c", "min"),
                puntos=("tmed_c", "count"), nobs_tmed=("nobs_tmed", "sum"), nobs_tmax=("nobs_tmax", "sum"), nobs_tmin=("nobs_tmin", "sum"),
            )
        g = g.join(expected)
        g["cobertura_pct"] = g["puntos"] / g["puntos_esperados"]
        g["fecha"] = pd.Timestamp(fecha)
        g["source_last_modified"] = lm
        rows.append(g.reset_index())
        if i % 1000 == 0:
            print(f"  {i}/{len(files)}")
    out = pd.concat(rows, ignore_index=True)
    EVAL_DIR.mkdir(exist_ok=True)
    out.to_csv(EVAL_DIR / f"{source}_subcuenca_daily.csv", index=False)
    print(f"[{source}] {len(out)} filas (fecha x sub-cuenca) -> {EVAL_DIR / f'{source}_subcuenca_daily.csv'}")
    return out


def coverage_table(df: pd.DataFrame, first: date, label: str) -> str:
    alta = df[df["subcuenca"] == "alta_frontera"].set_index("fecha").sort_index()
    last = alta.index.max().date()
    lines = [f"| Año | Días esperados | Días con dato ({label}) | Faltantes |", "| --- | --- | --- | --- |"]
    total_missing = []
    for year in range(first.year, last.year + 1):
        y0 = max(date(year, 1, 1), first)
        y1 = min(date(year, 12, 31), last)
        expected = (y1 - y0).days + 1
        present = alta.loc[str(year)].shape[0] if str(year) in alta.index.year.astype(str) else 0
        idx = pd.date_range(y0, y1, freq="D")
        missing = idx.difference(alta.index)
        total_missing.extend(missing.date)
        lines.append(f"| {year} | {expected} | {present} | {len(missing)} |")
    miss_txt = ", ".join(d.isoformat() for d in total_missing[:30]) + (" …" if len(total_missing) > 30 else "")
    lines.append("")
    lines.append(f"Total de días faltantes {first} → {last}: **{len(total_missing)}**" + (f" ({miss_txt})" if total_missing else ""))
    return "\n".join(lines)


def yearly_table(df: pd.DataFrame, cols: dict, subcuenca: str = "alta_frontera") -> str:
    sub = df[df["subcuenca"] == subcuenca].copy()
    sub["year"] = sub["fecha"].dt.year
    agg = sub.groupby("year").agg(**{k: v for k, v in cols.items()})
    header = "| Año | " + " | ".join(agg.columns) + " |"
    sep = "| --- | " + " | ".join("---" for _ in agg.columns) + " |"
    body = [f"| {y} | " + " | ".join(f"{v:.1f}" if isinstance(v, float) else str(v) for v in row) + " |" for y, row in agg.iterrows()]
    return "\n".join([header, sep] + body)


def compare_with_gold(merge_df: pd.DataFrame, samet_df: pd.DataFrame) -> str:
    if not GOLD_CACHE.exists():
        return "_Snapshot local de Gold no encontrado (`notebooks_local/gold_export/cache/training_dataset_v0.parquet`); comparación omitida._"
    gold = pd.read_parquet(GOLD_CACHE)
    gold["fecha"] = pd.to_datetime(gold["fecha"])
    gold = gold.set_index("fecha").sort_index()
    out = []

    m = merge_df[merge_df["subcuenca"] == "alta_frontera"].set_index("fecha").sort_index()
    joined = gold.join(m[["prec_media_mm", "pluviometros"]], how="inner")
    joined["lluvia_estacion_media_mm"] = joined["lluvia_acumulada_mm"] / joined["lluvia_agregado_alta_frontera_station_count"].replace(0, np.nan)
    j = joined.dropna(subset=["lluvia_estacion_media_mm", "prec_media_mm"])
    out.append(f"**Lluvia — `alta_frontera`** ({len(j)} días en común, {j.index.min().date()} → {j.index.max().date()}). "
               f"Media diaria estaciones ANA (suma/estaciones): {j['lluvia_estacion_media_mm'].mean():.2f} mm; MERGE media areal: {j['prec_media_mm'].mean():.2f} mm.")
    out.append("")
    out.append("| Desfase MERGE vs estaciones | Correlación diaria | Correlación mensual |")
    out.append("| --- | --- | --- |")
    for lag in (-1, 0, 1):
        s = j["prec_media_mm"].shift(lag)
        daily_corr = j["lluvia_estacion_media_mm"].corr(s)
        monthly = pd.DataFrame({"e": j["lluvia_estacion_media_mm"], "m": s}).resample("MS").sum(min_count=20)
        monthly_corr = monthly["e"].corr(monthly["m"])
        label = {0: "sin desfase (mismo día)", 1: "MERGE(D-1) vs estaciones(D)", -1: "MERGE(D+1) vs estaciones(D)"}[lag]
        out.append(f"| {label} | {daily_corr:.3f} | {monthly_corr:.3f} |")
    yearly = pd.DataFrame({"estaciones_mm": j["lluvia_estacion_media_mm"], "merge_mm": j["prec_media_mm"]}).resample("YS").sum(min_count=300)
    yearly = yearly.dropna()
    out.append("")
    out.append("| Año | Lluvia anual estaciones (mm) | Lluvia anual MERGE (mm) | Cociente MERGE/estaciones |")
    out.append("| --- | --- | --- | --- |")
    for y, row in yearly.iterrows():
        ratio = row["merge_mm"] / row["estaciones_mm"] if row["estaciones_mm"] else np.nan
        out.append(f"| {y.year} | {row['estaciones_mm']:.0f} | {row['merge_mm']:.0f} | {ratio:.2f} |")

    s = samet_df[samet_df["subcuenca"] == "alta_frontera"].set_index("fecha").sort_index()
    jt = gold.join(s[["temp_media_c", "temp_max_c", "temp_min_c"]], how="inner", rsuffix="_samet")
    jt = jt.dropna(subset=["temp_media_c", "temp_media_c_samet"])
    out.append("")
    out.append(f"**Temperatura — `alta_frontera`** ({len(jt)} días en común, {jt.index.min().date()} → {jt.index.max().date()}; "
               f"estaciones INMET vs SAMeT media areal).")
    out.append("")
    out.append("| Variable | Media estaciones (°C) | Media SAMeT (°C) | Sesgo SAMeT−estaciones | Correlación diaria |")
    out.append("| --- | --- | --- | --- | --- |")
    for var, gcol in [("media", "temp_media_c"), ("máxima", "temp_max_c"), ("mínima", "temp_min_c")]:
        a = jt[gcol]
        b = jt[f"{gcol}_samet"]
        ok = a.notna() & b.notna()
        out.append(f"| {var} | {a[ok].mean():.2f} | {b[ok].mean():.2f} | {(b[ok] - a[ok]).mean():+.2f} | {a[ok].corr(b[ok]):.3f} |")
    out.append("")
    out.append("_Nota: el agregado por estaciones usa `min`/`max` entre estaciones para mínima/máxima (extremos de la red) mientras que SAMeT "
               "es la media areal de la mínima/máxima de cada punto; el sesgo de esas dos filas es en parte diferencia de definición, no error._")
    return "\n".join(out)


def build_report(merge_df: pd.DataFrame, samet_df: pd.DataFrame) -> str:
    today = date.today().isoformat()
    parts = [
        "# Evaluación local de MERGE y SAMeT (CPTEC/INPE)",
        "",
        f"Generado por `notebooks_local/cptec_obs/evaluate_cptec_obs.py` el {today}, a partir del archivo completo descargado en local "
        "(`output_parquet/`) y de `grid_subcuenca.json`. Los agregados por sub-cuenca replican la regla de "
        "`ETL_Silver_CPTEC_Grid_Daily.ipynb` (media areal de los puntos de grilla dentro del polígono). "
        "Contexto y decisiones: `docs/data_sources.md` §9.6/§9.7 y Decisión 033.",
        "",
        "## 1. Cobertura temporal",
        "",
        "### MERGE (precipitación, desde 1998-01-02)",
        "",
        coverage_table(merge_df, MERGE_FIRST_DATE, "MERGE"),
        "",
        "### SAMeT (temperatura, desde 2000-01-01)",
        "",
        coverage_table(samet_df, SAMET_FIRST_DATE, "SAMeT"),
        "",
        "## 2. Densidad de observaciones dentro de `alta_frontera`",
        "",
        "MERGE: `pluviometros` = suma de NEST (pluviómetros por punto de grilla) sobre los puntos de la sub-cuenca, promedio diario del año; "
        "`puntos_con_pluviometro` = puntos de grilla con al menos un pluviómetro (de 566 puntos de 0,1°). "
        "SAMeT: `nobs_tmed` = observaciones de temperatura usadas por día (de 2.269 puntos de 0,05°).",
        "",
        yearly_table(merge_df, {
            "lluvia_anual_mm": ("prec_media_mm", "sum"),
            "pluviometros_prom_dia": ("pluviometros", "mean"),
            "puntos_con_pluviometro_prom": ("puntos_con_pluviometro", "mean"),
            "cobertura_pct_min": ("cobertura_pct", "min"),
        }),
        "",
        yearly_table(samet_df, {
            "tmed_anual_c": ("temp_media_c", "mean"),
            "tmax_anual_c": ("temp_max_c", "mean"),
            "tmin_anual_c": ("temp_min_c", "mean"),
            "nobs_tmed_prom_dia": ("nobs_tmed", "mean"),
            "cobertura_pct_min": ("cobertura_pct", "min"),
        }),
        "",
        "## 3. Climatología mensual (`alta_frontera`, todo el período)",
        "",
        monthly_climatology(merge_df, samet_df),
        "",
        "## 4. Comparación contra los agregados por estación del snapshot de Gold",
        "",
        compare_with_gold(merge_df, samet_df),
        "",
        "## 5. Estado de revisión de los archivos (regeneración de CPTEC)",
        "",
        revision_summary(merge_df, samet_df),
        "",
    ]
    return "\n".join(parts)


def monthly_climatology(merge_df: pd.DataFrame, samet_df: pd.DataFrame) -> str:
    m = merge_df[merge_df["subcuenca"] == "alta_frontera"].copy()
    m["month"] = m["fecha"].dt.month
    m["year"] = m["fecha"].dt.year
    monthly_sum = m.groupby(["year", "month"])["prec_media_mm"].sum().groupby("month").mean()
    s = samet_df[samet_df["subcuenca"] == "alta_frontera"].copy()
    s["month"] = s["fecha"].dt.month
    t = s.groupby("month")[["temp_media_c", "temp_max_c", "temp_min_c"]].mean()
    lines = ["| Mes | Lluvia media mensual MERGE (mm) | Tmed SAMeT (°C) | Tmax SAMeT (°C) | Tmin SAMeT (°C) |", "| --- | --- | --- | --- | --- |"]
    for month in range(1, 13):
        lines.append(f"| {month:02d} | {monthly_sum.get(month, np.nan):.0f} | {t.loc[month, 'temp_media_c']:.1f} | {t.loc[month, 'temp_max_c']:.1f} | {t.loc[month, 'temp_min_c']:.1f} |")
    lines.append(f"| **Año** | **{monthly_sum.sum():.0f}** | {t['temp_media_c'].mean():.1f} | {t['temp_max_c'].mean():.1f} | {t['temp_min_c'].mean():.1f} |")
    return "\n".join(lines)


def revision_summary(merge_df: pd.DataFrame, samet_df: pd.DataFrame) -> str:
    out = []
    for name, df, rule in [
        ("MERGE", merge_df, "regenerado en los primeros días del mes siguiente"),
        ("SAMeT", samet_df, "regenerado ~7 días después con ERA5"),
    ]:
        a = df[df["subcuenca"] == "alta_frontera"].copy()
        a["lm"] = pd.to_datetime(a["source_last_modified"], utc=True)
        a["lag_days"] = (a["lm"].dt.tz_localize(None) - a["fecha"]).dt.days
        recent = a[a["fecha"] >= a["fecha"].max() - pd.Timedelta(days=60)]
        out.append(f"* **{name}** ({rule}): `source_last_modified` − `fecha` en los últimos 60 días: mínimo {recent['lag_days'].min()} días, "
                   f"mediana {recent['lag_days'].median():.0f} días, máximo {recent['lag_days'].max()} días. "
                   f"Fecha de modificación más antigua en todo el archivo: {a['lm'].min().date()}; más reciente: {a['lm'].max().date()}.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-aggregate", action="store_true", help="Reusar los CSV de evaluation/ ya generados")
    parser.add_argument("--aggregate-only", choices=["merge", "samet"], default=None,
                        help="Solo agregar este producto a CSV (sin reporte); util mientras el otro todavia se descarga")
    args = parser.parse_args()

    if args.aggregate_only:
        aggregate_source(args.aggregate_only)
        return

    def load_or_aggregate(source):
        csv = EVAL_DIR / f"{source}_subcuenca_daily.csv"
        if args.skip_aggregate and csv.exists():
            return pd.read_csv(csv, parse_dates=["fecha"])
        return aggregate_source(source)

    merge_df = load_or_aggregate("merge")
    samet_df = load_or_aggregate("samet")

    report = build_report(merge_df, samet_df)
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"Reporte escrito en {REPORT_FILE}")


if __name__ == "__main__":
    main()
