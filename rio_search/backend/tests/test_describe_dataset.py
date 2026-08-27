"""Tests de `DescribeDataset` (Fase 1, docs/rio_search_plan.md §5): cobertura por
columna/año/split sobre un dataset sintetico con huecos deliberados en algunas columnas
(replica el patron real de §2.1: temperatura 0% en 2000-2005, huecos de target en la cola)."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from rio_search.application.datasets.describe_dataset import DescribeDataset
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.split_policy import SplitPolicy, TrainWindow

HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)


def _dataset_version(n_days: int) -> DatasetVersion:
    return DatasetVersion(
        delta_version=1,
        sha256="0" * 64,
        rows=n_days,
        fecha_min="2015-01-01",
        fecha_max="2018-04-14",
        columns=("fecha", "caudal_actual_m3s", "temp_media_c")
        + tuple(f"caudal_t_mas_{h}d" for h in HORIZONS),
    )


def _synthetic_df(n_days: int = 1200, start: date = date(2015, 1, 1)) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(n_days)]
    ramp = [float(i) for i in range(n_days)]
    # temp_media_c solo tiene datos a partir del dia 700 (simula "0% de cobertura" en años tempranos, §2.1).
    temp = [None if i < 700 else 20.0 + (i % 10) for i in range(n_days)]
    data: dict[str, list] = {"fecha": dates, "caudal_actual_m3s": ramp, "temp_media_c": temp}
    for h in HORIZONS:
        data[f"caudal_t_mas_{h}d"] = [ramp[i + h] if i + h < n_days else None for i in range(n_days)]
    return pl.DataFrame(data)


def _policy() -> SplitPolicy:
    return SplitPolicy(
        policy="rolling_365", embargo_days=14, train_window=TrainWindow(start=date(2015, 1, 1))
    )


def test_describe_dataset_reports_rows_and_date_range_per_split() -> None:
    df = _synthetic_df()
    coverage = DescribeDataset().execute(
        dataset_version=_dataset_version(df.height),
        df=df,
        split_policy=_policy(),
        horizons=HORIZONS,
        columns=("caudal_actual_m3s", "temp_media_c"),
    )
    for split_coverage in coverage.splits:
        assert split_coverage.rows == split_coverage.date_range.days
        assert split_coverage.name in {"train", "val", "test"}


def test_describe_dataset_column_coverage_reflects_nulls() -> None:
    df = _synthetic_df()
    coverage = DescribeDataset().execute(
        dataset_version=_dataset_version(df.height),
        df=df,
        split_policy=_policy(),
        horizons=HORIZONS,
        columns=("caudal_actual_m3s", "temp_media_c"),
    )
    train = coverage.split_coverage("train")
    # train cubre dias 0..~429 (train_end ~ dia 427): todo antes del dia 700 -> temp 0% cobertura.
    assert train.column("temp_media_c").non_null_pct == 0.0
    assert train.column("caudal_actual_m3s").non_null_pct == 100.0


def test_describe_dataset_year_coverage_shows_temp_gap() -> None:
    df = _synthetic_df()
    coverage = DescribeDataset().execute(
        dataset_version=_dataset_version(df.height),
        df=df,
        split_policy=_policy(),
        horizons=HORIZONS,
        columns=("temp_media_c",),
    )
    years_by_year = {y.year: y for y in coverage.years}
    assert years_by_year[2015].column("temp_media_c").non_null_pct == 0.0
    # dia 700 cae en 2016-12-01 (2015-01-01 + 700 dias); 2018 deberia tener cobertura > 0.
    assert years_by_year[2018].column("temp_media_c").non_null_pct > 0.0


def test_describe_dataset_default_columns_excludes_date_column() -> None:
    df = _synthetic_df(n_days=1200)
    coverage = DescribeDataset().execute(
        dataset_version=_dataset_version(df.height), df=df, split_policy=_policy(), horizons=HORIZONS
    )
    for split_coverage in coverage.splits:
        assert "fecha" not in {c.column for c in split_coverage.columns}


def test_describe_dataset_empty_columns_tuple_is_safe() -> None:
    df = _synthetic_df()
    coverage = DescribeDataset().execute(
        dataset_version=_dataset_version(df.height),
        df=df,
        split_policy=_policy(),
        horizons=HORIZONS,
        columns=(),
    )
    assert coverage.splits[0].columns == ()
