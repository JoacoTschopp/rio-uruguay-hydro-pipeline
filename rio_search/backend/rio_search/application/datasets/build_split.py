"""`BuildSplit` (Fase 1, docs/rio_search_plan.md §3.2, §3.6): aplica una `SplitPolicy` sobre
un `pl.DataFrame` ya cargado y devuelve, ademas del `Split` (fechas), el dataframe recortado a
cada sub-periodo. `SequenceBuilder`/`TargetBuilder`/`BuildFeatureMatrix` trabajan siempre sobre
estas particiones ya filtradas, nunca sobre el dataframe completo: asi una ventana no puede
cruzar el limite de su split porque las filas de los otros splits ni siquiera estan presentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from rio_search.domain.datasets.split_policy import Split, SplitPolicy


@dataclass(frozen=True, slots=True)
class SplitDataFrames:
    split: Split
    train: pl.DataFrame
    val: pl.DataFrame
    test: pl.DataFrame


class BuildSplit:
    def execute(
        self,
        df: pl.DataFrame,
        policy: SplitPolicy,
        horizons: tuple[int, ...],
        date_column: str = "fecha",
    ) -> SplitDataFrames:
        fecha_max = _max_date(df, date_column)
        split = policy.build(fecha_max=fecha_max, horizons=horizons)
        train = _slice(df, date_column, split.train.start, split.train.end)
        val = _slice(df, date_column, split.val.start, split.val.end)
        test = _slice(df, date_column, split.test.start, split.test.end)
        return SplitDataFrames(split=split, train=train, val=val, test=test)


def _slice(df: pl.DataFrame, date_column: str, start: date, end: date) -> pl.DataFrame:
    return df.filter(pl.col(date_column).is_between(start, end, closed="both")).sort(date_column)


def _max_date(df: pl.DataFrame, date_column: str) -> date:
    value = df.select(pl.col(date_column).max()).item()
    if value is None:
        raise ValueError(f"No se pudo determinar fecha_max: columna {date_column!r} vacia")
    if isinstance(value, date):
        return value
    # Fallback por si `fecha` llega como string ISO (no es el caso del parquet real, pero
    # protege datasets sinteticos/externos que no tipen la columna como Date).
    return date.fromisoformat(str(value)[:10])
