"""Tests offline de `infrastructure.persistence.champion_store.SqliteChampionStore` (Fase 6):
sqlite3 puro sobre `tmp_path`, sin tocar Databricks/MLflow (mismo patron que
`tests/test_sqlite_cache.py`, Fase 4)."""

from __future__ import annotations

from pathlib import Path

from rio_search.domain.predictions.champion import Champion
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.persistence.champion_store import SqliteChampionStore


def _champion(run_id: str, promoted_at: str, metric_value: float = 0.2) -> Champion:
    return Champion(
        target=TargetVariable.CAUDAL,
        run_id=run_id,
        model_name="bilstm",
        metric_name="val/kge/mean",
        metric_value=metric_value,
        promoted_at=promoted_at,
        registered_model_name="weather.ml.rio_search_bilstm",
        registered_model_version="9",
        note="campeon provisorio",
    )


def test_get_returns_none_when_nothing_promoted(tmp_path: Path) -> None:
    store = SqliteChampionStore(tmp_path / "champions.sqlite3")
    assert store.get(TargetVariable.CAUDAL) is None


def test_set_and_get_round_trip(tmp_path: Path) -> None:
    store = SqliteChampionStore(tmp_path / "champions.sqlite3")
    champion = _champion("run-9", "2026-08-27T18:00:00+00:00")
    store.set(champion)
    fetched = store.get(TargetVariable.CAUDAL)
    assert fetched == champion


def test_set_overwrites_current_champion_but_keeps_history(tmp_path: Path) -> None:
    store = SqliteChampionStore(tmp_path / "champions.sqlite3")
    first = _champion("run-9", "2026-08-27T18:00:00+00:00")
    second = _champion("run-10", "2026-08-28T09:00:00+00:00", metric_value=0.25)
    store.set(first)
    store.set(second)

    assert store.get(TargetVariable.CAUDAL) == second
    history = store.history(TargetVariable.CAUDAL)
    assert [c.run_id for c in history] == ["run-10", "run-9"]


def test_targets_are_independent(tmp_path: Path) -> None:
    store = SqliteChampionStore(tmp_path / "champions.sqlite3")
    caudal_champion = _champion("run-caudal", "2026-08-27T18:00:00+00:00")
    store.set(caudal_champion)
    assert store.get(TargetVariable.NIVEL) is None
    assert store.get(TargetVariable.CAUDAL) == caudal_champion


def test_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "champions.sqlite3"
    SqliteChampionStore(path).set(_champion("run-9", "2026-08-27T18:00:00+00:00"))
    reopened = SqliteChampionStore(path)
    assert reopened.get(TargetVariable.CAUDAL).run_id == "run-9"
