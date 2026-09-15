"""Lock de un solo proceso para el backfill: usado tanto por la tarea programada de
Windows como por el dashboard Gradio, para que nunca corran dos backfills en paralelo
pisandose el estado (historic_backfill_state.json) ni la escritura de archivos JSON.

El lock file guarda el PID del proceso activo. `acquire()` chequea si el PID guardado
sigue vivo (via `tasklist`, sin dependencias extra tipo psutil) antes de asumir que el
lock esta stale y tomarlo.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

LOCK_FILE = Path(__file__).parent / "backfill.lock"


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
    """Devuelve la info del lock si hay un proceso realmente corriendo, None si no."""
    info = read_lock()
    if info is None:
        return None
    if _pid_is_running(info.get("pid", -1)):
        return info
    # lock stale (el proceso murio sin limpiar): lo liberamos solos.
    release()
    return None


def acquire(label: str) -> bool:
    """True si se pudo tomar el lock (no habia otro proceso corriendo)."""
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


def stop_running() -> bool:
    """Mata el proceso activo (si hay uno) via taskkill. True si se encontro y se mato."""
    info = is_locked()
    if info is None:
        return False
    pid = info["pid"]
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=15)
    release()
    return True
