"""Tests de `infrastructure.models.naive.climatology.ClimatologyAdapter` (Fase 2,
docs/rio_search_plan.md §3.3, §5: "por dia del año sobre TRAIN")."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.naive.climatology import ClimatologyAdapter

_DEVICE = Device(type="cpu")


def _seq_from(start: date, values: list[float]) -> Sequences:
    x = np.array(values, dtype=np.float32).reshape(-1, 1, 1)
    dates = tuple(start + timedelta(days=i) for i in range(len(values)))
    return Sequences(X=x, anchor_dates=dates, feature_columns=("caudal_actual_m3s",))


def _adapter(horizons: list[int]) -> ClimatologyAdapter:
    adapter = ClimatologyAdapter()
    spec = ModelSpec(
        name="climatology", horizon_strategy=HorizonStrategy.MULTI_OUTPUT, params={"horizons": horizons}
    )
    adapter.build(spec, n_features=1, n_outputs=len(horizons), device=_DEVICE)
    return adapter


def test_fit_averages_same_calendar_day_across_years() -> None:
    # 3-jan de tres años distintos: 10, 20, 30 -> media 20
    train_dates = [date(2018, 1, 3), date(2019, 1, 3), date(2020, 1, 3)]
    train = Sequences(
        X=np.array([10.0, 20.0, 30.0], dtype=np.float32).reshape(-1, 1, 1),
        anchor_dates=tuple(train_dates),
        feature_columns=("caudal_actual_m3s",),
    )
    adapter = _adapter([1])
    adapter.fit(train, train, training=None)

    # ancla 2-ene, horizonte 1 -> fecha objetivo 3-ene -> deberia usar la media 20.0
    x_pred = _seq_from(date(2021, 1, 2), [999.0])
    predictions = adapter.predict(x_pred)
    assert predictions.y_pred[0, 0] == pytest.approx(20.0)


def test_predict_falls_back_to_overall_mean_for_unseen_calendar_day() -> None:
    train = Sequences(
        X=np.array([100.0], dtype=np.float32).reshape(-1, 1, 1),
        anchor_dates=(date(2020, 6, 15),),
        feature_columns=("caudal_actual_m3s",),
    )
    adapter = _adapter([1])
    adapter.fit(train, train, training=None)

    # objetivo 2-ene, nunca visto en TRAIN -> cae al overall_mean (= 100.0, unico dato)
    x_pred = _seq_from(date(2021, 1, 1), [0.0])
    predictions = adapter.predict(x_pred)
    assert predictions.y_pred[0, 0] == pytest.approx(100.0)


def test_fit_ignores_non_finite_values() -> None:
    train = Sequences(
        X=np.array([10.0, np.nan, 30.0], dtype=np.float32).reshape(-1, 1, 1),
        anchor_dates=(date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)),
        feature_columns=("caudal_actual_m3s",),
    )
    adapter = _adapter([1])
    adapter.fit(train, train, training=None)

    x_pred = _seq_from(date(2019, 12, 31), [0.0])  # objetivo h=1 -> 1-ene
    predictions = adapter.predict(x_pred)
    assert predictions.y_pred[0, 0] == pytest.approx(20.0)  # media de 10 y 30, sin el NaN


def test_save_and_load_roundtrip(tmp_path) -> None:
    train = Sequences(
        X=np.array([10.0, 20.0], dtype=np.float32).reshape(-1, 1, 1),
        anchor_dates=(date(2020, 1, 1), date(2021, 1, 1)),
        feature_columns=("caudal_actual_m3s",),
    )
    adapter = _adapter([1])
    adapter.fit(train, train, training=None)

    path = tmp_path / "model_state.json"
    adapter.save(path)
    loaded = ClimatologyAdapter.load(path, device=_DEVICE)

    x_pred = _seq_from(date(2019, 12, 31), [0.0])
    np.testing.assert_allclose(loaded.predict(x_pred).y_pred, adapter.predict(x_pred).y_pred)
