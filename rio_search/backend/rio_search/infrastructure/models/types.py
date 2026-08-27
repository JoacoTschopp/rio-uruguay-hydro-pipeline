"""`Predictions`: salida de `ModelAdapterPort.predict` (Fase 2, docs/rio_search_plan.md §3.3).
Vive en `infrastructure`, no en `domain`, por la misma razon que `Sequences`/`Targets` (Fase 1,
`infrastructure.datasets.sequence_builder`/`target_builder`): son contenedores con NumPy, y el
dominio de este repo se mantiene sin dependencias de terceros.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np


@dataclass(frozen=True, slots=True)
class Predictions:
    """`y_pred[i, j]` es la prediccion de horizonte `horizons[j]` para la ventana cuya fecha
    "as of" es `anchor_dates[i]` -- misma convencion que `Targets` (Fase 1)."""

    y_pred: np.ndarray
    anchor_dates: tuple[date, ...]
    horizons: tuple[int, ...]
