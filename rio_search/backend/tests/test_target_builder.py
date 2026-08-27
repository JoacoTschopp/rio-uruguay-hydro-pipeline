"""Tests de `TargetBuilder` (Fase 1, docs/rio_search_plan.md §3.6): matriz de targets alineada
por fecha "as of" con `SequenceBuilder.anchor_dates`, y la vista `for_horizon` que usa
`horizon_strategy: per_horizon` (§3.3)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.datasets.target_builder import TargetBuilder


def _df_with_targets(n: int, horizons: tuple[int, ...], start: date = date(2020, 1, 1)) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(n)]
    base = [float(i) for i in range(n)]
    data: dict[str, list] = {"fecha": dates, "caudal_actual_m3s": base}
    for h in horizons:
        data[f"caudal_t_mas_{h}d"] = [base[i + h] if i + h < n else None for i in range(n)]
    return pl.DataFrame(data)


def test_build_multi_output_matrix_shape_and_values() -> None:
    horizons = (1, 3, 7)
    df = _df_with_targets(20, horizons)
    anchor_dates = tuple(df["fecha"].to_list()[:10])  # primeras 10 fechas, con targets validos
    builder = TargetBuilder(TargetVariable.CAUDAL, horizons)

    targets = builder.build(df, anchor_dates)

    assert targets.y.shape == (10, 3)
    # anchor_dates[0] = dia 0 -> target h=1 es el valor del dia 1 = 1.0
    assert targets.y[0, 0] == pytest.approx(1.0)
    assert targets.y[0, 1] == pytest.approx(3.0)  # h=3
    assert targets.y[0, 2] == pytest.approx(7.0)  # h=7


def test_for_horizon_returns_column_view() -> None:
    horizons = (1, 3, 7)
    df = _df_with_targets(20, horizons)
    anchor_dates = tuple(df["fecha"].to_list()[:5])
    builder = TargetBuilder(TargetVariable.CAUDAL, horizons)
    targets = builder.build(df, anchor_dates)

    view = targets.for_horizon(3)
    assert view.shape == (5, 1)
    np.testing.assert_array_equal(view[:, 0], targets.y[:, 1])


def test_for_horizon_unknown_raises() -> None:
    builder = TargetBuilder(TargetVariable.CAUDAL, (1, 3))
    df = _df_with_targets(5, (1, 3))
    targets = builder.build(df, tuple(df["fecha"].to_list()[:2]))
    with pytest.raises(ValueError):
        targets.for_horizon(14)


def test_nivel_target_uses_nivel_rio_prefix() -> None:
    dates = [date(2020, 1, 1), date(2020, 1, 2)]
    df = pl.DataFrame(
        {"fecha": dates, "nivel_rio_t_mas_1d": [1.5, 2.5]}
    )
    builder = TargetBuilder(TargetVariable.NIVEL, (1,))
    targets = builder.build(df, (dates[0],))
    assert targets.y[0, 0] == pytest.approx(1.5)


def test_target_builder_requires_at_least_one_horizon() -> None:
    with pytest.raises(ValueError):
        TargetBuilder(TargetVariable.CAUDAL, ())


def test_missing_anchor_date_yields_null_row() -> None:
    """Una fecha "as of" que no esta en `df` (no deberia pasar en la practica, ya que
    `SequenceBuilder` y `TargetBuilder` comparten el mismo dataframe recortado) produce nulos
    en vez de reventar -- protege contra desalineaciones silenciosas mas que las oculta."""
    df = _df_with_targets(5, (1,))
    builder = TargetBuilder(TargetVariable.CAUDAL, (1,))
    targets = builder.build(df, (date(2099, 1, 1),))
    assert targets.y.shape == (1, 1)
    assert np.isnan(targets.y[0, 0])
