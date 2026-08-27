"""Puerto de **lectura** de MLflow (Fase 4, docs/rio_search_plan.md §3.9, §5): la contraparte de
`application.ports.tracking.TrackingPort` (que solo escribe). La API HTTP (Búsquedas, Run,
Comparar) necesita listar y leer runs ya logueados -- nunca escribe -- así que este puerto separa
esa responsabilidad en vez de sobrecargar `TrackingPort` con métodos que `RunSearch` no usa.

`RunRecord` es un DTO de infraestructura (no un agregado de dominio): expone exactamente lo que
`mlflow.tracking.MlflowClient` devuelve (tags/params/metrics ya "aplanados", sin reconstruir
`Search`/`Trial`/`MetricSet` de `domain.experiments`) porque la jerarquía búsqueda -> trial ->
horizonte (§3.5) no está en un campo dedicado de MLflow: se infiere del tag `mlflow.parentRunId`
que MLflow setea solo al anidar (`start_run(nested=True)`). Reconstruir esa jerarquía es trabajo
de aplicación (`application.experiments.list_searches`), no de este puerto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

MLFLOW_PARENT_RUN_ID_TAG = "mlflow.parentRunId"
MLFLOW_RUN_NAME_TAG = "mlflow.runName"


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    experiment_id: str
    status: str  # "RUNNING" | "FINISHED" | "FAILED" | "KILLED" (mlflow.entities.RunStatus)
    start_time_ms: int | None
    end_time_ms: int | None
    artifact_uri: str
    tags: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def run_name(self) -> str:
        return self.tags.get(MLFLOW_RUN_NAME_TAG, self.run_id)

    @property
    def parent_run_id(self) -> str | None:
        return self.tags.get(MLFLOW_PARENT_RUN_ID_TAG)

    def rio_search_tag(self, name: str) -> str | None:
        """Tag `rio_search.<name>` (§3.5) sin el prefijo -- el mismo nombre que recibe
        `TrackingPort.set_tags`."""
        return self.tags.get(f"rio_search.{name}")


@dataclass(frozen=True, slots=True)
class MetricPoint:
    step: int
    timestamp_ms: int
    value: float


class TrackingReadPort(Protocol):
    def list_runs(self, experiment_names: Sequence[str], max_results: int = 500) -> list[RunRecord]:
        """Todos los runs (búsqueda + trial + horizonte, sin distinguir) de los experimentos
        pedidos, más recientes primero. `experiment_names` que no existen se saltan en
        silencio (un experimento nuevo, p. ej. `daily_forecast`, puede no existir todavía)."""
        ...

    def get_run(self, run_id: str) -> RunRecord | None:
        """`None` si el run no existe (borrado o `run_id` inválido) en vez de excepción --
        la API lo traduce a 404."""
        ...

    def list_children(
        self, parent_run_id: str, experiment_id: str, max_results: int = 200
    ) -> list[RunRecord]:
        """Runs hijos directos de `parent_run_id` (trials de una búsqueda, u horizontes de un
        trial `per_horizon`, §3.5) -- filtra por el tag `mlflow.parentRunId` que MLflow setea
        solo en `start_run(nested=True)`. Un nivel a la vez: para la jerarquía completa
        búsqueda -> trial -> horizonte, `application.experiments` llama esto dos veces."""
        ...

    def get_metric_history(self, run_id: str, metric_key: str) -> list[MetricPoint]:
        ...
