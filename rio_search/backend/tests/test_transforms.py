"""Tests de transforms experimentales (Decision #5, docs/rio_search_plan.md §3.6): cada
funcion produce la expresion Polars esperada y `build_expressions` resuelve un
`ExperimentalTransformSpec` del dominio a `list[pl.Expr]` correctamente."""

from __future__ import annotations

import math
from datetime import date

import polars as pl
import pytest

from rio_search.domain.datasets.feature_transform import ExperimentalTransformSpec
from rio_search.infrastructure.preprocess import transforms as transform_fns
from rio_search.infrastructure.preprocess.transforms import TRANSFORMS, build_expressions


def test_registry_has_all_six_transforms() -> None:
    assert set(TRANSFORMS) == {"log1p", "doy_cyclic", "clip", "ratio", "diff", "rolling"}


def test_log1p_expression() -> None:
    df = pl.DataFrame({"x": [0.0, 1.0, math.e - 1]})
    out = df.select(pl.col("x").log1p().alias("x_log1p"))
    expected = [math.log1p(v) for v in [0.0, 1.0, math.e - 1]]
    assert out["x_log1p"].to_list() == pytest.approx(expected)


def test_clip_bounds_both_sides() -> None:
    df = pl.DataFrame({"x": [-10.0, 5.0, 100.0]})
    spec = ExperimentalTransformSpec(name="clip", version=1, columns=["x"], params={"min": 0, "max": 50})
    out = df.with_columns(build_expressions(spec))
    assert out["x_clip"].to_list() == [0.0, 5.0, 50.0]


def test_clip_requires_min_or_max() -> None:
    with pytest.raises(ValueError):
        transform_fns.clip("x")


def test_ratio_divides_and_nulls_on_zero_denominator() -> None:
    df = pl.DataFrame({"num": [10.0, 20.0], "den": [2.0, 0.0]})
    spec = ExperimentalTransformSpec(
        name="ratio", version=1, params={"numerator": "num", "denominator": "den"}
    )
    out = df.with_columns(build_expressions(spec))
    assert out["num_ratio_den"].to_list() == [5.0, None]


def test_diff_shifts_and_subtracts() -> None:
    df = pl.DataFrame({"x": [1.0, 3.0, 6.0, 10.0]})
    spec = ExperimentalTransformSpec(name="diff", version=1, columns=["x"], params={"periods": 1})
    out = df.with_columns(build_expressions(spec))
    assert out["x_diff_1d"].to_list() == [None, 2.0, 3.0, 4.0]


def test_rolling_mean_window() -> None:
    df = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]})
    spec = ExperimentalTransformSpec(
        name="rolling", version=1, columns=["x"], params={"window": 2, "stat": "mean"}
    )
    out = df.with_columns(build_expressions(spec))
    assert out["x_rolling_mean_2d"].to_list() == [1.0, 1.5, 2.5, 3.5]


def test_rolling_unknown_stat_raises() -> None:
    spec = ExperimentalTransformSpec(name="rolling", version=1, columns=["x"], params={"stat": "median"})
    with pytest.raises(ValueError):
        build_expressions(spec)


def test_doy_cyclic_produces_sin_cos_pair() -> None:
    df = pl.DataFrame({"fecha": [date(2020, 1, 1), date(2020, 7, 1)]})
    spec = ExperimentalTransformSpec(name="doy_cyclic", version=1)
    out = df.with_columns(build_expressions(spec))
    assert "doy_sin" in out.columns and "doy_cos" in out.columns
    # sin^2 + cos^2 == 1 para cada fila.
    for row in out.select("doy_sin", "doy_cos").iter_rows():
        assert row[0] ** 2 + row[1] ** 2 == pytest.approx(1.0, abs=1e-9)


def test_build_expressions_unknown_transform_raises() -> None:
    spec = ExperimentalTransformSpec(name="fft", version=1, columns=["x"])
    with pytest.raises(ValueError, match="fft"):
        build_expressions(spec)


def test_build_expressions_requires_columns_for_column_wise_transforms() -> None:
    spec = ExperimentalTransformSpec(name="log1p", version=1, columns=())
    with pytest.raises(ValueError, match="columns"):
        build_expressions(spec)


def test_build_expressions_multiple_columns_produce_one_expr_each() -> None:
    spec = ExperimentalTransformSpec(name="log1p", version=1, columns=["a", "b", "c"])
    exprs = build_expressions(spec)
    assert len(exprs) == 3
