"""Tests offline de `application.experiments.{list_runs,list_searches,get_run_detail,
compare_runs}` (Fase 4, docs/rio_search_plan.md §3.2, §3.9): un `TrackingReadPort` falso con una
jerarquia sintetica busqueda -> trial -> horizonte (§3.5), sin tocar Databricks/MLflow real."""

from __future__ import annotations

from rio_search.application.experiments.compare_runs import CompareRuns
from rio_search.application.experiments.get_run_detail import GetRunDetail
from rio_search.application.experiments.list_runs import DEFAULT_EXPERIMENT_FAMILIES, ListRuns
from rio_search.application.experiments.list_searches import ListSearches
from rio_search.application.ports.tracking_read import RunRecord

BASE_PATH = "/Users/test@example.com/rio_search"


def _run(run_id: str, parent: str | None, start_ms: int, **kwargs) -> RunRecord:
    tags = {"mlflow.runName": run_id}
    if parent is not None:
        tags["mlflow.parentRunId"] = parent
    tags.update(kwargs.pop("tags", {}))
    return RunRecord(
        run_id=run_id,
        experiment_id="exp-1",
        status=kwargs.pop("status", "FINISHED"),
        start_time_ms=start_ms,
        end_time_ms=start_ms + 100,
        artifact_uri=f"dbfs:/{run_id}",
        tags=tags,
        params=kwargs.pop("params", {}),
        metrics=kwargs.pop("metrics", {}),
    )


class FakeReader:
    def __init__(self, runs: list[RunRecord]) -> None:
        self._runs = {r.run_id: r for r in runs}

    def list_runs(self, experiment_names, max_results: int = 500) -> list[RunRecord]:
        return list(self._runs.values())

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_children(
        self, parent_run_id: str, experiment_id: str, max_results: int = 200
    ) -> list[RunRecord]:
        return [r for r in self._runs.values() if r.parent_run_id == parent_run_id]

    def get_metric_history(self, run_id: str, metric_key: str):
        return []


def _hierarchy() -> list[RunRecord]:
    search = _run("search-1", None, 300)
    trial_a = _run("trial-a", "search-1", 200, params={"model.name": "bilstm"})
    trial_b = _run("trial-b", "search-1", 100, params={"model.name": "persistence"})
    horizon = _run("h01", "trial-a", 250)
    return [search, trial_a, trial_b, horizon]


def test_list_runs_returns_all_records_newest_first() -> None:
    reader = FakeReader(_hierarchy())
    list_runs = ListRuns(reader=reader, base_path=BASE_PATH)

    records = list_runs.execute()

    assert [r.run_id for r in records] == ["search-1", "h01", "trial-a", "trial-b"]


def test_list_runs_default_families_match_documented_set() -> None:
    # fase_estrategias se sumo 2026-09-18: migracion de las 26 celdas del framework rio_search/
    # (feature/fase-estrategias) a MLflow, para que aparezcan en Busquedas sin filtro manual.
    assert DEFAULT_EXPERIMENT_FAMILIES == ("baselines", "bilstm", "smoke", "daily_forecast", "fase_estrategias")


def test_list_searches_groups_direct_trials_only() -> None:
    reader = FakeReader(_hierarchy())
    list_searches = ListSearches(list_runs=ListRuns(reader=reader, base_path=BASE_PATH))

    results = list_searches.execute()

    assert len(results) == 1
    assert results[0].search.run_id == "search-1"
    trial_ids = sorted(t.run_id for t in results[0].trials)
    assert trial_ids == ["trial-a", "trial-b"]  # h01 (nieto de trial-a) no aparece aca


def test_get_run_detail_returns_children_of_a_search() -> None:
    reader = FakeReader(_hierarchy())
    detail = GetRunDetail(reader=reader).execute("search-1")

    assert detail is not None
    assert detail.run.run_id == "search-1"
    assert sorted(c.run_id for c in detail.children) == ["trial-a", "trial-b"]


def test_get_run_detail_returns_none_for_unknown_run() -> None:
    reader = FakeReader(_hierarchy())
    assert GetRunDetail(reader=reader).execute("nope") is None


def test_get_run_detail_returns_horizon_children_of_a_trial() -> None:
    reader = FakeReader(_hierarchy())
    detail = GetRunDetail(reader=reader).execute("trial-a")

    assert detail is not None
    assert [c.run_id for c in detail.children] == ["h01"]


def test_compare_runs_reports_missing_ids_and_param_diff() -> None:
    reader = FakeReader(_hierarchy())
    comparison = CompareRuns(reader=reader).execute(["trial-a", "trial-b", "nope"])

    assert comparison.missing_run_ids == ("nope",)
    assert [r.run_id for r in comparison.runs] == ["trial-a", "trial-b"]
    assert comparison.param_diff == {
        "model.name": {"trial-a": "bilstm", "trial-b": "persistence"},
    }


def test_compare_runs_omits_params_that_are_identical() -> None:
    reader = FakeReader(
        [
            _run("a", None, 1, params={"seed": "42", "model.name": "x"}),
            _run("b", None, 2, params={"seed": "42", "model.name": "y"}),
        ]
    )
    comparison = CompareRuns(reader=reader).execute(["a", "b"])

    assert "seed" not in comparison.param_diff
    assert comparison.param_diff["model.name"] == {"a": "x", "b": "y"}
