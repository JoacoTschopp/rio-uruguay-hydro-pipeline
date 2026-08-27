"""Tests de `infrastructure.evaluation.metrics` (Fase 2, docs/rio_search_plan.md §3.7, §5):
"funciones puras + tests con valores conocidos (NSE = 1 en prediccion perfecta, KGE de la media
= -0,41, etc.)"."""

from __future__ import annotations

import math

import numpy as np
import pytest

from rio_search.infrastructure.evaluation import metrics


def test_nse_is_one_for_perfect_prediction() -> None:
    obs = np.array([10.0, 20.0, 30.0, 15.0, 25.0])
    assert metrics.nse(obs, obs) == pytest.approx(1.0)


def test_nse_is_nan_when_observed_variance_is_zero() -> None:
    obs = np.array([5.0, 5.0, 5.0])
    assert math.isnan(metrics.nse(obs, np.array([1.0, 2.0, 3.0])))


def test_kge_of_predicting_the_mean_is_minus_0_41() -> None:
    """Resultado conocido (Knoben et al. 2019, citado en el plan §5): predecir siempre la
    media de lo observado da KGE = 1 - sqrt(2) ~= -0.41421 (r=0 por convencion cuando la
    prediccion es constante, alpha=0, beta=1)."""
    rng = np.random.default_rng(42)
    obs = rng.normal(loc=1000.0, scale=250.0, size=200)
    sim = np.full_like(obs, obs.mean())
    assert metrics.kge(obs, sim) == pytest.approx(1.0 - math.sqrt(2.0), abs=1e-9)


def test_kge_is_one_for_perfect_prediction() -> None:
    obs = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    assert metrics.kge(obs, obs) == pytest.approx(1.0)


def test_rmse_and_mae_known_values() -> None:
    obs = np.array([10.0, 20.0, 30.0])
    sim = np.array([12.0, 18.0, 33.0])
    # errores: 2, -2, 3 -> mae = (2+2+3)/3; rmse = sqrt((4+4+9)/3)
    assert metrics.mae(obs, sim) == pytest.approx(7.0 / 3.0)
    assert metrics.rmse(obs, sim) == pytest.approx(math.sqrt(17.0 / 3.0))


def test_mape_known_value() -> None:
    obs = np.array([100.0, 200.0])
    sim = np.array([110.0, 180.0])
    # |10|/100=0.10, |20|/200=0.10 -> 10%
    assert metrics.mape(obs, sim) == pytest.approx(10.0)


def test_mape_excludes_zero_observed() -> None:
    obs = np.array([0.0, 100.0])
    sim = np.array([5.0, 90.0])
    assert metrics.mape(obs, sim) == pytest.approx(10.0)


def test_pbias_known_value() -> None:
    obs = np.array([100.0, 100.0])
    sim = np.array([110.0, 90.0])
    assert metrics.pbias(obs, sim) == pytest.approx(0.0)
    sim_biased = np.array([110.0, 110.0])
    assert metrics.pbias(obs, sim_biased) == pytest.approx(10.0)


def test_r_squared_is_one_for_perfect_linear_relationship() -> None:
    obs = np.array([1.0, 2.0, 3.0, 4.0])
    sim = obs * 2.0 + 1.0
    assert metrics.r_squared(obs, sim) == pytest.approx(1.0)


def test_peak_error_uses_top_fraction_of_observed() -> None:
    obs = np.array([1.0, 2.0, 3.0, 4.0, 100.0])  # top 5% (min k=1) -> el pico es 100.0
    sim = np.array([1.0, 2.0, 3.0, 4.0, 90.0])
    peak = metrics.peak_error(obs, sim, top_fraction=0.05)
    assert peak["n"] == 1.0
    assert peak["mae"] == pytest.approx(10.0)
    assert peak["bias"] == pytest.approx(-10.0)


def test_skill_score_of_persistence_vs_itself_is_exactly_zero() -> None:
    """Criterio de cierre de la Fase 2 (§5): "skill de persistencia = 0 por construccion".
    Verificado aca como propiedad matematica de `skill_score`, no solo de `RunSearch`."""
    obs = np.array([10.0, 20.0, 30.0, 5.0])
    sim = np.array([9.0, 22.0, 28.0, 6.0])
    model_rmse = metrics.rmse(obs, sim)
    assert metrics.skill_score(model_rmse, model_rmse) == 0.0


def test_skill_score_positive_when_model_beats_reference() -> None:
    assert metrics.skill_score(rmse_model=5.0, rmse_reference=10.0) == pytest.approx(0.5)


def test_skill_score_nan_when_reference_rmse_is_zero() -> None:
    assert math.isnan(metrics.skill_score(rmse_model=5.0, rmse_reference=0.0))


def test_metrics_ignore_non_finite_pairs() -> None:
    obs = np.array([10.0, np.nan, 30.0])
    sim = np.array([10.0, 999.0, 30.0])
    assert metrics.rmse(obs, sim) == pytest.approx(0.0)


def test_metrics_return_nan_when_no_finite_pairs() -> None:
    obs = np.array([np.nan, np.nan])
    sim = np.array([1.0, 2.0])
    assert math.isnan(metrics.rmse(obs, sim))
    assert math.isnan(metrics.mae(obs, sim))
    assert math.isnan(metrics.nse(obs, sim))
    assert math.isnan(metrics.kge(obs, sim))
