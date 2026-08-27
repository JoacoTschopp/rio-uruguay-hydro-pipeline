"""Tests offline del dominio `predictions` (Fase 6, docs/rio_search_plan.md §3.2, §3.8):
`Champion`, `Forecast`/`ForecastPoint`, `AsOfPolicy`. Sin dependencias del proyecto (regla de
`domain`), sin tocar Databricks/MLflow."""

from __future__ import annotations

from datetime import date

import pytest

from rio_search.domain.predictions.as_of_policy import AsOfPolicy
from rio_search.domain.predictions.champion import Champion
from rio_search.domain.predictions.forecast import Forecast, ForecastPoint
from rio_search.domain.shared.target_variable import TargetVariable


def test_champion_as_tags_includes_registered_model_when_present() -> None:
    champion = Champion(
        target=TargetVariable.CAUDAL,
        run_id="run-1",
        model_name="bilstm",
        metric_name="val/kge/mean",
        metric_value=0.207,
        promoted_at="2026-08-27T18:00:00+00:00",
        registered_model_name="weather.ml.rio_search_bilstm",
        registered_model_version="9",
        note="campeon provisorio",
    )
    tags = champion.as_tags()
    assert tags["champion_run_id"] == "run-1"
    assert tags["champion_metric_value"] == "0.207000"
    assert tags["champion_registered_model_name"] == "weather.ml.rio_search_bilstm"
    assert tags["champion_registered_model_version"] == "9"


def test_champion_as_tags_without_registered_model() -> None:
    champion = Champion(
        target=TargetVariable.CAUDAL,
        run_id="run-1",
        model_name="persistence",
        metric_name="val/kge/mean",
        metric_value=0.0,
        promoted_at="2026-08-27T18:00:00+00:00",
    )
    tags = champion.as_tags()
    assert "champion_registered_model_name" not in tags


def test_forecast_point_for_and_horizons() -> None:
    forecast = Forecast(
        target=TargetVariable.CAUDAL,
        as_of=date(2026, 8, 23),
        issued_at="2026-08-27T09:30:00+00:00",
        dataset_delta_version=268,
        dataset_sha256="a" * 64,
        champion_run_id="run-1",
        champion_model_name="bilstm",
        device_type="cuda",
        data_lag_days=4,
        points=(
            ForecastPoint(horizon=2, target_date=date(2026, 8, 25), value=1200.0),
            ForecastPoint(horizon=1, target_date=date(2026, 8, 24), value=1100.0),
        ),
    )
    assert forecast.horizons == (1, 2)
    assert forecast.point_for(1).value == 1100.0
    with pytest.raises(KeyError):
        forecast.point_for(99)


def test_forecast_rejects_duplicate_horizons() -> None:
    with pytest.raises(ValueError):
        Forecast(
            target=TargetVariable.CAUDAL,
            as_of=date(2026, 8, 23),
            issued_at="2026-08-27T09:30:00+00:00",
            dataset_delta_version=268,
            dataset_sha256="a" * 64,
            champion_run_id="run-1",
            champion_model_name="bilstm",
            device_type="cpu",
            data_lag_days=0,
            points=(
                ForecastPoint(horizon=1, target_date=date(2026, 8, 24), value=1.0),
                ForecastPoint(horizon=1, target_date=date(2026, 8, 24), value=2.0),
            ),
        )


def test_forecast_rejects_empty_points() -> None:
    with pytest.raises(ValueError):
        Forecast(
            target=TargetVariable.CAUDAL,
            as_of=date(2026, 8, 23),
            issued_at="2026-08-27T09:30:00+00:00",
            dataset_delta_version=268,
            dataset_sha256="a" * 64,
            champion_run_id="run-1",
            champion_model_name="bilstm",
            device_type="cpu",
            data_lag_days=0,
            points=(),
        )


def test_forecast_as_tags() -> None:
    forecast = Forecast(
        target=TargetVariable.CAUDAL,
        as_of=date(2026, 8, 23),
        issued_at="2026-08-27T09:30:00+00:00",
        dataset_delta_version=268,
        dataset_sha256="a" * 64,
        champion_run_id="run-1",
        champion_model_name="bilstm",
        device_type="cuda",
        data_lag_days=4,
        points=(ForecastPoint(horizon=1, target_date=date(2026, 8, 24), value=1100.0),),
    )
    tags = forecast.as_tags()
    assert tags["as_of"] == "2026-08-23"
    assert tags["data_lag_days"] == "4"
    assert tags["device"] == "cuda"


def test_as_of_policy_data_lag_days() -> None:
    policy = AsOfPolicy(max_ffill_days=3)
    assert policy.data_lag_days(date(2026, 8, 23), date(2026, 8, 27)) == 4
    assert policy.data_lag_days(date(2026, 8, 27), date(2026, 8, 27)) == 0


def test_as_of_policy_rejects_future_as_of() -> None:
    policy = AsOfPolicy()
    with pytest.raises(ValueError):
        policy.data_lag_days(date(2026, 8, 28), date(2026, 8, 27))


def test_as_of_policy_rejects_negative_max_ffill_days() -> None:
    with pytest.raises(ValueError):
        AsOfPolicy(max_ffill_days=-1)
