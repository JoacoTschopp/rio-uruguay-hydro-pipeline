"""Sube los JSON crudos del barrido de curvas de aforo (descargados local con
download_rating_curves_batch.py) al Volume que lee ETL_Bronze_Rating_Curve.ipynb. No
dispara ningun job: el proximo run de Rating_Curve_Discharge_Initial_Load los recoge solo,
porque ese notebook lee todo el folder sin importar el origen del archivo y hace MERGE
idempotente.

Mismo patron que notebooks_local/ana_historic_backfill/sync_to_databricks.py: sube solo
los archivos que todavia no existen en el Volume, para poder correrlo de nuevo despues del
refresco trimestral de curvas (Decision 020) sin retransmitir todo.

Requiere `databricks` CLI autenticado (perfil pasado por --profile).

Uso:
    python sync_to_databricks.py --profile joaquintschopp@gmail.com
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

LOCAL_DIR = Path(__file__).parent
RAW_JSON_DIR = LOCAL_DIR / "output" / "raw_json"

VOLUME_CURVE_SEGMENTS_DIR = "dbfs:/Volumes/weather/raw/ana_volume/rating_curves/curve_segments"
VOLUME_DISCHARGE_MEASUREMENTS_DIR = "dbfs:/Volumes/weather/raw/ana_volume/rating_curves/discharge_measurements"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def list_remote_files(profile: str, volume_dir: str) -> set[str]:
    result = _run(["databricks", "-p", profile, "fs", "ls", volume_dir, "--output", "json"])
    if result.returncode != 0:
        if "not found" in result.stderr.lower() or "does not exist" in result.stderr.lower():
            return set()
        raise RuntimeError(f"No se pudo listar {volume_dir}: {result.stderr}")
    entries = json.loads(result.stdout)
    return {e["name"] for e in entries}


def _sync_group(profile: str, local_files: list[Path], volume_dir: str, log) -> dict:
    summary = {"uploaded": 0, "failed": 0, "skipped": 0, "errors": []}
    if not local_files:
        log(f"No hay archivos locales para {volume_dir}.")
        return summary

    log(f"Listando archivos ya presentes en {volume_dir}...")
    remote_files = list_remote_files(profile, volume_dir)
    pending = [f for f in local_files if f.name not in remote_files]
    summary["skipped"] = len(local_files) - len(pending)
    log(f"{len(local_files)} archivos locales, {len(pending)} pendientes de subir")

    for i, filepath in enumerate(pending, 1):
        dest = f"{volume_dir}/{filepath.name}"
        result = _run(["databricks", "-p", profile, "fs", "cp", str(filepath), dest, "--overwrite"])
        if result.returncode != 0:
            log(f"  [{i}/{len(pending)}] FALLO {filepath.name}: {result.stderr.strip()[:300]}")
            summary["failed"] += 1
            summary["errors"].append(f"{filepath.name}: {result.stderr.strip()[:300]}")
            continue
        log(f"  [{i}/{len(pending)}] OK {filepath.name}")
        summary["uploaded"] += 1
    return summary


def sync(profile: str, log=print) -> dict:
    """Sube al Volume los JSON de curvas (`curva_*.json`) y aforos (`aforos_*.json`) que
    todavia no esten alla. Devuelve un resumen por grupo."""
    if not RAW_JSON_DIR.exists():
        raise RuntimeError(f"No existe {RAW_JSON_DIR}, corre download_rating_curves_batch.py primero")

    curve_files = sorted(RAW_JSON_DIR.glob("curva_*.json"))
    discharge_files = sorted(RAW_JSON_DIR.glob("aforos_*.json"))

    log(f"-- Curvas ({len(curve_files)} archivos locales) --")
    curve_summary = _sync_group(profile, curve_files, VOLUME_CURVE_SEGMENTS_DIR, log)

    log(f"-- Aforos ({len(discharge_files)} archivos locales) --")
    discharge_summary = _sync_group(profile, discharge_files, VOLUME_DISCHARGE_MEASUREMENTS_DIR, log)

    log("\nListo. El proximo run de Rating_Curve_Discharge_Initial_Load va a mergear estos registros en Bronze.")
    return {"curve_segments": curve_summary, "discharge_measurements": discharge_summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI (ej: joaquintschopp@gmail.com)")
    args = parser.parse_args()
    sync(args.profile)


if __name__ == "__main__":
    main()
