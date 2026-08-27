"""`Search`: agregado raiz del contexto Experiments (Fase 2, docs/rio_search_plan.md §3.2) --
un run padre de MLflow que explora una o mas configuraciones (`Trial`) sobre una misma
`DatasetVersion` pineada (Decision #10). "Un experimento simple es una busqueda de un solo
trial" (§0): en la Fase 2 (baselines naive) siempre hay exactamente un `Trial` por `Search`.
Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.domain.experiments.run_status import RunStatus
from rio_search.domain.experiments.trial import Trial


@dataclass(frozen=True, slots=True)
class Search:
    name: str
    experiment_path: str
    status: RunStatus
    trials: tuple[Trial, ...] = ()
    run_id: str | None = None
