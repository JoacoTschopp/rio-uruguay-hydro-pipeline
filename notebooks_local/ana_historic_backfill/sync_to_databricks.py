"""Sube los JSON del backfill historico (descargados local con run_backfill_local.py) al
mismo folder que ya lee ETL_Bronze_ANA.ipynb en el Volume de Databricks. No dispara ningun
job: el proximo run programado de All_Estacoes_ANA_Daily (schedule diario existente) los
recoge solo, porque ETL_Bronze_ANA lee todo el folder json/ sin importar el origen del
archivo y hace MERGE idempotente por (codigoestacao, Data_Hora_Medicao).

Requiere `databricks` CLI autenticado (perfil pasado por --profile). Sube solo los
archivos que todavia no existen en el Volume (evita retransmitir todo en cada corrida).

Expone `sync(profile, sync_state=False) -> dict` para uso programatico (dashboard Gradio),
ademas del entrypoint CLI (usado por la tarea programada sync_task.ps1).

Uso:
    python sync_to_databricks.py --profile joaquintschopp@gmail.com
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

LOCAL_DIR = Path(__file__).parent
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"
STATE_FILE = LOCAL_DIR / "historic_backfill_state.json"
LAST_SYNC_FILE = LOCAL_DIR / "last_sync.json"

VOLUME_JSON_DIR = "dbfs:/Volumes/weather/raw/ana_volume/json"
VOLUME_STATE_FILE = "dbfs:/Volumes/weather/raw/ana_volume/historic_backfill_state.json"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def list_remote_files(profile: str) -> set[str]:
    result = _run(["databricks", "-p", profile, "fs", "ls", VOLUME_JSON_DIR, "--output", "json"])
    if result.returncode != 0:
        raise RuntimeError(f"No se pudo listar {VOLUME_JSON_DIR}: {result.stderr}")
    entries = json.loads(result.stdout)
    return {e["name"] for e in entries}


def sync(profile: str, sync_state: bool = False, log=print) -> dict:
    """Sube al Volume los JSON locales que todavia no esten alla. Devuelve un resumen
    {uploaded, failed, skipped, errors} para que el llamador (CLI o Gradio) lo muestre."""
    summary = {"uploaded": 0, "failed": 0, "skipped": 0, "errors": []}

    if not OUTPUT_JSON_DIR.exists():
        raise RuntimeError(f"No existe {OUTPUT_JSON_DIR}, corre run_backfill_local.py primero")

    local_files = sorted(OUTPUT_JSON_DIR.glob("ANA_HIST_*.json"))
    if not local_files:
        log("No hay archivos locales para subir.")
        return summary

    log(f"Listando archivos ya presentes en {VOLUME_JSON_DIR}...")
    remote_files = list_remote_files(profile)

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

    if sync_state and STATE_FILE.exists():
        result = _run(["databricks", "-p", profile, "fs", "cp", str(STATE_FILE), VOLUME_STATE_FILE, "--overwrite"])
        log("Estado sincronizado al Volume (backup)." if result.returncode == 0 else f"Fallo al subir estado: {result.stderr}")

    log("\nListo. El proximo run de All_Estacoes_ANA_Daily (job diario) va a mergear estos registros en Bronze automaticamente.")

    summary["finished_at"] = time.time()
    LAST_SYNC_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI (ej: joaquintschopp@gmail.com)")
    parser.add_argument("--sync-state", action="store_true", help="Tambien sube historic_backfill_state.json al Volume (backup, no se usa en Databricks)")
    args = parser.parse_args()
    sync(args.profile, sync_state=args.sync_state)


if __name__ == "__main__":
    main()
