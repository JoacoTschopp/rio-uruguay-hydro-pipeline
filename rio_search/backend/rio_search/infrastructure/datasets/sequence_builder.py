"""`SequenceBuilder` (Fase 1, docs/rio_search_plan.md §3.6): ventaneo `lookback_days` ->
tensores `(N, lookback, n_features)`.

Trabaja siempre sobre un `pl.DataFrame` ya recortado a un split por
`application.datasets.build_split.BuildSplit`: como las filas de los otros splits ni siquiera
estan presentes, ninguna ventana puede cruzar el limite de su split (invariante de no-fuga,
§3.2, §6). El dataset base no tiene huecos de calendario (§2.1: "9.732 filas sin huecos"), asi
que el ventaneo no necesita re-indexar por fecha.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from rio_search.domain.datasets.sequence_spec import SequenceSpec


@dataclass(frozen=True, slots=True)
class Sequences:
    """`X`: `(N, lookback, n_features)`. `anchor_dates[i]` es la fecha del ultimo dia de la
    ventana `i` -- el dia "as of" desde el que se predice, alineado 1:1 con
    `TargetBuilder.build(..., anchor_dates=...)`."""

    X: np.ndarray
    anchor_dates: tuple[date, ...]
    feature_columns: tuple[str, ...]


class SequenceBuilder:
    def __init__(self, spec: SequenceSpec) -> None:
        self._spec = spec

    def build(self, df: pl.DataFrame, feature_columns: list[str], date_column: str = "fecha") -> Sequences:
        lookback = self._spec.lookback_days
        if df.height < lookback:
            raise ValueError(
                f"El split tiene {df.height} filas, menos que sequence.lookback_days={lookback}; "
                "no se puede construir ninguna ventana (ajustar train_window o lookback)."
            )

        ordered = df.sort(date_column)
        arr = ordered.select(feature_columns).to_numpy().astype(np.float32)
        dates = ordered.select(date_column).to_series().to_list()

        n_windows = arr.shape[0] - lookback + 1
        windows = np.stack([arr[i : i + lookback] for i in range(n_windows)])
        anchor_dates = tuple(dates[lookback - 1 :])

        return Sequences(X=windows, anchor_dates=anchor_dates, feature_columns=tuple(feature_columns))
