"""`ModelFamily`: naive | sklearn | torch (Fase 2, docs/rio_search_plan.md §3.2, §3.3). Sin
dependencias del proyecto (regla de `domain`)."""

from __future__ import annotations

from enum import Enum


class ModelFamily(str, Enum):
    NAIVE = "naive"
    SKLEARN = "sklearn"
    TORCH = "torch"
