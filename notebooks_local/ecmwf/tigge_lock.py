"""Lock de un solo proceso, dedicado al backfill local de TIGGE (cf+pf). Mismo mecanismo que
notebooks_local/ana_historic_backfill/lock.py (PID + `tasklist` para detectar locks
abandonados), pero con su propio archivo -- **no se reusa el lock compartido de
ana_historic_backfill/inmet_backfill/gefs_reforecast a proposito**: esas tres fuentes y TIGGE
pegan contra APIs completamente distintas (ANA, INMET, S3 publico de NOAA, ECDS/TIGGE) y no
hace falta serializarlas entre si. Lo que si hay que serializar -- `cf` nunca en paralelo con
`pf`, ninguno de los dos en paralelo con el job diario de Databricks -- ya lo maneja
run_tigge_backfill.py corriendo todo en un solo proceso con este lock.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

LOCK_FILE = Path(__file__).parent / "tigge_backfill.lock"


def _pid_is_running(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return False
    return str(pid) in result.stdout


def read_lock() -> Optional[dict]:
    if not LOCK_FILE.exists():
        return None
    try:
        return json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def is_locked() -> Optional[dict]:
    info = read_lock()
    if info is None:
        return None
    if _pid_is_running(info.get("pid", -1)):
        return info
    release()
    return None


def acquire(label: str) -> bool:
    if is_locked() is not None:
        return False
    LOCK_FILE.write_text(
        json.dumps({"pid": os.getpid(), "label": label, "started_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def release() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass
