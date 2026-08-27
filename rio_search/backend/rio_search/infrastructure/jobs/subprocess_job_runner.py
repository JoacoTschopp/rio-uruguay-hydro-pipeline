"""`SubprocessJobRunner` (Fase 4, docs/rio_search_plan.md §5): implementa
`application.ports.job_runner.JobRunner`. Cola local en memoria (un `queue.Queue` + un thread
worker daemon) que corre **un job a la vez**, cada uno como un subproceso
(`rio-search search run <config>` via `command_builder`, inyectable para tests offline sin tocar
Databricks) con su stdout/stderr combinados a un archivo de log (`data/jobs/<job_id>.log`) que
`stream_log()` puede tailear en vivo para `GET /api/jobs/{id}/log` (SSE).

Ademas de la cola (que solo serializa jobs *de este proceso*), cada ejecucion toma el
`ProcessLock` compartido (§5, aviso operativo de la Fase 3) antes de lanzar el subproceso y lo
libera al terminar -- asi un `rio-search search run` corrido a mano desde otra terminal tambien
queda serializado, no solo los jobs encolados por esta API.

**Nota de diseño (no persistente entre reinicios):** los `JobRecord` viven solo en memoria de
este proceso; si el backend se reinicia, la lista de jobs se pierde (los logs en disco
sobreviven, pero no quedan asociados a un job navegable por la API). Se acepta a proposito para
la Fase 4: la fuente de verdad de "que corrio y que resultado dio" es MLflow (`GET /api/runs`),
no la cola de jobs -- un job es solo el mecanismo para *lanzar* una búsqueda y ver su log en
vivo mientras corre. Si la Fase 5 (UI) necesita que la cola sobreviva un reinicio del backend
(p. ej. para no perder el job "Lanzar" si el usuario cierra la pestana), migrar `_records` a
`infrastructure.persistence.sqlite_cache` es directo (misma forma que el cache de lectura) --
queda documentado como pendiente, no bloqueante para el criterio de cierre de esta fase.
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from rio_search.application.ports.job_runner import JobRecord, JobStatus
from rio_search.infrastructure.jobs.process_lock import ProcessLock

CommandBuilder = Callable[[Path], list[str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubprocessJobRunner:
    """Implementa `application.ports.job_runner.JobRunner`."""

    def __init__(
        self,
        command_builder: CommandBuilder,
        log_dir: Path,
        lock: ProcessLock,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._command_builder = command_builder
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._lock = lock
        self._cwd = cwd
        self._env = env
        self._records: dict[str, JobRecord] = {}
        self._records_lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._run_worker, name="rio-search-job-worker", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # JobRunner
    # ------------------------------------------------------------------
    def submit(self, config_path: Path, label: str) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(
            job_id=job_id,
            label=label,
            config_path=str(config_path),
            status=JobStatus.QUEUED,
            created_at=_now_iso(),
        )
        with self._records_lock:
            self._records[job_id] = record
        self._queue.put(job_id)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._records_lock:
            return self._records.get(job_id)

    def list(self) -> list[JobRecord]:
        with self._records_lock:
            return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    def stream_log(self, job_id: str) -> Iterator[str]:
        log_path = self._log_path(job_id)
        while not log_path.exists():
            record = self.get(job_id)
            if record is None:
                return
            time.sleep(0.2)
        with log_path.open("r", encoding="utf-8", errors="replace") as f:
            while True:
                line = f.readline()
                if line:
                    yield line.rstrip("\n")
                    continue
                record = self.get(job_id)
                if record is None or record.status in (JobStatus.FINISHED, JobStatus.FAILED):
                    return
                time.sleep(0.3)

    # ------------------------------------------------------------------
    # worker
    # ------------------------------------------------------------------
    def _log_path(self, job_id: str) -> Path:
        return self._log_dir / f"{job_id}.log"

    def _update(self, job_id: str, **changes: object) -> None:
        with self._records_lock:
            current = self._records.get(job_id)
            if current is None:
                return
            self._records[job_id] = replace(current, **changes)  # type: ignore[arg-type]

    def _run_worker(self) -> None:
        while True:
            job_id = self._queue.get()
            self._execute(job_id)

    def _execute(self, job_id: str) -> None:
        record = self.get(job_id)
        if record is None:
            return

        self._update(job_id, status=JobStatus.RUNNING, started_at=_now_iso())
        # Un job a la vez, tambien contra un `rio-search` corrido a mano en otra terminal
        # (docstring del modulo): espera indefinidamente en vez de fallar el job.
        self._lock.acquire_blocking(label=f"api_job:{job_id}", poll_seconds=2.0, timeout_seconds=None)

        log_path = self._log_path(job_id)
        command = self._command_builder(Path(record.config_path))
        try:
            with log_path.open("w", encoding="utf-8") as log_file:
                # `encoding="utf-8"` explicito (Decision 044, verificado contra Databricks
                # real): sin esto, `subprocess.Popen(text=True)` decodifica el stdout del hijo
                # con `locale.getpreferredencoding()` (cp1252 en la consola de Windows) y revienta
                # con `UnicodeDecodeError` en los iconos unicode que MLflow imprime al terminar
                # un run (View run [ROCKET] ..., mismo caracter que `interfaces/cli/main.py` ya
                # reconfigura para *su propio* stdout -- eso no alcanza aca porque el problema
                # esta en como el proceso *padre* (este) decodifica el stdout del *hijo*).
                process = subprocess.Popen(
                    command,
                    cwd=str(self._cwd) if self._cwd else None,
                    env=self._env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                self._update(job_id, pid=process.pid)
                assert process.stdout is not None
                for line in process.stdout:
                    log_file.write(line)
                    log_file.flush()
                exit_code = process.wait()

            extra = _extract_extra(log_path)
            status = JobStatus.FINISHED if exit_code == 0 else JobStatus.FAILED
            self._update(job_id, status=status, ended_at=_now_iso(), exit_code=exit_code, extra=extra)
        except Exception as exc:  # noqa: BLE001 - un job que revienta no debe tumbar el worker
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"\n[job runner] excepcion no capturada: {exc!r}\n")
            self._update(job_id, status=JobStatus.FAILED, ended_at=_now_iso())
        finally:
            self._lock.release()


def _extract_extra(log_path: Path) -> dict[str, str]:
    """`search_run_id=<id> experiment=<path> trials=<n>` es exactamente lo que imprime
    `rio-search search run` al terminar (`interfaces/cli/main.py::search_run`) -- se parsea del
    log para que la API pueda devolver el `run_id` de MLflow sin que el `JobRunner` sepa nada de
    MLflow."""
    extra: dict[str, str] = {}
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return extra
    for line in text.splitlines():
        if "search_run_id=" in line:
            for token in line.split():
                if "=" in token:
                    key, _, value = token.partition("=")
                    extra[key] = value
            break
    return extra
