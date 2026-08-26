"""Sube los JSON del backfill de GEFS Reforecast v12 (ya recortados a la cuenca y aplanados,
ver download_gefs_backfill.py) al Volume de Databricks que lee ETL_Bronze_GEFS.ipynb. No sube
nunca los .grib2 crudos (se borran localmente apenas se procesan) -- solo el JSON pequeno con
los puntos de grilla dentro del bounding box de la cuenca. No dispara ningun job -- el proximo
run del job de Bronze/Silver los recoge solo. Mismo patron que
notebooks_local/inmet_backfill/sync_to_databricks.py.

Requiere `databricks` CLI autenticado (perfil pasado por --profile). Sube solo los archivos
que todavia no existen en el Volume.

Uso:
    python sync_to_databricks.py --profile joaquintschopp@gmail.com
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LOCAL_DIR = Path(__file__).parent
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"

VOLUME_JSON_DIR = "dbfs:/Volumes/weather/raw/gefs_volume/json"


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    # 900s (15 min): un dia extendido recortado puede pesar ~338 MiB; 120s alcanzaba para
    # listar pero no para subir un archivo grande en una conexion modesta -- confirmado
    # empiricamente que el timeout corto tiraba `subprocess.TimeoutExpired` sin capturar,
    # cortando toda la corrida de backfill a mitad de un sync (ver Decision 030).
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def list_remote_files(profile: str, remote_dir: str) -> set[str]:
    result = _run(["databricks", "-p", profile, "fs", "ls", remote_dir, "--output", "json"])
    if result.returncode != 0:
        if "does not exist" in result.stderr or "RESOURCE_DOES_NOT_EXIST" in result.stderr or "no such directory" in result.stderr:
            return set()
        raise RuntimeError(f"No se pudo listar {remote_dir}: {result.stderr}")
    entries = json.loads(result.stdout)
    return {e["name"] for e in entries}


def _upload_one(profile: str, filepath: Path) -> tuple[str, bool, str]:
    """Corre en un worker thread. `databricks fs cp` es un subprocess I/O-bound (red), no
    hay contencion de GIL/eccodes como en la descarga -- threads alcanzan, no hace falta
    ProcessPoolExecutor aca."""
    dest = f"{VOLUME_JSON_DIR}/{filepath.name}"
    try:
        result = _run(["databricks", "-p", profile, "fs", "cp", str(filepath), dest, "--overwrite"])
    except subprocess.TimeoutExpired:
        return filepath.name, False, "timeout"
    if result.returncode != 0:
        return filepath.name, False, result.stderr.strip()[:300]
    return filepath.name, True, ""


def sync(profile: str, log=print, max_workers: int = 6) -> dict:
    """Sube en paralelo (`max_workers` uploads concurrentes) -- un solo `databricks fs cp`
    serial tarda ~1 min por archivo (~150-340 MiB cada uno), y con cientos de archivos
    acumulados entre sincronizaciones eso se volvia el cuello de botella real de todo el
    backfill (las descargas concurrentes generan trabajo mas rapido de lo que un upload
    serial puede subir) -- ver Decision 030."""
    summary = {"uploaded": 0, "failed": 0, "skipped": 0, "errors": []}
    log_lock = threading.Lock()

    def safe_log(msg: str) -> None:
        with log_lock:
            log(msg)

    if not OUTPUT_JSON_DIR.exists():
        raise RuntimeError(f"No existe {OUTPUT_JSON_DIR}, corre download_gefs_backfill.py primero")

    local_files = sorted(OUTPUT_JSON_DIR.glob("GEFS_*.json"))
    log(f"Listando archivos ya presentes en {VOLUME_JSON_DIR}...")
    remote_files = list_remote_files(profile, VOLUME_JSON_DIR)

    pending = [f for f in local_files if f.name not in remote_files]
    summary["skipped"] = len(local_files) - len(pending)
    log(f"{len(local_files)} archivos locales, {len(pending)} pendientes de subir ({max_workers} en paralelo)")

    done_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_upload_one, profile, f): f for f in pending}
        for future in as_completed(futures):
            name, ok, err = future.result()
            done_count += 1
            if ok:
                safe_log(f"  [{done_count}/{len(pending)}] OK {name}")
                summary["uploaded"] += 1
            else:
                safe_log(f"  [{done_count}/{len(pending)}] FALLO {name}: {err}")
                summary["failed"] += 1
                summary["errors"].append(f"{name}: {err}")

    log("\nListo. El proximo run de Bronze/Silver de GEFS va a mergear estos registros automaticamente.")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI (ej: joaquintschopp@gmail.com)")
    args = parser.parse_args()
    summary = sync(args.profile)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
