"""Resultado de `DescribeDataset` (Fase 1, docs/rio_search_plan.md §5): cobertura por
columna, por año y por split -- alimenta `rio-search datasets describe` y la pagina Datasets
de la UI (Fase 5). Sin dependencias del proyecto (regla de `domain`); quien calcula los
porcentajes con Polars es `application.datasets.describe_dataset.DescribeDataset`.
"""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.split_policy import Split
from rio_search.domain.shared.date_range import DateRange


@dataclass(frozen=True, slots=True)
class ColumnCoverage:
    column: str
    rows: int
    non_null_rows: int
    non_null_pct: float


@dataclass(frozen=True, slots=True)
class SplitCoverage:
    name: str  # "train" | "val" | "test"
    date_range: DateRange
    rows: int
    columns: tuple[ColumnCoverage, ...]

    def column(self, name: str) -> ColumnCoverage:
        for c in self.columns:
            if c.column == name:
                return c
        raise KeyError(f"Columna sin cobertura calculada: {name!r}")


@dataclass(frozen=True, slots=True)
class YearCoverage:
    year: int
    rows: int
    columns: tuple[ColumnCoverage, ...]

    def column(self, name: str) -> ColumnCoverage:
        for c in self.columns:
            if c.column == name:
                return c
        raise KeyError(f"Columna sin cobertura calculada: {name!r}")


@dataclass(frozen=True, slots=True)
class DatasetCoverage:
    dataset_version: DatasetVersion
    split: Split
    splits: tuple[SplitCoverage, ...]
    years: tuple[YearCoverage, ...]

    def split_coverage(self, name: str) -> SplitCoverage:
        for s in self.splits:
            if s.name == name:
                return s
        raise KeyError(f"Split sin cobertura calculada: {name!r}")
