"""`DescribeDataset` (Fase 1, docs/rio_search_plan.md §5): cobertura por columna, por año y
por split -- alimenta `rio-search datasets describe` y la pagina Datasets de la UI (Fase 5).
"""

from __future__ import annotations

import polars as pl

from rio_search.application.datasets.build_split import BuildSplit
from rio_search.domain.datasets.dataset_coverage import (
    ColumnCoverage,
    DatasetCoverage,
    SplitCoverage,
    YearCoverage,
)
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.split_policy import SplitPolicy


class DescribeDataset:
    def __init__(self, build_split: BuildSplit | None = None) -> None:
        self._build_split = build_split or BuildSplit()

    def execute(
        self,
        dataset_version: DatasetVersion,
        df: pl.DataFrame,
        split_policy: SplitPolicy,
        horizons: tuple[int, ...],
        columns: tuple[str, ...] | None = None,
        date_column: str = "fecha",
    ) -> DatasetCoverage:
        cols = (
            tuple(columns)
            if columns is not None
            else tuple(c for c in df.columns if c != date_column)
        )

        split_dfs = self._build_split.execute(df, split_policy, horizons, date_column=date_column)
        splits = tuple(
            SplitCoverage(
                name=name,
                date_range=date_range,
                rows=part.height,
                columns=_column_coverage(part, cols),
            )
            for name, part, date_range in (
                ("train", split_dfs.train, split_dfs.split.train),
                ("val", split_dfs.val, split_dfs.split.val),
                ("test", split_dfs.test, split_dfs.split.test),
            )
        )

        year_values = df.select(pl.col(date_column).dt.year()).to_series().unique().to_list()
        years_list = sorted(y for y in year_values if y is not None)
        years = tuple(
            YearCoverage(
                year=int(year),
                rows=(group := df.filter(pl.col(date_column).dt.year() == year)).height,
                columns=_column_coverage(group, cols),
            )
            for year in years_list
        )

        return DatasetCoverage(
            dataset_version=dataset_version,
            split=split_dfs.split,
            splits=splits,
            years=years,
        )


def _column_coverage(df: pl.DataFrame, columns: tuple[str, ...]) -> tuple[ColumnCoverage, ...]:
    rows = df.height
    if rows == 0 or not columns:
        return tuple(ColumnCoverage(column=c, rows=0, non_null_rows=0, non_null_pct=0.0) for c in columns)

    row = df.select([pl.col(c).is_not_null().sum().alias(c) for c in columns]).row(0, named=True)
    return tuple(
        ColumnCoverage(
            column=c,
            rows=rows,
            non_null_rows=int(row[c]),
            non_null_pct=round(100.0 * int(row[c]) / rows, 2),
        )
        for c in columns
    )
