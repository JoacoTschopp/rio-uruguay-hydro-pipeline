"""`seasonal_naive` (Fase 2, docs/rio_search_plan.md §3.3, §5): predice, para la fecha objetivo
`anchor + h`, el valor observado 365 dias antes de esa fecha (`anchor + h - 365`). Para
cualquier horizonte `h <= 14`, `anchor + h - 365` es siempre anterior al propio `anchor` (con
margen >= 351 dias): usar ese valor nunca mira al futuro respecto de la fecha "as of" de la
prediccion, sea cual sea el split al que pertenezca en el calendario (TRAIN/VAL/TEST son cortes
arbitrarios sobre una misma serie ya observada; §3.2 protege que el *ajuste* de estadisticos no
vea VAL/TEST, no que un baseline sin estado deje de usar valores ya observados).

No usa la ventana de `Sequences` para el lookup (con `sequence.lookback_days: 1`, como los
otros dos baselines, §5) sino un metodo extra `set_history()` que `RunSearch` llama con la
serie diaria completa del target (sin recortar por split) antes de `predict()`: agrandar la
ventana a 365 dias para lograr lo mismo colapsaria la cantidad de anclas evaluables en splits de
~365 dias como `rolling_365` VAL/TEST (ver `naive/base.py`).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from rio_search.domain.experiments.fit_result import FitResult
from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_registry import register_model
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.types import Predictions

SEASONAL_LAG_DAYS = 365


@register_model("seasonal_naive")
class SeasonalNaiveAdapter:
    """Implementa `application.ports.model_adapter.ModelAdapterPort` + `set_history()` (extra,
    fuera del Protocol -- Python Protocols se chequean estructuralmente, agregar metodos no
    rompe conformidad; `RunSearch` lo detecta con `hasattr` y lo llama antes de `fit`/`predict`
    para cualquier adaptador que lo declare, no solo este)."""

    name = "seasonal_naive"
    family = ModelFamily.NAIVE
    supports = {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}

    def __init__(self) -> None:
        self._horizons: tuple[int, ...] = ()
        self._history: dict[date, float] | None = None

    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None:
        horizons = tuple(int(h) for h in spec.params["horizons"])
        if len(horizons) != n_outputs:
            raise ValueError(f"n_outputs={n_outputs} no coincide con horizons={horizons}")
        self._horizons = horizons

    def set_history(self, dates: tuple[date, ...], values: np.ndarray) -> None:
        """Serie diaria completa del target (todo el dataset pineado, no un split): la unica
        fuente que este baseline necesita para mirar `target_date - 365`."""
        self._history = {d: float(v) for d, v in zip(dates, values) if np.isfinite(v)}

    def fit(self, train: Sequences, val: Sequences, training: Any, callbacks: Any = None) -> FitResult:
        return FitResult(epochs=0, best_epoch=0)

    def predict(self, X: Sequences) -> Predictions:
        if self._history is None:
            raise RuntimeError(
                "SeasonalNaiveAdapter.predict llamado sin set_history(): RunSearch debe "
                "llamarlo antes de predict() para todo adaptador que lo declare."
            )
        n = len(X.anchor_dates)
        h = len(self._horizons)
        y_pred = np.full((n, h), np.nan, dtype=np.float64)
        for i, anchor in enumerate(X.anchor_dates):
            for j, horizon in enumerate(self._horizons):
                lookup_date = anchor + timedelta(days=horizon - SEASONAL_LAG_DAYS)
                value = self._history.get(lookup_date)
                if value is not None:
                    y_pred[i, j] = value
        return Predictions(y_pred=y_pred, anchor_dates=X.anchor_dates, horizons=self._horizons)

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({"model": self.name, "horizons": list(self._horizons)}), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path, device: Device) -> "SeasonalNaiveAdapter":
        data = json.loads(path.read_text(encoding="utf-8"))
        adapter = cls()
        adapter._horizons = tuple(data["horizons"])
        return adapter
