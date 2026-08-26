"""Sube los JSON del backfill local de TIGGE (`cf`+`pf`, ver historic_cf_tigge.py/
historic_pf_tigge.py/run_tigge_backfill.py) al Volume de Databricks que ya lee
ETL_Bronze_ECMWF_CF.ipynb / ETL_Bronze_ECMWF_PF.ipynb -- mismo folder que usa el job diario
(`Daily_ECMWF_CF`/`Daily_ECMWF_PF`), asi Bronze no distingue el origen del archivo. Mismo
patron que notebooks_local/gefs_reforecast/sync_to_databricks.py (upload paralelo, subprocess
`databricks fs cp`).

No dispara ningun job -- el proximo run de Bronze/Silver los recoge solo.

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
CF_JSON_DIR = LOCAL_DIR / "local_data" / "ecmwf_volume" / "cf_tigge" / "json"
PF_JSON_DIR = LOCAL_DIR / "local_data" / "ecmwf_volume" / "pf_tigge" / "json"

VOLUME_CF_JSON_DIR = "dbfs:/Volumes/weather/raw/ecmwf_volume/cf_tigge/json"
VOLUME_PF_JSON_DIR = "dbfs:/Volumes/weather/raw/ecmwf_volume/pf_tigge/json"


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def list_remote_files(profile: str, remote_dir: str) -> set[str]:
    result = _run(["databricks", "-p", profile, "fs", "ls", remote_dir, "--output", "json"])
    if result.returncode != 0:
        if "does not exist" in result.stderr or "RESOURCE_DOES_NOT_EXIST" in result.stderr or "no such directory" in result.stderr:
            return set()
        raise RuntimeError(f"No se pudo listar {remote_dir}: {result.stderr}")
    entries = json.loads(result.stdout)
    return {e["name"] for e in entries}


def _upload_one(profile: str, filepath: Path, remote_dir: str) -> tuple[str, bool, str]:
    dest = f"{remote_dir}/{filepath.name}"
    try:
        result = _run(["databricks", "-p", profile, "fs", "cp", str(filepath), dest, "--overwrite"])
    except subprocess.TimeoutExpired:
        return filepath.name, False, "timeout"
    if result.returncode != 0:
        return filepath.name, False, result.stderr.strip()[:300]
    return filepath.name, True, ""


def _sync_dir(profile: str, local_dir: Path, remote_dir: str, label: str, log, max_workers: int = 6) -> dict:
    summary = {"uploaded": 0, "failed": 0, "skipped": 0, "errors": []}
    log_lock = threading.Lock()

    def safe_log(msg: str) -> None:
        with log_lock:
            log(msg)

    if not local_dir.exists():
        log(f"[{label}] No existe {local_dir}, nada que subir.")
        return summary

    local_files = sorted(local_dir.glob("ECMWF_*.json"))
    if not local_files:
        log(f"[{label}] Sin archivos locales.")
        return summary

    log(f"[{label}] Listando archivos ya presentes en {remote_dir}...")
    remote_files = list_remote_files(profile, remote_dir)
    pending = [f for f in local_files if f.name not in remote_files]
    summary["skipped"] = len(local_files) - len(pending)
    log(f"[{label}] {len(local_files)} archivos locales, {len(pending)} pendientes de subir")

    done_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_upload_one, profile, f, remote_dir): f for f in pending}
        for future in as_completed(futures):
            name, ok, err = future.result()
            done_count += 1
            if ok:
                safe_log(f"[{label}] [{done_count}/{len(pending)}] OK {name}")
                summary["uploaded"] += 1
            else:
                safe_log(f"[{label}] [{done_count}/{len(pending)}] FALLO {name}: {err}")
                summary["failed"] += 1
                summary["errors"].append(f"{name}: {err}")

    return summary


def sync(profile: str, log=print) -> dict:
    cf_summary = _sync_dir(profile, CF_JSON_DIR, VOLUME_CF_JSON_DIR, "cf", log)
    pf_summary = _sync_dir(profile, PF_JSON_DIR, VOLUME_PF_JSON_DIR, "pf", log)
    combined = {
        "uploaded": cf_summary["uploaded"] + pf_summary["uploaded"],
        "failed": cf_summary["failed"] + pf_summary["failed"],
        "skipped": cf_summary["skipped"] + pf_summary["skipped"],
        "errors": cf_summary["errors"] + pf_summary["errors"],
    }
    log(f"\nListo. cf: {cf_summary}, pf: {pf_summary}")
    return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI (ej: joaquintschopp@gmail.com)")
    args = parser.parse_args()
    summary = sync(args.profile)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
