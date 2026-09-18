"""`ListRuns` (Fase 4, docs/rio_search_plan.md §3.2, §3.9): caso de uso de solo lectura detras de
`GET /api/runs`. Lista runs de uno o mas "familias" de experimento (`baselines`, `bilstm`,
`smoke`, `daily_forecast`, §3.5) sin distinguir todavia si cada uno es una búsqueda (run padre),
un trial o un horizonte -- esa jerarquía la arma `ListSearches`/`GetRunDetail` a partir del tag
`mlflow.parentRunId` (§3.5, `application.ports.tracking_read`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from rio_search.application.ports.tracking_read import RunRecord, TrackingReadPort

# Familias documentadas en §3.5: "Experimentos: /Users/<profile>/rio_search/<familia> --
# baselines, bilstm, <modelo_futuro>, daily_forecast, smoke." `daily_forecast` llega recien en
# la Fase 6 pero listarla ya no hace dano (`TrackingReadPort.list_runs` salta experimentos que
# todavia no existen). `fase_estrategias` se agrega por la migracion de la fase de busqueda de
# modelos del framework rio_search/ (feature/fase-estrategias, 26 trials, campana d303).
DEFAULT_EXPERIMENT_FAMILIES: tuple[str, ...] = (
    "baselines",
    "bilstm",
    "smoke",
    "daily_forecast",
    "fase_estrategias",
)


@dataclass(frozen=True, slots=True)
class ListRuns:
    reader: TrackingReadPort
    base_path: str  # p. ej. "/Users/joaquintschopp@gmail.com/rio_search" (sin barra final)

    def execute(
        self, families: Sequence[str] | None = None, max_results: int = 500
    ) -> list[RunRecord]:
        families = tuple(families) if families else DEFAULT_EXPERIMENT_FAMILIES
        experiment_names = [f"{self.base_path}/{family}" for family in families]
        records = self.reader.list_runs(experiment_names, max_results=max_results)
        return sorted(records, key=lambda r: r.start_time_ms or 0, reverse=True)
