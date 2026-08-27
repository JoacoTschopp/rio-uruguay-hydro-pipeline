"""Tests de `SequenceBuilder` (Fase 1, docs/rio_search_plan.md §3.6): ventaneo `lookback_days`
-> tensores `(N, lookback, n_features)`, alineacion de `anchor_dates`, y que las ventanas no
puedan cruzar el limite de un split (porque el df de entrada ya viene recortado)."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from rio_search.domain.datasets.sequence_spec import SequenceSpec
from rio_search.infrastructure.datasets.sequence_builder import SequenceBuilder


def _df(n: int, start: date = date(2020, 1, 1)) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(n)]
    return pl.DataFrame(
        {"fecha": dates, "x": [float(i) for i in range(n)], "y": [float(i * 2) for i in range(n)]}
    )


def test_build_produces_expected_shape() -> None:
    df = _df(10)
    builder = SequenceBuilder(SequenceSpec(lookback_days=3))
    seqs = builder.build(df, ["x", "y"])
    assert seqs.X.shape == (8, 3, 2)  # 10 - 3 + 1 = 8 ventanas
    assert len(seqs.anchor_dates) == 8


def test_anchor_dates_are_last_day_of_each_window() -> None:
    df = _df(5)
    builder = SequenceBuilder(SequenceSpec(lookback_days=2))
    seqs = builder.build(df, ["x"])
    # ventana 0 = dias [0,1] -> anchor = dia 1; ventana 1 = dias [1,2] -> anchor = dia 2; ...
    expected = [date(2020, 1, 1) + timedelta(days=i) for i in (1, 2, 3, 4)]
    assert list(seqs.anchor_dates) == expected


def test_window_content_matches_consecutive_rows() -> None:
    df = _df(5)
    builder = SequenceBuilder(SequenceSpec(lookback_days=3))
    seqs = builder.build(df, ["x"])
    # primera ventana: x = [0, 1, 2]
    assert seqs.X[0, :, 0].tolist() == [0.0, 1.0, 2.0]
    # ultima ventana: x = [2, 3, 4]
    assert seqs.X[-1, :, 0].tolist() == [2.0, 3.0, 4.0]


def test_raises_when_split_smaller_than_lookback() -> None:
    df = _df(2)
    builder = SequenceBuilder(SequenceSpec(lookback_days=5))
    with pytest.raises(ValueError, match="lookback_days"):
        builder.build(df, ["x"])


def test_windows_never_extend_past_the_slice_given() -> None:
    """Ventanas construidas sobre un split ya recortado no pueden `ver` dias fuera de ese
    split -- lo verificamos con un split de 20 dias: todas las fechas usadas (incluidas las de
    inicio de ventana) caen dentro del rango del df de entrada."""
    df = _df(20)
    builder = SequenceBuilder(SequenceSpec(lookback_days=7))
    seqs = builder.build(df, ["x"])
    df_dates = set(df["fecha"].to_list())
    for anchor in seqs.anchor_dates:
        assert anchor in df_dates
        window_start = anchor - timedelta(days=6)
        assert window_start in df_dates


def test_sequence_spec_rejects_non_positive_lookback() -> None:
    with pytest.raises(ValueError):
        SequenceSpec(lookback_days=0)
