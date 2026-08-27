"""Tests de `infrastructure.models.naive.seasonal_naive.SeasonalNaiveAdapter` (Fase 2,
docs/rio_search_plan.md §3.3, §5)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.naive.seasonal_naive import SEASONAL_LAG_DAYS, SeasonalNaiveAdapter

_DEVICE = Device(type="cpu")


def _adapter(horizons: list[int]) -> SeasonalNaiveAdapter:
    adapter = SeasonalNaiveAdapter()
    spec = ModelSpec(
        name="seasonal_naive", horizon_strategy=HorizonStrategy.MULTI_OUTPUT, params={"horizons": horizons}
    )
    adapter.build(spec, n_features=1, n_outputs=len(horizons), device=_DEVICE)
    return adapter


def _daily_history(start: date, values: list[float]) -> tuple[tuple[date, ...], np.ndarray]:
    dates = tuple(start + timedelta(days=i) for i in range(len(values)))
    return dates, np.array(values, dtype=np.float64)


def _seq(anchor_dates: list[date]) -> Sequences:
    n = len(anchor_dates)
    return Sequences(
        X=np.zeros((n, 1, 1), dtype=np.float32), anchor_dates=tuple(anchor_dates), feature_columns=("x",)
    )


def test_predict_looks_up_value_365_days_before_target_date() -> None:
    adapter = _adapter([1])
    history_start = date(2019, 1, 1)
    dates, values = _daily_history(history_start, [float(i) for i in range(1000)])
    adapter.set_history(dates, values)

    anchor = date(2021, 1, 1)
    predictions = adapter.predict(_seq([anchor]))

    target_date = anchor + timedelta(days=1)
    lookup_date = target_date - timedelta(days=SEASONAL_LAG_DAYS)
    expected = (lookup_date - history_start).days
    assert predictions.y_pred[0, 0] == pytest.approx(float(expected))


def test_predict_is_nan_when_lookup_date_missing_from_history() -> None:
    adapter = _adapter([14])
    dates, values = _daily_history(date(2020, 1, 1), [1.0, 2.0, 3.0])  # historial muy corto
    adapter.set_history(dates, values)

    predictions = adapter.predict(_seq([date(2021, 6, 1)]))
    assert math.isnan(predictions.y_pred[0, 0])


def test_predict_raises_without_set_history() -> None:
    adapter = _adapter([1])
    with pytest.raises(RuntimeError, match="set_history"):
        adapter.predict(_seq([date(2020, 1, 1)]))


def test_fit_is_a_deterministic_no_op() -> None:
    adapter = _adapter([1])
    seq = _seq([date(2020, 1, 1)])
    result = adapter.fit(seq, seq, training=None)
    assert result.epochs == 0


def test_save_and_load_roundtrip_does_not_carry_history(tmp_path) -> None:
    adapter = _adapter([1, 7])
    path = tmp_path / "model_state.json"
    adapter.save(path)
    loaded = SeasonalNaiveAdapter.load(path, device=_DEVICE)
    assert loaded._horizons == (1, 7)  # noqa: SLF001 - test blanco, verifica el roundtrip exacto
    with pytest.raises(RuntimeError):
        loaded.predict(_seq([date(2020, 1, 1)]))  # sin set_history() de nuevo tras cargar
