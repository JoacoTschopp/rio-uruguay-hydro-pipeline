"""Tests de escalado (Fase 1, docs/rio_search_plan.md §3.6): `standard` | `robust` | `minmax`
| `none`, ajustado **solo** con estadisticos de TRAIN -- el caso central de no-fuga que pide
la Fase 1 ("el escalador no ve VAL/TEST")."""

from __future__ import annotations

import polars as pl
import pytest

from rio_search.infrastructure.preprocess.scalers import apply_scaler, fit_scaler


def test_standard_scaler_center_and_scale() -> None:
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
    stats = fit_scaler(train, ["x"], "standard")
    assert stats.center["x"] == pytest.approx(3.0)
    assert stats.scale["x"] == pytest.approx(train["x"].std())


def test_apply_standard_scaler_produces_zero_mean() -> None:
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
    stats = fit_scaler(train, ["x"], "standard")
    scaled = apply_scaler(train, ["x"], stats)
    assert scaled["x"].mean() == pytest.approx(0.0, abs=1e-9)


def test_robust_scaler_uses_median_and_iqr() -> None:
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 100.0]})  # outlier no debe mover el centro
    stats = fit_scaler(train, ["x"], "robust")
    assert stats.center["x"] == 3.0  # mediana
    q1, q3 = train["x"].quantile(0.25), train["x"].quantile(0.75)
    assert stats.scale["x"] == pytest.approx(q3 - q1)


def test_minmax_scaler_bounds_train_to_0_1() -> None:
    train = pl.DataFrame({"x": [10.0, 20.0, 30.0]})
    stats = fit_scaler(train, ["x"], "minmax")
    scaled = apply_scaler(train, ["x"], stats)
    assert scaled["x"].min() == pytest.approx(0.0)
    assert scaled["x"].max() == pytest.approx(1.0)


def test_none_method_is_identity() -> None:
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0]})
    stats = fit_scaler(train, ["x"], "none")
    scaled = apply_scaler(train, ["x"], stats)
    assert scaled["x"].to_list() == train["x"].to_list()


def test_constant_column_avoids_division_by_zero() -> None:
    train = pl.DataFrame({"x": [5.0, 5.0, 5.0]})
    stats = fit_scaler(train, ["x"], "standard")
    assert stats.scale["x"] == 1.0  # fallback, no NaN/inf
    scaled = apply_scaler(train, ["x"], stats)
    assert scaled["x"].to_list() == [0.0, 0.0, 0.0]


def test_scaler_stats_are_fit_only_from_train_argument() -> None:
    """No hay forma de que `fit_scaler` vea VAL/TEST: solo recibe `train` -- este test
    documenta la invariante en vez de asumirla (si la firma cambiara para aceptar mas
    dataframes, este test seria la primera señal a revisar)."""
    import inspect

    from rio_search.infrastructure.preprocess.scalers import fit_scaler as fn

    params = list(inspect.signature(fn).parameters)
    assert params == ["train", "columns", "method"]


def test_apply_scaler_on_val_test_uses_train_stats_not_their_own() -> None:
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0]})  # mean=2, std known
    stats = fit_scaler(train, ["x"], "standard")

    val = pl.DataFrame({"x": [100.0, 200.0, 300.0]})  # muy distinto de train
    scaled_val = apply_scaler(val, ["x"], stats)

    # Si el escalador hubiera visto VAL, el resultado tendria media ~0; al usar solo stats
    # de TRAIN (mean=2), el resultado de VAL queda lejos de 0.
    assert scaled_val["x"].mean() != pytest.approx(0.0, abs=1.0)


def test_unknown_method_raises() -> None:
    train = pl.DataFrame({"x": [1.0]})
    with pytest.raises(ValueError):
        fit_scaler(train, ["x"], "zscore")  # type: ignore[arg-type]
