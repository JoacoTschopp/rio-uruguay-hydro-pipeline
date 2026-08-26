"""Exportador local del dataset Gold (`weather.gold.training_dataset_v0`), sin necesitar
un SQL warehouse encendido (Decision 016). El task `Export_Gold_Snapshot`, al final del
job de Gold (notebooks/05_Gold/Export_Gold_Snapshot.ipynb), escribe un Parquet unico mas
un manifest.json en `/Volumes/weather/raw/gold_export_volume/`. Este script baja ambos con la
CLI de `databricks` (mismo camino de autenticacion que
notebooks_local/ana_historic_backfill/sync_to_databricks.py), cachea el Parquet en
`cache/` y sólo lo vuelve a bajar si la version Delta de origen cambio o si se pide
`--refresh`. `--resumen` corre siempre sobre el cache local, sin tocar Databricks.

Comparte el lock de un solo proceso con las tareas de ANA (notebooks_local/
ana_historic_backfill/lock.py) para no chocar con `sync_to_databricks.py` ni con
`run_backfill_local.py` mientras usan la CLI de `databricks` en paralelo.

Uso:
    python export_gold_dataset.py --profile joaquintschopp@gmail.com --resumen
    python export_gold_dataset.py --desde 2015-01-01 --confiable --horizonte 7
    python export_gold_dataset.py --refresh --formato csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

LOCAL_DIR = Path(__file__).parent
CACHE_DIR = LOCAL_DIR / "cache"
OUTPUT_DIR = LOCAL_DIR / "output"
CACHE_PARQUET = CACHE_DIR / "training_dataset_v0.parquet"
CACHE_MANIFEST = CACHE_DIR / "manifest.json"

VOLUME_DIR = "dbfs:/Volumes/weather/raw/gold_export_volume"
VOLUME_PARQUET = f"{VOLUME_DIR}/training_dataset_v0.parquet"
VOLUME_MANIFEST = f"{VOLUME_DIR}/manifest.json"

DEFAULT_PROFILE = "joaquintschopp@gmail.com"

# Horizontes que el roadmap fija como objetivo final (Decision 019). Hoy Gold solo
# publica caudal_t_mas_{1,3,7,14}d; el resto llega en la Fase 2 (8 horizontes).
KNOWN_HORIZONS = [1, 2, 3, 4, 5, 6, 7, 14]

sys.path.insert(0, str(LOCAL_DIR.parent / "ana_historic_backfill"))
import lock as shared_lock  # noqa: E402  (lock compartido con las tareas de ANA)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sync(profile: str, refresh: bool, log=print) -> dict:
    """Baja manifest.json (siempre, es liviano) y el Parquet solo si la version Delta
    cambio o si se pide --refresh. Devuelve el manifest remoto."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_manifest = CACHE_DIR / "manifest.remote.json"

    result = _run(["databricks", "-p", profile, "fs", "cp", VOLUME_MANIFEST, str(tmp_manifest), "--overwrite"])
    if result.returncode != 0:
        raise RuntimeError(f"No se pudo bajar manifest.json desde {VOLUME_MANIFEST}: {result.stderr}")
    remote_manifest = json.loads(tmp_manifest.read_text(encoding="utf-8"))
    tmp_manifest.unlink(missing_ok=True)

    local_manifest = json.loads(CACHE_MANIFEST.read_text(encoding="utf-8")) if CACHE_MANIFEST.exists() else None
    need_download = needs_download(local_manifest, remote_manifest, refresh, CACHE_PARQUET.exists())

    if need_download:
        log(f"Version Delta {remote_manifest.get('delta_version')} (cache: "
            f"{local_manifest.get('delta_version') if local_manifest else None}); bajando parquet...")
        result = _run(["databricks", "-p", profile, "fs", "cp", VOLUME_PARQUET, str(CACHE_PARQUET), "--overwrite"])
        if result.returncode != 0:
            raise RuntimeError(f"No se pudo bajar el parquet desde {VOLUME_PARQUET}: {result.stderr}")
        actual_hash = sha256_of(CACHE_PARQUET)
        expected_hash = remote_manifest.get("file_sha256")
        if expected_hash and actual_hash != expected_hash:
            raise RuntimeError(
                f"Hash del parquet descargado ({actual_hash}) no coincide con el manifest "
                f"({expected_hash}); descarga corrupta, reintentar."
            )
        CACHE_MANIFEST.write_text(json.dumps(remote_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        log("Parquet actualizado.")
    else:
        log(f"Version Delta sin cambios ({remote_manifest.get('delta_version')}); usando cache local.")

    return remote_manifest


def needs_download(local_manifest: Optional[dict], remote_manifest: dict, refresh: bool, cache_exists: bool) -> bool:
    if refresh or not cache_exists or local_manifest is None:
        return True
    return local_manifest.get("delta_version") != remote_manifest.get("delta_version")


def load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def apply_filters(
    df: pd.DataFrame,
    desde: Optional[date] = None,
    confiable: bool = False,
    horizonte: Optional[int] = None,
) -> pd.DataFrame:
    if desde is not None:
        df = df[df["fecha"] >= pd.Timestamp(desde)]

    if confiable:
        if "caudal_confiable" not in df.columns:
            raise ValueError("La columna caudal_confiable no esta en el dataset; no se puede filtrar por --confiable")
        df = df[df["caudal_confiable"] == True]  # noqa: E712 (comparacion explicita, NULL no confiable se excluye)

    if horizonte is not None:
        df = trim_horizon_tail(df, horizonte)

    return df.reset_index(drop=True)


def trim_horizon_tail(df: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    """Regla R9: recorta la cola de dias sin target observable para ese horizonte
    (Decision 019, enmienda). Recorta por fecha, no por NULL: un NULL en medio de la
    serie es dato faltante real y se conserva."""
    caudal_col = f"caudal_t_mas_{horizonte}d"
    nivel_col = f"nivel_rio_t_mas_{horizonte}d"
    if caudal_col not in df.columns and nivel_col not in df.columns:
        disponibles = sorted(
            int(c.removeprefix("caudal_t_mas_").removesuffix("d"))
            for c in df.columns
            if c.startswith("caudal_t_mas_") and c.endswith("d")
        )
        raise ValueError(
            f"Horizonte {horizonte}d no esta publicado en Gold todavia "
            f"(la Fase 2 del roadmap agrega los horizontes restantes). "
            f"Horizontes disponibles hoy: {disponibles}"
        )
    if df.empty:
        return df
    cutoff = df["fecha"].max() - pd.Timedelta(days=horizonte)
    return df[df["fecha"] <= cutoff]


def build_resumen(df: pd.DataFrame) -> str:
    lines = [f"Filas: {len(df)}"]
    if df.empty:
        lines.append("Rango de fechas: (sin datos)")
        return "\n".join(lines)

    lines.append(f"Rango de fechas: {df['fecha'].min().date()} a {df['fecha'].max().date()}")
    lines.append("")
    lines.append("Faltantes por columna:")
    total = len(df)
    missing = df.isna().sum().sort_values(ascending=False)
    for col, n_missing in missing.items():
        if n_missing == 0:
            continue
        lines.append(f"  {col}: {n_missing} ({100.0 * n_missing / total:.1f}%)")

    lines.append("")
    lines.append("Cobertura por caudal_metodo:")
    if "caudal_metodo" in df.columns:
        counts = df["caudal_metodo"].value_counts(dropna=False)
        for metodo, n in counts.items():
            lines.append(f"  {metodo}: {n} ({100.0 * n / total:.1f}%)")
    else:
        lines.append("  (columna caudal_metodo no presente)")

    return "\n".join(lines)


def export_file(df: pd.DataFrame, formato: str, out_dir: Path, suffix: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"training_dataset_v0{suffix}_{ts}.{formato}"
    if formato == "csv":
        df.to_csv(path, index=False)
    else:
        df.to_parquet(path, index=False)
    return path


def filters_suffix(desde: Optional[date], confiable: bool, horizonte: Optional[int]) -> str:
    parts = []
    if desde is not None:
        parts.append(f"desde-{desde.isoformat()}")
    if confiable:
        parts.append("confiable")
    if horizonte is not None:
        parts.append(f"h{horizonte}d")
    return ("_" + "_".join(parts)) if parts else ""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Perfil de databricks CLI (solo hace falta si se contacta el Volume)")
    parser.add_argument("--refresh", action="store_true", help="Forzar re-descarga del parquet aunque la version Delta no haya cambiado")
    parser.add_argument("--desde", type=date.fromisoformat, default=None, help="Filtrar fecha >= YYYY-MM-DD")
    parser.add_argument("--confiable", action="store_true", help="Filtrar solo filas con caudal_confiable = true")
    parser.add_argument("--horizonte", type=int, choices=KNOWN_HORIZONS, default=None, help="Aplica R9: recorta la cola sin target observable para ese horizonte")
    parser.add_argument("--formato", choices=["parquet", "csv"], default="parquet", help="Formato del archivo exportado")
    parser.add_argument("--resumen", action="store_true", help="Imprime filas, rango de fechas, faltantes por columna y cobertura por caudal_metodo")
    parser.add_argument("--offline", action="store_true", help="No tocar Databricks; usar solo el cache local (falla si no hay cache)")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if not shared_lock.acquire("gold_export"):
        info = shared_lock.read_lock()
        print(f"Hay otro proceso local corriendo ({info}); abortando para no chocar con el backfill de ANA.")
        return 1

    try:
        if args.offline:
            if not CACHE_PARQUET.exists():
                print("No hay cache local y se pidio --offline. Corre una vez sin --offline para poblarlo.")
                return 1
        else:
            sync(args.profile, refresh=args.refresh)

        df = load_dataset(CACHE_PARQUET)
        try:
            df = apply_filters(df, desde=args.desde, confiable=args.confiable, horizonte=args.horizonte)
        except ValueError as exc:
            print(str(exc))
            return 1

        if args.resumen:
            print(build_resumen(df))
            print()

        suffix = filters_suffix(args.desde, args.confiable, args.horizonte)
        out_path = export_file(df, args.formato, OUTPUT_DIR, suffix)
        print(f"Exportado: {out_path} ({len(df)} filas)")
        return 0
    finally:
        shared_lock.release()


if __name__ == "__main__":
    sys.exit(main())
