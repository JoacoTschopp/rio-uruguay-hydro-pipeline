"""Tests de imputacion (Fase 1, docs/rio_search_plan.md §3.6): `ffill` acotado + mediana de
TRAIN, ajustada **solo** con TRAIN y reaplicada tal cual sobre VAL/TEST."""

from __future__ import annotations

import polars as pl

from rio_search.infrastructure.preprocess.imputers import apply_imputer, fit_imputer


def test_fit_imputer_computes_median_from_train_only() -> None:
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0, None]})
    stats = fit_imputer(train, ["x"], max_ffill_days=3)
    assert stats.medians["x"] == 2.0


def test_apply_imputer_ffill_within_limit() -> None:
    train = pl.DataFrame({"x": [10.0, 10.0, 10.0]})
    stats = fit_imputer(train, ["x"], max_ffill_days=2)
    df = pl.DataFrame({"x": [5.0, None, None, None, 8.0]})
    out, report = apply_imputer(df, ["x"], stats, split="test")
    # 2 nulos seguidos se llenan con ffill (limit=2); el 3ro (si lo hubiera) caeria a mediana.
    assert out["x"].to_list() == [5.0, 5.0, 5.0, 10.0, 8.0]


def test_apply_imputer_falls_back_to_train_median_beyond_ffill_limit() -> None:
    train_median = 42.0
    stats = fit_imputer(pl.DataFrame({"x": [42.0]}), ["x"], max_ffill_days=1)
    df = pl.DataFrame({"x": [1.0, None, None, None]})
    out, _ = apply_imputer(df, ["x"], stats, split="test")
    # ffill(limit=1) cubre solo el primer nulo tras el 1.0; los siguientes 2 quedan en mediana.
    assert out["x"].to_list() == [1.0, 1.0, train_median, train_median]


def test_apply_imputer_reports_imputed_pct_per_column() -> None:
    stats = fit_imputer(pl.DataFrame({"x": [1.0]}), ["x"], max_ffill_days=0)
    df = pl.DataFrame({"x": [1.0, None, None, 4.0]})
    _, report = apply_imputer(df, ["x"], stats, split="val")
    assert report.split == "val"
    assert report.imputed_pct["x"] == 50.0  # 2 de 4 filas eran nulas


def test_imputer_stats_do_not_change_when_val_or_test_change() -> None:
    """El imputador se ajusta solo con TRAIN: cambiar VAL/TEST no puede cambiar `medians`."""
    train = pl.DataFrame({"x": [1.0, 2.0, 3.0]})
    stats_before = fit_imputer(train, ["x"], max_ffill_days=1)

    # VAL/TEST con valores extremos no deberian influir -- ni siquiera se les pasa a fit_imputer.
    _wild_val = pl.DataFrame({"x": [999999.0, -999999.0]})
    stats_after = fit_imputer(train, ["x"], max_ffill_days=1)

    assert stats_before.medians == stats_after.medians == {"x": 2.0}


def test_fit_imputer_empty_columns_returns_empty_stats() -> None:
    train = pl.DataFrame({"x": [1.0]})
    stats = fit_imputer(train, [], max_ffill_days=3)
    assert stats.medians == {}


def test_apply_imputer_empty_columns_is_noop() -> None:
    df = pl.DataFrame({"x": [1.0, None]})
    stats = fit_imputer(df, [], max_ffill_days=3)
    out, report = apply_imputer(df, [], stats, split="train")
    assert out["x"].to_list() == [1.0, None]
    assert report.imputed_pct == {}
