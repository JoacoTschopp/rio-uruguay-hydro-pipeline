"""`JobRunner` (Fase 4, docs/rio_search_plan.md §3.2, §3.9: pagina "Lanzar" -- `POST /api/jobs`,
`GET /api/jobs/{id}/log`): cola local de trabajos pesados (una búsqueda completa, `rio-search
search run <config>`) que la API dispara y sigue en vivo, **uno a la vez** -- el aviso operativo
de la Fase 3 (`docs/rio_search_plan.md`, fila de Notas): dos procesos de Rio_Search contra
Databricks/MLflow con el mismo perfil CLI al mismo tiempo compiten por el cache de tokens OAuth
en Windows y uno falla con 401. `SubprocessJobRunner` (infrastructure) es la unica
implementacion; este puerto existe para que `interfaces/api` no dependa de `subprocess` ni de
como se logra la exclusion mutua, y para que los tests de la API puedan inyectar un `JobRunner`
falso sin lanzar procesos de verdad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterator, Protocol


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    label: str
    config_path: str  # ruta relativa a configs/experiments/, tal como la pidio POST /api/jobs
    status: JobStatus
    created_at: str  # ISO 8601 UTC
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    pid: int | None = None
    # p. ej. {"search_run_id": "..."} si se parseo del log del proceso al terminar.
    extra: dict[str, str] = field(default_factory=dict)


class JobRunner(Protocol):
    def submit(self, config_path: Path, label: str) -> JobRecord:
        """Encola una búsqueda (`rio-search search run <config_path>`). No bloquea: el trabajo
        real corre en un worker en background, un job a la vez (ver docstring del modulo)."""
        ...

    def get(self, job_id: str) -> JobRecord | None:
        ...

    def list(self) -> list[JobRecord]:
        """Mas recientes primero."""
        ...

    def stream_log(self, job_id: str) -> Iterator[str]:
        """Lineas de log del job, empezando desde el principio del archivo. Sigue produciendo
        lineas nuevas mientras el job no termino (`QUEUED`/`RUNNING`); termina el generador
        cuando el job llega a un estado final (`FINISHED`/`FAILED`) y no hay mas lineas nuevas
        que leer -- `interfaces/api` lo envuelve en un `StreamingResponse` de SSE."""
        ...
