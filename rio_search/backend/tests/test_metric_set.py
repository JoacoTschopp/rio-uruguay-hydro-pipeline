"""Tests de `domain.experiments.metric_set` (Fase 2, docs/rio_search_plan.md §3.5, §3.7):
formato jerarquico `{split}/{metrica}/h{NN}` + `{split}/{metrica}/mean`."""

from __future__ import annotations

import math

import pytest

from rio_search.domain.experiments.metric_set import HorizonMetrics, MetricSet


def _metric_set() -> MetricSet:
    return MetricSet(
        split="test",
        horizons=(
            HorizonMetrics(horizon=1, values={"rmse": 10.0, "kge": 0.5}, coverage=1.0),
            HorizonMetrics(horizon=14, values={"rmse": 20.0, "kge": float("nan")}, coverage=0.8),
        ),
    )


def test_as_mlflow_metrics_uses_two_digit_horizon_keys() -> None:
    out = _metric_set().as_mlflow_metrics()
    assert out["test/rmse/h01"] == 10.0
    assert out["test/rmse/h14"] == 20.0
    assert out["test/kge/h01"] == 0.5
    assert "test/kge/h14" not in out  # NaN se omite


def test_as_mlflow_metrics_includes_coverage_per_horizon() -> None:
    out = _metric_set().as_mlflow_metrics()
    assert out["test/coverage/h01"] == 1.0
    assert out["test/coverage/h14"] == 0.8


def test_mean_skips_nan() -> None:
    ms = _metric_set()
    assert ms.mean("rmse") == pytest.approx(15.0)
    assert ms.mean("kge") == pytest.approx(0.5)  # el NaN de h14 no cuenta


def test_mean_is_nan_when_all_values_missing() -> None:
    ms = _metric_set()
    assert math.isnan(ms.mean("no_existe"))


def test_as_mlflow_metrics_includes_mean_aggregate() -> None:
    out = _metric_set().as_mlflow_metrics()
    assert out["test/rmse/mean"] == pytest.approx(15.0)
    assert out["test/kge/mean"] == pytest.approx(0.5)


def test_horizon_lookup() -> None:
    ms = _metric_set()
    assert ms.horizon(14).get("rmse") == 20.0
    with pytest.raises(KeyError):
        ms.horizon(7)
