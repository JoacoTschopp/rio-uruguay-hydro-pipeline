"""Tests offline de `infrastructure.persistence.forecast_repository.SqliteForecastRepository`
(Fase 6, docs/rio_search_plan.md §3.8 paso 4): SQLite + parquet en `tmp_path`, sin tocar
Databricks/MLflow."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from rio_search.domain.predictions.forecast import Forecast, ForecastPoint
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.persistence.forecast_repository import SqliteForecastRepository


def _forecast(as_of: date, issued_at: str) -> Forecast:
    return Forecast(
        target=TargetVariable.CAUDAL,
        as_of=as_of,
        issued_at=issued_at,
        dataset_delta_version=268,
        dataset_sha256="a" * 64,
        champion_run_id="run-9",
        champion_model_name="bilstm",
        device_type="cuda",
        data_lag_days=1,
        points=(
            ForecastPoint(horizon=1, target_date=date(as_of.year, as_of.month, as_of.day), value=1000.0),
            ForecastPoint(horizon=2, target_date=date(as_of.year, as_of.month, as_of.day), value=1010.0),
        ),
        forecast_run_id="forecast-run-1",
    )


def test_latest_returns_none_when_empty(tmp_path: Path) -> None:
    repo = SqliteForecastRepository(tmp_path / "forecasts.sqlite3", tmp_path / "parquet")
    assert repo.latest(TargetVariable.CAUDAL) is None


def test_save_and_latest_round_trip(tmp_path: Path) -> None:
    repo = SqliteForecastRepository(tmp_path / "forecasts.sqlite3", tmp_path / "parquet")
    forecast = _forecast(date(2026, 8, 23), "2026-08-27T09:30:00+00:00")
    repo.save(forecast)

    latest = repo.latest(TargetVariable.CAUDAL)
    assert latest == forecast


def test_save_writes_a_parquet_file(tmp_path: Path) -> None:
    parquet_dir = tmp_path / "parquet"
    repo = SqliteForecastRepository(tmp_path / "forecasts.sqlite3", parquet_dir)
    forecast = _forecast(date(2026, 8, 23), "2026-08-27T09:30:00+00:00")
    repo.save(forecast)

    files = list(parquet_dir.glob("*.parquet"))
    assert len(files) == 1
    df = pl.read_parquet(files[0])
    assert df.height == 2
    assert set(df["horizonte"].to_list()) == {1, 2}


def test_list_recent_orders_most_recent_first(tmp_path: Path) -> None:
    repo = SqliteForecastRepository(tmp_path / "forecasts.sqlite3", tmp_path / "parquet")
    older = _forecast(date(2026, 8, 22), "2026-08-26T09:30:00+00:00")
    newer = _forecast(date(2026, 8, 23), "2026-08-27T09:30:00+00:00")
    repo.save(older)
    repo.save(newer)

    recent = repo.list_recent(TargetVariable.CAUDAL, max_results=10)
    assert [f.as_of for f in recent] == [date(2026, 8, 23), date(2026, 8, 22)]


def test_targets_are_independent(tmp_path: Path) -> None:
    repo = SqliteForecastRepository(tmp_path / "forecasts.sqlite3", tmp_path / "parquet")
    caudal = _forecast(date(2026, 8, 23), "2026-08-27T09:30:00+00:00")
    repo.save(caudal)
    assert repo.latest(TargetVariable.NIVEL) is None
    assert repo.latest(TargetVariable.CAUDAL) == caudal
