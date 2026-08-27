"""Tests de `BuildSplit` (Fase 1, docs/rio_search_plan.md §3.2, §3.6): aplica una
`SplitPolicy` sobre un `pl.DataFrame` sintetico y recorta train/val/test -- ninguna fila de un
split aparece fuera de su `DateRange`, y las tres particiones no se solapan."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from rio_search.application.datasets.build_split import BuildSplit
from rio_search.domain.datasets.split_policy import SplitPolicy, TrainWindow

HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)


def _synthetic_df(n_days: int = 1200, start: date = date(2015, 1, 1)) -> pl.DataFrame:
    """`n_days` de calendario continuo (sin huecos, como Gold real, §2.1). `caudal_actual_m3s`
    es una rampa simple (`i`), y cada `caudal_t_mas_{h}d` es exactamente el valor de la rampa
    `h` dias adelante -- reproduce el comportamiento real de un target LEAD sobre Gold."""
    dates = [start + timedelta(days=i) for i in range(n_days)]
    ramp = [float(i) for i in range(n_days)]
    data: dict[str, list] = {"fecha": dates, "caudal_actual_m3s": ramp}
    for h in HORIZONS:
        data[f"caudal_t_mas_{h}d"] = [ramp[i + h] if i + h < n_days else None for i in range(n_days)]
    return pl.DataFrame(data)


def _policy(train_start: date = date(2015, 1, 1)) -> SplitPolicy:
    return SplitPolicy(policy="rolling_365", embargo_days=14, train_window=TrainWindow(start=train_start))


def test_build_split_partitions_stay_within_their_own_date_range() -> None:
    df = _synthetic_df()
    split_dfs = BuildSplit().execute(df, _policy(), HORIZONS)

    for name, part, date_range in (
        ("train", split_dfs.train, split_dfs.split.train),
        ("val", split_dfs.val, split_dfs.split.val),
        ("test", split_dfs.test, split_dfs.split.test),
    ):
        fechas = part["fecha"].to_list()
        assert fechas, f"{name} quedo vacio"
        assert all(date_range.contains(f) for f in fechas), f"{name} tiene fechas fuera de {date_range}"


def test_build_split_partitions_do_not_overlap_in_rows() -> None:
    df = _synthetic_df()
    split_dfs = BuildSplit().execute(df, _policy(), HORIZONS)

    train_dates = set(split_dfs.train["fecha"].to_list())
    val_dates = set(split_dfs.val["fecha"].to_list())
    test_dates = set(split_dfs.test["fecha"].to_list())

    assert train_dates.isdisjoint(val_dates)
    assert val_dates.isdisjoint(test_dates)
    assert train_dates.isdisjoint(test_dates)


def test_build_split_row_counts_match_date_range_days() -> None:
    df = _synthetic_df()
    split_dfs = BuildSplit().execute(df, _policy(), HORIZONS)
    # el dataset sintetico no tiene huecos de calendario -> filas == dias del rango.
    assert split_dfs.train.height == split_dfs.split.train.days
    assert split_dfs.val.height == split_dfs.split.val.days
    assert split_dfs.test.height == split_dfs.split.test.days


def test_build_split_uses_real_fecha_max_of_the_dataframe() -> None:
    df = _synthetic_df(n_days=1200, start=date(2015, 1, 1))
    fecha_max = df["fecha"].max()
    split_dfs = BuildSplit().execute(df, _policy(), HORIZONS)
    assert split_dfs.split.anchor == fecha_max - timedelta(days=max(HORIZONS))
