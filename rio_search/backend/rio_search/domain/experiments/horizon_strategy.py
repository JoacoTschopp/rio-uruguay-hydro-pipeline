"""`HorizonStrategy`: multi_output | per_horizon (Decision #2, docs/rio_search_plan.md §0, §3.3).

Solo el enum se adelanta a la Fase 1 porque `TargetBuilder` (contexto Datasets) lo necesita para
elegir la vista de la matriz de targets; el resto del contexto `experiments` (`Search`, `Trial`,
`ExperimentConfig`, ...) llega en la Fase 2. Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from enum import Enum


class HorizonStrategy(str, Enum):
    MULTI_OUTPUT = "multi_output"
    PER_HORIZON = "per_horizon"
