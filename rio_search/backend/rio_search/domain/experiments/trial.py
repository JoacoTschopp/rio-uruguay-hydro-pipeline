"""`Trial`: una configuracion de modelo evaluada dentro de un `Search` (Fase 2,
docs/rio_search_plan.md §0, §3.2) -- un run hijo de MLflow (nested=True). Carga sus metricas de
`val`/`test` ya calculadas para que el resultado de `RunSearch` sea autocontenido (no hace falta
volver a pegarle a MLflow para leer lo que la propia corrida acaba de loguear). Sin dependencias
del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.domain.experiments.metric_set import MetricSet
from rio_search.domain.experiments.run_status import RunStatus
from rio_search.domain.models.model_spec import ModelSpec


@dataclass(frozen=True, slots=True)
class Trial:
    name: str
    model: ModelSpec
    status: RunStatus
    run_id: str | None = None
    val_metrics: MetricSet | None = None
    test_metrics: MetricSet | None = None
