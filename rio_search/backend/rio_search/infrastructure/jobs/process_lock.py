"""Lock de un solo proceso (Fase 4, docs/rio_search_plan.md §5: "comparte el `lock.py` de
`ana_historic_backfill`"). Mismo patron que `notebooks_local/ana_historic_backfill/lock.py`
-- PID guardado en un archivo, verificado vivo via `tasklist` (Windows, sin dependencias extra
tipo `psutil`) antes de asumir que el lock esta "stale" -- **portado**, no importado: ese modulo
vive en `notebooks_local/` (entorno con pandas, conceptualmente otra parte del repo, §0 de este
encargo) y `rio_search/backend` no depende de nada fuera de si mismo.

Por que hace falta ademas de la cola en memoria de `SubprocessJobRunner`: la cola solo serializa
los jobs *dentro de este proceso* (el backend API). El aviso operativo de la Fase 3 es mas
amplio -- un `rio-search search run` corrido a mano desde otra terminal, o el propio CLI, tambien
cuenta como "otro proceso pegandole a Databricks con el mismo perfil". El lock de archivo cubre
eso: cualquier proceso de Rio_Search (API o CLI) que lo respete queda serializado entre si,
no solo los jobs encolados por esta API.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _pid_is_running(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    return str(pid) in result.stdout


class ProcessLock:
    def __init__(self, lock_file: Path) -> None:
        self._lock_file = lock_file

    def read(self) -> dict | None:
        if not self._lock_file.exists():
            return None
        try:
            return json.loads(self._lock_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def is_locked(self) -> dict | None:
        """Info del lock si hay un proceso realmente corriendo, `None` si no (y libera solo un
        lock "stale": el PID guardado ya no existe)."""
        info = self.read()
        if info is None:
            return None
        if _pid_is_running(info.get("pid", -1)):
            return info
        self.release()
        return None

    def acquire(self, label: str) -> bool:
        """`True` si se pudo tomar el lock (no habia otro proceso corriendo)."""
        if self.is_locked() is not None:
            return False
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file.write_text(
            json.dumps({"pid": os.getpid(), "label": label, "started_at": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    def release(self) -> None:
        try:
            self._lock_file.unlink(missing_ok=True)
        except OSError:
            pass

    def acquire_blocking(
        self, label: str, poll_seconds: float = 2.0, timeout_seconds: float | None = None
    ) -> bool:
        """Espera hasta poder tomar el lock (usado por `SubprocessJobRunner`: la cola local ya
        garantiza un job a la vez *de este proceso*, pero un `rio-search search run` corrido a
        mano en paralelo puede tener el lock tomado -- el worker espera en vez de fallar el
        job). `False` si se agoto `timeout_seconds` sin poder tomarlo."""
        waited = 0.0
        while not self.acquire(label):
            if timeout_seconds is not None and waited >= timeout_seconds:
                return False
            time.sleep(poll_seconds)
            waited += poll_seconds
        return True
