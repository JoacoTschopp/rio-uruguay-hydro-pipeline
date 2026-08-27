"""Escalado (Fase 1, docs/rio_search_plan.md §3.6): `standard` | `robust` | `minmax` | `none`,
ajustado **solo** con estadisticos de TRAIN (invariante del contexto Datasets, §3.2) y
reaplicado tal cual sobre VAL/TEST. Expresiones Polars, nunca pandas (Decision #9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl

ScalingMethod = Literal["standard", "robust", "minmax", "none"]

_METHODS = ("standard", "robust", "minmax", "none")


@dataclass(frozen=True, slots=True)
class ScalerStats:
    """Ajustado solo con TRAIN."""

    method: ScalingMethod
    center: dict[str, float]
    scale: dict[str, float]


def fit_scaler(train: pl.DataFrame, columns: list[str], method: ScalingMethod) -> ScalerStats:
    if method not in _METHODS:
        raise ValueError(f"Metodo de escalado desconocido: {method!r}. Disponibles: {_METHODS}")
    if method == "none" or not columns:
        return ScalerStats(
            method=method, center=dict.fromkeys(columns, 0.0), scale=dict.fromkeys(columns, 1.0)
        )

    if method == "standard":
        exprs = [pl.col(c).mean().alias(f"{c}__c") for c in columns] + [
            pl.col(c).std().alias(f"{c}__s") for c in columns
        ]
    elif method == "robust":
        exprs = [pl.col(c).median().alias(f"{c}__c") for c in columns] + [
            (pl.col(c).quantile(0.75) - pl.col(c).quantile(0.25)).alias(f"{c}__s") for c in columns
        ]
    else:  # minmax
        exprs = [pl.col(c).min().alias(f"{c}__c") for c in columns] + [
            (pl.col(c).max() - pl.col(c).min()).alias(f"{c}__s") for c in columns
        ]

    row = train.select(exprs).row(0, named=True)
    center = {c: float(row[f"{c}__c"]) if row[f"{c}__c"] is not None else 0.0 for c in columns}
    # evita division por cero (columna constante en TRAIN): escala 1.0, deja el centrado.
    scale = {
        c: (float(row[f"{c}__s"]) if row[f"{c}__s"] not in (None, 0.0) else 1.0) for c in columns
    }
    return ScalerStats(method=method, center=center, scale=scale)


def apply_scaler(df: pl.DataFrame, columns: list[str], stats: ScalerStats) -> pl.DataFrame:
    if stats.method == "none" or not columns:
        return df
    return df.with_columns([((pl.col(c) - stats.center[c]) / stats.scale[c]).alias(c) for c in columns])
