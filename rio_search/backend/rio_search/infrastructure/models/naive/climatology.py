"""`climatology` (Fase 2, docs/rio_search_plan.md §3.3, §5): "por dia del año sobre TRAIN" --
predice, para la fecha objetivo `anchor + h`, la media climatologica de esa fecha calendario
(mes, dia) ajustada **solo** con TRAIN (invariante del contexto Datasets, §3.2: "el escalador se
ajusta solo con TRAIN", aplicado aca al estadistico del baseline). Con `sequence.lookback_days:
1` (ver `naive/base.py`), `train.anchor_dates`/`train.X[:, -1, 0]` cubren exactamente los dias de
TRAIN, sin contaminacion de fechas anteriores ni perdida de dias por ventaneo.
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
from rio_search.infrastructure.models.naive.base import last_step_value
from rio_search.infrastructure.models.types import Predictions


def _month_day_key(d: date) -> str:
    return f"{d.month:02d}-{d.day:02d}"


@register_model("climatology")
class ClimatologyAdapter:
    """Implementa `application.ports.model_adapter.ModelAdapterPort`."""

    name = "climatology"
    family = ModelFamily.NAIVE
    supports = {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}

    def __init__(self) -> None:
        self._horizons: tuple[int, ...] = ()
        self._doy_mean: dict[str, float] = {}
        self._overall_mean: float = float("nan")

    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None:
        horizons = tuple(int(h) for h in spec.params["horizons"])
        if len(horizons) != n_outputs:
            raise ValueError(f"n_outputs={n_outputs} no coincide con horizons={horizons}")
        self._horizons = horizons

    def fit(self, train: Sequences, val: Sequences, training: Any, callbacks: Any = None) -> FitResult:
        values = last_step_value(train)
        finite = np.isfinite(values)
        self._overall_mean = float(values[finite].mean()) if finite.any() else float("nan")

        buckets: dict[str, list[float]] = {}
        for d, v, ok in zip(train.anchor_dates, values, finite):
            if not ok:
                continue
            buckets.setdefault(_month_day_key(d), []).append(float(v))
        self._doy_mean = {key: float(np.mean(vals)) for key, vals in buckets.items()}
        return FitResult(epochs=0, best_epoch=0)

    def predict(self, X: Sequences) -> Predictions:
        n = len(X.anchor_dates)
        h = len(self._horizons)
        y_pred = np.empty((n, h), dtype=np.float64)
        for i, anchor in enumerate(X.anchor_dates):
            for j, horizon in enumerate(self._horizons):
                target_date = anchor + timedelta(days=horizon)
                y_pred[i, j] = self._doy_mean.get(_month_day_key(target_date), self._overall_mean)
        return Predictions(y_pred=y_pred, anchor_dates=X.anchor_dates, horizons=self._horizons)

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "model": self.name,
                    "horizons": list(self._horizons),
                    "doy_mean": self._doy_mean,
                    "overall_mean": self._overall_mean,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, device: Device) -> "ClimatologyAdapter":
        data = json.loads(path.read_text(encoding="utf-8"))
        adapter = cls()
        adapter._horizons = tuple(data["horizons"])
        adapter._doy_mean = data["doy_mean"]
        adapter._overall_mean = data["overall_mean"]
        return adapter
