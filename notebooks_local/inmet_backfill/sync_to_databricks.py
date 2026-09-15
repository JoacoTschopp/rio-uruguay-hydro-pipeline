"""Sube el catalogo de estaciones y los JSON del backfill INMET al Volume de Databricks
que leen DDL_Silver_Gold.ipynb (catalogo) y ETL_Bronze_INMET.ipynb (json/). No dispara ningun
job -- el proximo run del job de Silver/Gold los recoge solo. Mismo patron que
notebooks_local/ana_historic_backfill/sync_to_databricks.py.

Requiere `databricks` CLI autenticado (perfil pasado por --profile). Sube solo los archivos
que todavia no existen en el Volume.

Uso:
    python sync_to_databricks.py --profile joaquintschopp@gmail.com
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

LOCAL_DIR = Path(__file__).parent
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"
CATALOGO_FILE = LOCAL_DIR / "estaciones_inmet_catalogo.json"

VOLUME_JSON_DIR = "dbfs:/Volumes/weather/raw/inmet_volume/json"
VOLUME_CATALOGO_DIR = "dbfs:/Volumes/weather/raw/inmet_volume/catalogo"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def list_remote_files(profile: str, remote_dir: str) -> set[str]:
    result = _run(["databricks", "-p", profile, "fs", "ls", remote_dir, "--output", "json"])
    if result.returncode != 0:
        if "does not exist" in result.stderr or "RESOURCE_DOES_NOT_EXIST" in result.stderr:
            return set()
        raise RuntimeError(f"No se pudo listar {remote_dir}: {result.stderr}")
    entries = json.loads(result.stdout)
    return {e["name"] for e in entries}


def sync(profile: str, log=print) -> dict:
    summary = {"uploaded": 0, "failed": 0, "skipped": 0, "errors": []}

    if not OUTPUT_JSON_DIR.exists():
        raise RuntimeError(f"No existe {OUTPUT_JSON_DIR}, corre download_inmet_zips.py primero")

    local_files = sorted(OUTPUT_JSON_DIR.glob("INMET_*.json"))
    log(f"Listando archivos ya presentes en {VOLUME_JSON_DIR}...")
    remote_files = list_remote_files(profile, VOLUME_JSON_DIR)

    pending = [f for f in local_files if f.name not in remote_files]
    summary["skipped"] = len(local_files) - len(pending)
    log(f"{len(local_files)} archivos locales, {len(pending)} pendientes de subir")

    for i, filepath in enumerate(pending, 1):
        dest = f"{VOLUME_JSON_DIR}/{filepath.name}"
        result = _run(["databricks", "-p", profile, "fs", "cp", str(filepath), dest, "--overwrite"])
        if result.returncode != 0:
            log(f"  [{i}/{len(pending)}] FALLO {filepath.name}: {result.stderr.strip()[:300]}")
            summary["failed"] += 1
            summary["errors"].append(f"{filepath.name}: {result.stderr.strip()[:300]}")
            continue
        log(f"  [{i}/{len(pending)}] OK {filepath.name}")
        summary["uploaded"] += 1

    if CATALOGO_FILE.exists():
        dest = f"{VOLUME_CATALOGO_DIR}/{CATALOGO_FILE.name}"
        result = _run(["databricks", "-p", profile, "fs", "cp", str(CATALOGO_FILE), dest, "--overwrite"])
        log(f"Catalogo subido a {dest}" if result.returncode == 0 else f"Fallo al subir catalogo: {result.stderr}")

    log("\nListo. El proximo run de Silver_Gold_Initial_Load_v0 / Daily_Incremental va a mergear estos registros en Bronze automaticamente.")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI (ej: joaquintschopp@gmail.com)")
    args = parser.parse_args()
    summary = sync(args.profile)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
