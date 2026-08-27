"""`TargetBuilder` (Fase 1, docs/rio_search_plan.md §3.6): matriz de targets alineada por
fecha "as of" con `SequenceBuilder.anchor_dates`.

`multi_output` usa `Targets.y` completo (todas las columnas de horizonte juntas);
`per_horizon` usa `Targets.for_horizon(h)` -- una vista `(N, 1)` de la misma matriz. El bucle
sobre horizontes de `per_horizon` (un run hijo de MLflow por horizonte) vive en la aplicacion
(§3.3), no aca: un `TargetBuilder` alcanza para ambas estrategias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

from rio_search.domain.shared.target_variable import TargetVariable


@dataclass(frozen=True, slots=True)
class Targets:
    """`y[i, j]` es el target de horizonte `horizons[j]` para la ventana cuya fecha "as of"
    es `anchor_dates[i]` (mismo orden que `Sequences.anchor_dates`)."""

    y: np.ndarray
    horizons: tuple[int, ...]

    def for_horizon(self, horizon: int) -> np.ndarray:
        """Vista `(N, 1)` para `horizon_strategy: per_horizon` (§3.3)."""
        if horizon not in self.horizons:
            raise ValueError(f"Horizonte {horizon} no esta en {self.horizons}")
        idx = self.horizons.index(horizon)
        return self.y[:, idx : idx + 1]


class TargetBuilder:
    def __init__(self, target: TargetVariable, horizons: tuple[int, ...]) -> None:
        if not horizons:
            raise ValueError("TargetBuilder requiere al menos un horizonte")
        self._target = target
        self._horizons = horizons

    def build(
        self, df: pl.DataFrame, anchor_dates: tuple[date, ...], date_column: str = "fecha"
    ) -> Targets:
        """`df` debe contener, para cada fecha en `anchor_dates`, las columnas de target
        (`caudal_t_mas_{h}d` / `nivel_rio_t_mas_{h}d`) de esa misma fila -- son columnas LEAD
        ya calculadas en Gold (§2.1), no hace falta desplazarlas de nuevo."""
        columns = list(self._target.target_columns(self._horizons))
        lookup = df.select([date_column, *columns]).unique(subset=[date_column], keep="first")

        anchors = pl.DataFrame({date_column: list(anchor_dates)})
        aligned = anchors.join(lookup, on=date_column, how="left", maintain_order="left")

        y = aligned.select(columns).to_numpy().astype(np.float64)
        return Targets(y=y, horizons=self._horizons)
