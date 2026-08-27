"""Tests offline de `application.predictions.promote_champion.PromoteChampion` (Fase 6):
`TrackingReadPort`/`ChampionStorePort`/`ModelAliasPort` falsos, sin tocar Databricks/MLflow."""

from __future__ import annotations

import pytest

from rio_search.application.ports.tracking_read import RunRecord
from rio_search.application.predictions.promote_champion import PromoteChampion
from rio_search.domain.predictions.champion import Champion
from rio_search.domain.shared.target_variable import TargetVariable


class FakeReader:
    def __init__(self, runs: dict[str, RunRecord]) -> None:
        self._runs = runs

    def get_run(self, run_id: str):
        return self._runs.get(run_id)

    def list_runs(self, experiment_names, max_results: int = 500):
        return list(self._runs.values())

    def list_children(self, parent_run_id: str, experiment_id: str, max_results: int = 200):
        return []

    def get_metric_history(self, run_id: str, metric_key: str):
        return []


class FakeChampionStore:
    def __init__(self) -> None:
        self.saved: list[Champion] = []

    def set(self, champion: Champion) -> None:
        self.saved.append(champion)

    def get(self, target: TargetVariable):
        return self.saved[-1] if self.saved else None

    def history(self, target: TargetVariable, max_results: int = 50):
        return list(reversed(self.saved))[:max_results]


class FakeModelAlias:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def set_alias(self, name: str, alias: str, version: str) -> None:
        self.calls.append((name, alias, version))


def _run(run_id: str, **overrides) -> RunRecord:
    tags = {
        "rio_search.model": "bilstm",
        "rio_search.target": "caudal",
        "rio_search.registered_model_name": "weather.ml.rio_search_bilstm",
        "rio_search.registered_model_version": "9",
    }
    tags.update(overrides.pop("tags", {}))
    metrics = {"val/kge/mean": 0.207}
    metrics.update(overrides.pop("metrics", {}))
    return RunRecord(
        run_id=run_id,
        experiment_id="exp-1",
        status="FINISHED",
        start_time_ms=0,
        end_time_ms=100,
        artifact_uri=f"dbfs:/{run_id}",
        tags=tags,
        params={},
        metrics=metrics,
    )


def test_promotes_a_real_run_and_sets_the_alias() -> None:
    reader = FakeReader({"run-9": _run("run-9")})
    store = FakeChampionStore()
    alias = FakeModelAlias()
    promote = PromoteChampion(reader=reader, store=store, model_alias=alias)

    champion = promote.execute(run_id="run-9", target=TargetVariable.CAUDAL, note="provisorio")

    assert champion.run_id == "run-9"
    assert champion.model_name == "bilstm"
    assert champion.metric_value == pytest.approx(0.207)
    assert champion.note == "provisorio"
    assert store.saved == [champion]
    assert alias.calls == [("weather.ml.rio_search_bilstm", "champion_caudal", "9")]


def test_does_not_set_alias_when_set_alias_is_false() -> None:
    reader = FakeReader({"run-9": _run("run-9")})
    store = FakeChampionStore()
    alias = FakeModelAlias()
    promote = PromoteChampion(reader=reader, store=store, model_alias=alias)

    promote.execute(run_id="run-9", target=TargetVariable.CAUDAL, set_alias=False)

    assert alias.calls == []
    assert len(store.saved) == 1


def test_does_not_require_a_model_alias_port() -> None:
    reader = FakeReader({"run-9": _run("run-9")})
    store = FakeChampionStore()
    promote = PromoteChampion(reader=reader, store=store, model_alias=None)

    champion = promote.execute(run_id="run-9", target=TargetVariable.CAUDAL)
    assert champion.run_id == "run-9"


def test_raises_when_run_does_not_exist() -> None:
    promote = PromoteChampion(reader=FakeReader({}), store=FakeChampionStore())
    with pytest.raises(ValueError, match="no existe"):
        promote.execute(run_id="missing", target=TargetVariable.CAUDAL)


def test_raises_when_run_has_no_model_tag() -> None:
    run_without_tags = RunRecord(
        run_id="run-9",
        experiment_id="exp-1",
        status="FINISHED",
        start_time_ms=0,
        end_time_ms=100,
        artifact_uri="dbfs:/run-9",
        tags={},
        params={},
        metrics={"val/kge/mean": 0.1},
    )
    reader = FakeReader({"run-9": run_without_tags})
    promote = PromoteChampion(reader=reader, store=FakeChampionStore())
    with pytest.raises(ValueError, match="rio_search.model"):
        promote.execute(run_id="run-9", target=TargetVariable.CAUDAL)


def test_raises_when_target_tag_mismatches() -> None:
    reader = FakeReader({"run-9": _run("run-9", tags={"rio_search.target": "nivel"})})
    promote = PromoteChampion(reader=reader, store=FakeChampionStore())
    with pytest.raises(ValueError, match="target"):
        promote.execute(run_id="run-9", target=TargetVariable.CAUDAL)


def test_raises_when_metric_missing() -> None:
    run_without_metric = RunRecord(
        run_id="run-9",
        experiment_id="exp-1",
        status="FINISHED",
        start_time_ms=0,
        end_time_ms=100,
        artifact_uri="dbfs:/run-9",
        tags={"rio_search.model": "bilstm", "rio_search.target": "caudal"},
        params={},
        metrics={},
    )
    reader = FakeReader({"run-9": run_without_metric})
    promote = PromoteChampion(reader=reader, store=FakeChampionStore())
    with pytest.raises(ValueError, match="val/kge/mean"):
        promote.execute(run_id="run-9", target=TargetVariable.CAUDAL)
