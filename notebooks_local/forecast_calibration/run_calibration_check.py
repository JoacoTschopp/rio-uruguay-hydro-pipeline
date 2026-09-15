"""Verificacion contra datos REALES de Databricks de la calibracion GEFS c00 -> TIGGE cf
(Decision 021/035, Fase 4 de `docs/roadmap.md`). No simula nada: mide la cobertura real de
ambas tablas Bronze, arma el conjunto de `run_date` donde de verdad se solapan, pull esas
filas via SQL (recortadas a los `step_hours` de 24h necesarios para los horizontes de la
Decision 019) y corre el pipeline de `calibration.py` sobre ellas.

Si el solapamiento real disponible hoy es chico (la extension de GEFS 2006-10->2019-12,
Decision 034, sigue corriendo en background mientras se escribe este script), el reporte lo
dice explicitamente -- no rellena con nada sintetico. Re-correr este script mas adelante,
cuando la extension haya avanzado, amplia la muestra sin cambiar una linea de codigo.

Uso:
    python run_calibration_check.py
    python run_calibration_check.py --out output/bias_table.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibration as calib  # noqa: E402
from db_query import run_sql  # noqa: E402

RANGE_START = "2006-10-01"
RANGE_END = "2019-12-31"
NEEDED_STEPS = "(24,48,72,96,120,144,168,312,336)"


def measure_coverage() -> tuple[pd.DataFrame, pd.DataFrame, list]:
    print(f"== Cobertura real en Bronze, ventana {RANGE_START} .. {RANGE_END} ==")

    gefs_dates_df = run_sql(
        f"""
        SELECT DISTINCT run_date FROM weather.bronze.gefs_reforecast
        WHERE member = 'c00' AND run_date BETWEEN '{RANGE_START}' AND '{RANGE_END}'
        ORDER BY run_date
        """
    )
    tigge_dates_df = run_sql(
        f"""
        SELECT DISTINCT run_date FROM weather.bronze.ecmwf_forecast_cf
        WHERE run_date BETWEEN '{RANGE_START}' AND '{RANGE_END}'
        ORDER BY run_date
        """
    )

    gefs_dates = set(pd.to_datetime(gefs_dates_df["run_date"]).dt.date) if not gefs_dates_df.empty else set()
    tigge_dates = set(pd.to_datetime(tigge_dates_df["run_date"]).dt.date) if not tigge_dates_df.empty else set()
    overlap = sorted(gefs_dates & tigge_dates)

    print(f"GEFS c00: {len(gefs_dates)} fechas de corrida en la ventana"
          + (f" ({min(gefs_dates)} .. {max(gefs_dates)})" if gefs_dates else ""))
    print(f"TIGGE cf: {len(tigge_dates)} fechas de corrida en la ventana"
          + (f" ({min(tigge_dates)} .. {max(tigge_dates)})" if tigge_dates else ""))
    print(f"Solapamiento real (mismo run_date en ambas fuentes): {len(overlap)} fechas")
    if overlap:
        print(f"  {overlap[:10]}{' ...' if len(overlap) > 10 else ''}")
    return gefs_dates_df, tigge_dates_df, overlap


def pull_points(table: str, overlap_dates: list, member_filter: str | None = None) -> pd.DataFrame:
    dates_sql = ",".join(f"'{d}'" for d in overlap_dates)
    member_clause = f"AND member = '{member_filter}'" if member_filter else ""
    query = f"""
        SELECT run_date, latitude, longitude, step_hours, tp_mm
        FROM {table}
        WHERE run_date IN ({dates_sql}) AND step_hours IN {NEEDED_STEPS} {member_clause}
    """
    df = run_sql(query)
    if not df.empty:
        df["run_date"] = pd.to_datetime(df["run_date"]).dt.date.astype(str)
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="Ruta CSV donde guardar la tabla de sesgo calculada")
    parser.add_argument("--method", default="additive", choices=["additive", "multiplicative"])
    args = parser.parse_args()

    _, _, overlap = measure_coverage()

    if not overlap:
        print("\nNo hay ni un solo run_date real donde GEFS c00 y TIGGE cf coincidan en la "
              "ventana 2006-10->2019-12 todavia. La extension de GEFS (Decision 034) sigue "
              "bajando ese tramo en background -- no hay nada que calibrar hoy con datos "
              "reales. Volver a correr este script cuando avance.")
        return

    print(f"\n== Pull de {len(overlap)} fecha(s) de solapamiento real (steps de 24h en {NEEDED_STEPS}) ==")
    gefs_raw = pull_points("weather.bronze.gefs_reforecast", overlap, member_filter="c00")
    tigge_raw = pull_points("weather.bronze.ecmwf_forecast_cf", overlap)
    print(f"GEFS c00: {len(gefs_raw)} filas crudas (bbox completo, sin tagear)")
    print(f"TIGGE cf: {len(tigge_raw)} filas crudas (bbox completo, sin tagear)")

    if gefs_raw.empty or tigge_raw.empty:
        print("Una de las dos fuentes no trajo filas para las fechas de solapamiento -- abortando.")
        return

    print("\n== Tageando puntos de grilla a sub-cuenca (buffer 0.15 grados, subcuencas_modelo.geojson) ==")
    gefs_tagged = calib.tag_points(gefs_raw)
    tigge_tagged = calib.tag_points(tigge_raw)
    print(f"GEFS c00: {gefs_tagged['subcuenca_nombre'].notna().sum()} / {len(gefs_tagged)} filas caen en alguna sub-cuenca")
    print(f"TIGGE cf: {tigge_tagged['subcuenca_nombre'].notna().sum()} / {len(tigge_tagged)} filas caen en alguna sub-cuenca")

    print("\n== Precipitacion diaria por horizonte (Decision 019: t+1..t+7, t+14) ==")
    gefs_daily = calib.daily_horizon_precip(gefs_tagged)
    tigge_daily = calib.daily_horizon_precip(tigge_tagged)
    print(f"GEFS c00: {len(gefs_daily)} filas (run_date x punto x horizonte)")
    print(f"TIGGE cf: {len(tigge_daily)} filas (run_date x punto x horizonte)")

    gefs_agg = calib.aggregate_by_subcuenca(gefs_daily)
    tigge_agg = calib.aggregate_by_subcuenca(tigge_daily)

    print("\n== Sesgo GEFS c00 vs TIGGE cf, por sub-cuenca x horizonte (metodo: %s) ==" % args.method)
    bias = calib.compute_bias_table(gefs_agg, tigge_agg, method=args.method)
    if bias.empty:
        print("compute_bias_table no encontro ningun (subcuenca, horizonte) con solapamiento "
              "real tras tagear y calcular horizontes -- probablemente los puntos de las "
              "fechas disponibles no caen dentro de ninguna sub-cuenca con buffer, o falta "
              "algun step. Revisar el pull de arriba.")
        return

    with pd.option_context("display.max_rows", None, "display.width", 140):
        print(bias.sort_values(["subcuenca_nombre", "horizon_days"]).to_string(index=False))

    print("\nADVERTENCIA: el n_days de la mayoria de estas filas es minimo (solapamiento real "
          "todavia parcial mientras la extension de GEFS 2006-10->2019-12 termina de bajar, "
          "Decision 034) -- el sesgo estimado con pocos dias no es estadisticamente robusto. "
          "Re-correr este script y regenerar la tabla de sesgo cuando el solapamiento sea "
          "mayor, antes de usarla para calibrar la serie completa en produccion.")

    print("\n== Aplicando el sesgo a la serie GEFS del solapamiento (sanity check, no es la corrida completa) ==")
    calibrated = calib.apply_bias(gefs_agg, bias, method=args.method)
    with pd.option_context("display.max_rows", 20, "display.width", 140):
        print(calibrated.sort_values(["run_date", "subcuenca_nombre", "horizon_days"]).to_string(index=False))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        bias.to_csv(out_path, index=False)
        print(f"\nTabla de sesgo guardada en {out_path}")


if __name__ == "__main__":
    main()
