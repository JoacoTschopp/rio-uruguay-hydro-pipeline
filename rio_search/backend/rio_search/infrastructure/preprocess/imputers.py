"""Imputacion (Fase 1, docs/rio_search_plan.md §3.6): `ffill` acotado (`max_ffill_days`) +
mediana de TRAIN para lo que el `ffill` no llega a cubrir. Los estadisticos (`ImputerStats`)
se ajustan **solo** con TRAIN (invariante del contexto Datasets, §3.2) y se reusan tal cual en
VAL/TEST -- nunca se recalcula la mediana con datos de VAL o TEST. Reporta el % imputado por
columna, para loguear en MLflow (§3.5, `features/spec.json`) y en la pagina Datasets (Fase 5).
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True, slots=True)
class ImputerStats:
    """Ajustado solo con TRAIN."""

    medians: dict[str, float]
    max_ffill_days: int


@dataclass(frozen=True, slots=True)
class ImputationReport:
    split: str
    imputed_pct: dict[str, float]


def fit_imputer(train: pl.DataFrame, columns: list[str], max_ffill_days: int = 3) -> ImputerStats:
    """Mediana por columna calculada **solo** sobre `train`."""
    if not columns:
        return ImputerStats(medians={}, max_ffill_days=max_ffill_days)
    row = train.select([pl.col(c).median().alias(c) for c in columns]).row(0, named=True)
    medians = {c: float(row[c]) if row[c] is not None else 0.0 for c in columns}
    return ImputerStats(medians=medians, max_ffill_days=max_ffill_days)


def apply_imputer(
    df: pl.DataFrame, columns: list[str], stats: ImputerStats, split: str
) -> tuple[pl.DataFrame, ImputationReport]:
    """`ffill` acotado a `stats.max_ffill_days` seguido de mediana de TRAIN para lo que
    quede nulo. `df` debe venir ordenado por fecha (lo garantiza `BuildSplit`)."""
    if not columns:
        return df, ImputationReport(split=split, imputed_pct={})

    before_null = df.select([pl.col(c).is_null().sum().alias(c) for c in columns]).row(0, named=True)

    out = df.with_columns([pl.col(c).forward_fill(limit=stats.max_ffill_days) for c in columns])
    out = out.with_columns([pl.col(c).fill_null(stats.medians[c]) for c in columns])

    rows = out.height
    imputed_pct = {
        c: round(100.0 * float(before_null[c] or 0) / rows, 2) if rows else 0.0 for c in columns
    }
    return out, ImputationReport(split=split, imputed_pct=imputed_pct)
