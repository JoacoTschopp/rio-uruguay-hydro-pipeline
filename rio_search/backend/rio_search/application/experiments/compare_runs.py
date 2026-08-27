"""`CompareRuns` (Fase 4, docs/rio_search_plan.md §3.2, §3.9: pagina "Comparar" -- `GET
/api/runs/compare?ids=`): N runs lado a lado, mas el diff de sus `params` (config YAML aplanada,
§3.5) -- "tabla comparativa, diff de configs". Los runs pedidos que no existen se saltan (no
rompe la comparacion de los que si existen; la API reporta cuales faltaron)."""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.application.ports.tracking_read import RunRecord, TrackingReadPort


@dataclass(frozen=True, slots=True)
class RunComparison:
    runs: tuple[RunRecord, ...]
    missing_run_ids: tuple[str, ...]
    param_diff: dict[str, dict[str, str | None]]  # {param_name: {run_id: value|None}}


@dataclass(frozen=True, slots=True)
class CompareRuns:
    reader: TrackingReadPort

    def execute(self, run_ids: list[str]) -> RunComparison:
        runs: list[RunRecord] = []
        missing: list[str] = []
        for run_id in run_ids:
            record = self.reader.get_run(run_id)
            if record is None:
                missing.append(run_id)
            else:
                runs.append(record)

        all_param_names: set[str] = set()
        for run in runs:
            all_param_names.update(run.params.keys())

        param_diff: dict[str, dict[str, str | None]] = {}
        for name in sorted(all_param_names):
            values = {run.run_id: run.params.get(name) for run in runs}
            if len(set(values.values())) > 1:  # solo los params que difieren entre corridas
                param_diff[name] = values

        return RunComparison(runs=tuple(runs), missing_run_ids=tuple(missing), param_diff=param_diff)
