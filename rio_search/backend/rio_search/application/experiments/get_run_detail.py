"""`GetRunDetail` (Fase 4, docs/rio_search_plan.md §3.2, §3.9: pagina "Run" -- `GET
/api/runs/{id}`): un run puntual con sus hijos directos (`list_children`, §3.5) -- para un run
de búsqueda son sus trials; para un run de trial `per_horizon` son sus 8 runs de horizonte.
`None` si el `run_id` no existe (la API lo traduce a 404)."""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.application.ports.tracking_read import RunRecord, TrackingReadPort


@dataclass(frozen=True, slots=True)
class RunDetail:
    run: RunRecord
    children: tuple[RunRecord, ...]


@dataclass(frozen=True, slots=True)
class GetRunDetail:
    reader: TrackingReadPort

    def execute(self, run_id: str) -> RunDetail | None:
        run = self.reader.get_run(run_id)
        if run is None:
            return None
        children = tuple(self.reader.list_children(run_id, run.experiment_id))
        return RunDetail(run=run, children=children)
