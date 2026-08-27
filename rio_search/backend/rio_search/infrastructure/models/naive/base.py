"""Helpers compartidos por los adaptadores naive (Fase 2, docs/rio_search_plan.md §3.3, §5).

Los tres YAML de baseline usan `sequence.lookback_days: 1` a proposito (ver los propios YAML):
con ventana de 1 dia, `SequenceBuilder` produce una ancla por cada fila del split (cobertura
completa de VAL/TEST, sin la perdida de las primeras `lookback-1` filas que tendria una ventana
mas larga) y `X[:, -1, 0]` es exactamente el valor observado ese mismo dia -- "el propio target
rezagado" que usan estos baselines (§3.3), sin necesidad de mirar dias anteriores dentro de la
ventana. `seasonal_naive` necesita mirar 365 dias atras igual: en vez de agrandar la ventana (lo
que reduciria la cantidad de anclas evaluables en splits de ~365 dias, como VAL/TEST de
`rolling_365`), consulta directamente el historico completo via `set_history()` -- ver
`seasonal_naive.py`.
"""

from __future__ import annotations

import numpy as np

from rio_search.infrastructure.datasets.sequence_builder import Sequences


def last_step_value(seq: Sequences, feature_index: int = 0) -> np.ndarray:
    """Valor del ultimo dia de cada ventana -- con `lookback_days: 1` es el valor del propio
    dia ancla (persistencia)."""
    return seq.X[:, -1, feature_index]
