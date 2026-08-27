"""`ListSearches` (Fase 4, docs/rio_search_plan.md §3.9: pagina "Búsquedas" -- `GET
/api/searches`): agrupa el resultado plano de `ListRuns` en búsquedas (runs sin
`mlflow.parentRunId`, §3.5) con sus trials directos anidados (runs cuyo `parent_run_id` es la
búsqueda). No baja al tercer nivel (horizontes de `per_horizon`): la pagina Búsquedas solo
necesita "búsquedas y sus trials" (§3.9); el detalle de horizontes vive en `GetRunDetail`, que
se pide por un `run_id` de trial puntual.

No esta nombrada explicitamente en el arbol de `application/experiments/` del plan (§3.2 solo
lista `ListRuns`, `CompareRuns`, `GetRunDetail`) pero es la composicion mas chica que resuelve
"Búsquedas (runs padre) y sus trials" sin que `interfaces/api` tenga que conocer el tag
`mlflow.parentRunId` (una fuga de MLflow hacia la capa de interfaces) -- se mantiene en el mismo
paquete y mismo patron (`@dataclass` con dependencias, `execute()`).
"""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.application.experiments.list_runs import ListRuns
from rio_search.application.ports.tracking_read import RunRecord


@dataclass(frozen=True, slots=True)
class SearchWithTrials:
    search: RunRecord
    trials: tuple[RunRecord, ...]


@dataclass(frozen=True, slots=True)
class ListSearches:
    list_runs: ListRuns

    def execute(
        self, families: tuple[str, ...] | None = None, max_results: int = 500
    ) -> list[SearchWithTrials]:
        records = self.list_runs.execute(families=families, max_results=max_results)
        by_id = {r.run_id: r for r in records}
        children_by_parent: dict[str, list[RunRecord]] = {}
        for record in records:
            parent = record.parent_run_id
            if parent is not None and parent in by_id:
                children_by_parent.setdefault(parent, []).append(record)

        searches = [r for r in records if r.parent_run_id is None]
        return [
            SearchWithTrials(search=search, trials=tuple(children_by_parent.get(search.run_id, ())))
            for search in searches
        ]
