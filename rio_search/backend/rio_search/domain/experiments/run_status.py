"""`RunStatus`: estado de un `Search`/`Trial` (Fase 2, docs/rio_search_plan.md §3.2). Sin
dependencias del proyecto (regla de `domain`)."""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
