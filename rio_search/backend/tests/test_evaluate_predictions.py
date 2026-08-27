"""Tests de `application.experiments.evaluate_predictions.EvaluatePredictions` (Fase 2)."""

from __future__ import annotations

import numpy as np
import pytest

from rio_search.application.experiments.evaluate_predictions import EvaluatePredictions


def test_execute_builds_one_horizon_metrics_per_horizon() -> None:
    y_true = np.array([[10.0, 20.0], [12.0, 22.0], [11.0, 19.0]])
    y_pred = np.array([[10.0, 20.0], [12.0, 22.0], [11.0, 19.0]])  # prediccion perfecta
    y_ref = np.array([[9.0, 18.0], [11.0, 21.0], [10.0, 20.0]])

    result = EvaluatePredictions().execute("test", (1, 7), y_true, y_pred, y_ref)

    assert result.split == "test"
    assert [hm.horizon for hm in result.horizons] == [1, 7]
    for hm in result.horizons:
        assert hm.get("nse") == pytest.approx(1.0)
        assert hm.get("rmse") == pytest.approx(0.0)
        assert hm.coverage == pytest.approx(1.0)


def test_execute_skill_vs_persistence_zero_when_prediction_equals_reference() -> None:
    y_true = np.array([[10.0], [15.0], [9.0], [20.0]])
    y_pred = np.array([[9.0], [16.0], [8.0], [19.0]])
    y_ref = y_pred.copy()  # el modelo evaluado ES la referencia

    result = EvaluatePredictions().execute("test", (1,), y_true, y_pred, y_ref)

    assert result.horizon(1).get("skill_vs_persistence") == 0.0
