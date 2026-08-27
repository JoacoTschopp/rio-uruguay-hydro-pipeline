"""Tests de `infrastructure.models.naive.persistence.PersistenceAdapter` (Fase 2,
docs/rio_search_plan.md §3.3, §5)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.naive.persistence import PersistenceAdapter

_DEVICE = Device(type="cpu")


def _seq(values: list[float]) -> Sequences:
    """Ventana `lookback_days=1`: `X[i, 0, 0] == values[i]`, `anchor_dates[i]` = dia `i`."""
    x = np.array(values, dtype=np.float32).reshape(-1, 1, 1)
    start = date(2020, 1, 1)
    dates = tuple(start + timedelta(days=i) for i in range(len(values)))
    return Sequences(X=x, anchor_dates=dates, feature_columns=("caudal_actual_m3s",))


def test_predict_repeats_last_observed_value_across_all_horizons() -> None:
    adapter = PersistenceAdapter()
    spec = ModelSpec(
        name="persistence", horizon_strategy=HorizonStrategy.MULTI_OUTPUT, params={"horizons": [1, 3, 7]}
    )
    adapter.build(spec, n_features=1, n_outputs=3, device=_DEVICE)

    seq = _seq([100.0, 200.0, 300.0])
    predictions = adapter.predict(seq)

    assert predictions.horizons == (1, 3, 7)
    expected = [[100.0, 100.0, 100.0], [200.0, 200.0, 200.0], [300.0, 300.0, 300.0]]
    np.testing.assert_array_equal(predictions.y_pred, expected)


def test_build_rejects_horizons_count_mismatch() -> None:
    adapter = PersistenceAdapter()
    spec = ModelSpec(
        name="persistence", horizon_strategy=HorizonStrategy.MULTI_OUTPUT, params={"horizons": [1, 2]}
    )
    with pytest.raises(ValueError):
        adapter.build(spec, n_features=1, n_outputs=3, device=_DEVICE)


def test_fit_is_a_deterministic_no_op() -> None:
    adapter = PersistenceAdapter()
    seq = _seq([1.0, 2.0])
    result = adapter.fit(seq, seq, training=None)
    assert result.epochs == 0
    assert result.best_epoch == 0


def test_save_and_load_roundtrip(tmp_path) -> None:
    adapter = PersistenceAdapter()
    spec = ModelSpec(
        name="persistence", horizon_strategy=HorizonStrategy.MULTI_OUTPUT, params={"horizons": [1, 2]}
    )
    adapter.build(spec, n_features=1, n_outputs=2, device=_DEVICE)

    path = tmp_path / "model_state.json"
    adapter.save(path)
    loaded = PersistenceAdapter.load(path, device=_DEVICE)

    seq = _seq([50.0])
    np.testing.assert_array_equal(loaded.predict(seq).y_pred, adapter.predict(seq).y_pred)


def test_registered_metadata() -> None:
    assert PersistenceAdapter.name == "persistence"
    assert PersistenceAdapter.family == ModelFamily.NAIVE
    assert HorizonStrategy.MULTI_OUTPUT in PersistenceAdapter.supports
