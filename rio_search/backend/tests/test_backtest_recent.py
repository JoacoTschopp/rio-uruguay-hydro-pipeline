"""Tests offline de `application.predictions.backtest_recent.BacktestRecent` (Fase 6, docs/
rio_search_plan.md §3.8, §3.9): `ForecastRepositoryPort`/`DatasetRepository` falsos, sin tocar
Databricks/MLflow."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from rio_search.application.predictions.backtest_recent import BacktestRecent
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.predictions.forecast import Forecast, ForecastPoint
from rio_search.domain.shared.target_variable import TargetVariable


class FakeForecastRepository:
    def __init__(self, forecasts: list[Forecast]) -> None:
        self._forecasts = forecasts

    def save(self, forecast: Forecast) -> None:
        self._forecasts.insert(0, forecast)

    def latest(self, target: TargetVariable):
        return self._forecasts[0] if self._forecasts else None

    def list_recent(self, target: TargetVariable, max_results: int = 30):
        return [f for f in self._forecasts if f.target == target][:max_results]


class FakeDatasetRepository:
    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df
        self.calls: list[str] = []

    def load(self, mode: str = "ensure_latest", force: bool = False):
        self.calls.append(mode)
        version = DatasetVersion(
            delta_version=268,
            sha256="a" * 64,
            rows=self._df.height,
            fecha_min="2026-08-01",
            fecha_max="2026-08-05",
            columns=tuple(self._df.columns),
        )
        return version, self._df


def _forecast(as_of: date, points: tuple[ForecastPoint, ...]) -> Forecast:
    return Forecast(
        target=TargetVariable.CAUDAL,
        as_of=as_of,
        issued_at=f"{as_of.isoformat()}T09:30:00+00:00",
        dataset_delta_version=268,
        dataset_sha256="a" * 64,
        champion_run_id="run-9",
        champion_model_name="bilstm",
        device_type="cuda",
        data_lag_days=1,
        points=points,
        forecast_run_id=f"forecast-{as_of.isoformat()}",
    )


def _dataset() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "fecha": [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)],
            "caudal_actual_m3s": [1000.0, 1005.0, None, 1020.0],
        }
    )


def test_returns_empty_tuple_when_no_forecasts() -> None:
    backtest = BacktestRecent(
        forecast_repository=FakeForecastRepository([]), dataset_repository=FakeDatasetRepository(_dataset())
    )
    assert backtest.execute(TargetVariable.CAUDAL) == ()


def test_matches_observed_values_by_target_date() -> None:
    forecast = _forecast(
        date(2026, 8, 1),
        (
            ForecastPoint(horizon=1, target_date=date(2026, 8, 2), value=999.0),
            ForecastPoint(horizon=3, target_date=date(2026, 8, 4), value=1015.0),
        ),
    )
    dataset_repo = FakeDatasetRepository(_dataset())
    backtest = BacktestRecent(
        forecast_repository=FakeForecastRepository([forecast]), dataset_repository=dataset_repo
    )

    points = backtest.execute(TargetVariable.CAUDAL)

    assert len(points) == 2
    by_horizon = {p.horizon: p for p in points}
    assert by_horizon[1].observed == 1005.0
    assert by_horizon[1].error == pytest.approx(1005.0 - 999.0)
    assert by_horizon[3].observed == 1020.0
    assert by_horizon[3].error == pytest.approx(1020.0 - 1015.0)
    assert dataset_repo.calls == ["offline"]  # nunca vuelve a pegarle a Databricks


def test_pending_target_dates_have_no_observed_value() -> None:
    forecast = _forecast(
        date(2026, 8, 1),
        (
            ForecastPoint(horizon=2, target_date=date(2026, 8, 3), value=1000.0),  # nulo en Gold
            ForecastPoint(horizon=9, target_date=date(2026, 8, 20), value=1000.0),  # todavia no llego
        ),
    )
    backtest = BacktestRecent(
        forecast_repository=FakeForecastRepository([forecast]),
        dataset_repository=FakeDatasetRepository(_dataset()),
    )
    points = backtest.execute(TargetVariable.CAUDAL)
    assert all(p.observed is None and p.error is None and p.abs_error is None for p in points)
