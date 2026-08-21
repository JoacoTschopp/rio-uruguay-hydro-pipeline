"""Lista las fechas en que el caudal de la estacion objetivo (74100000) se calculo por
extrapolacion (R5, Decision 019): cota fuera del rango calibrado de la curva vigente. Es
el insumo pedido en la Fase 2 del roadmap para contrastar contra cronicas de crecidas
documentadas al escribir la tesis -- un valor fuera de tabla es muy probablemente una
crecida real, no un error de instrumento.

Corre sobre el mismo cache local que export_gold_dataset.py (no vuelve a bajar nada salvo
que se pida --refresh), porque training_dataset_v0 ya trae caudal_metodo,
caudal_extrapolado y distancia_fuera_rango_cm para la estacion target en cada fila.

Uso:
    python fechas_extrapoladas.py
    python fechas_extrapoladas.py --refresh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import export_gold_dataset as export

OUTPUT_CSV = export.OUTPUT_DIR / "fechas_extrapoladas_74100000.csv"

COLUMNS = ["fecha", "caudal_metodo", "caudal_extrapolado", "distancia_fuera_rango_cm", "curva_vigencia_extendida"]


def build_report(df) -> "object":
    faltantes = [c for c in COLUMNS if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Faltan columnas {faltantes} en el dataset cacheado; corre export_gold_dataset.py "
            "--refresh primero (necesita el Gold regenerado con la Fase 2)."
        )
    if "caudal_actual_m3s" in df.columns:
        caudal_col = "caudal_actual_m3s"
    elif "caudal_m3s" in df.columns:
        caudal_col = "caudal_m3s"
    else:
        raise ValueError("Ni caudal_actual_m3s ni caudal_m3s estan en el dataset cacheado.")
    extrapolados = df[df["caudal_extrapolado"] == True]  # noqa: E712
    report = extrapolados[["fecha", "caudal_metodo", caudal_col, "distancia_fuera_rango_cm", "curva_vigencia_extendida"]]
    report = report.rename(columns={caudal_col: "caudal_m3s"}).sort_values("fecha").reset_index(drop=True)
    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=export.DEFAULT_PROFILE)
    parser.add_argument("--refresh", action="store_true", help="Forzar re-descarga del parquet antes de generar el listado")
    parser.add_argument("--offline", action="store_true", help="No tocar Databricks; usar solo el cache local")
    args = parser.parse_args(argv)

    if not export.shared_lock.acquire("gold_export"):
        info = export.shared_lock.read_lock()
        print(f"Hay otro proceso local corriendo ({info}); abortando.")
        return 1

    try:
        if not args.offline:
            export.sync(args.profile, refresh=args.refresh)
        elif not export.CACHE_PARQUET.exists():
            print("No hay cache local y se pidio --offline. Corre una vez sin --offline para poblarlo.")
            return 1

        df = export.load_dataset(export.CACHE_PARQUET)
        report = build_report(df)

        export.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report.to_csv(OUTPUT_CSV, index=False)
        print(f"{len(report)} fechas extrapoladas escritas en {OUTPUT_CSV}")
        if not report.empty:
            print(report["caudal_metodo"].value_counts().to_string())
        return 0
    finally:
        export.shared_lock.release()


if __name__ == "__main__":
    sys.exit(main())
