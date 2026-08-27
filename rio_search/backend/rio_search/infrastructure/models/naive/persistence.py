"""`persistence` (Fase 2, docs/rio_search_plan.md §3.3, §5): "predice, para todo horizonte, el
ultimo valor observado" -- la vara contra la que se mide el *skill* de todo lo demas (§3.3).
Sin entrenamiento (`fit` es un no-op deterministico); tambien sirve de referencia interna a
`RunSearch` para calcular `skill_vs_persistence` de *cualquier* modelo (§3.7): cuando el modelo
evaluado es este mismo, la referencia y la prediccion son identicas bit a bit y el skill da
`0.0` exacto (criterio de cierre de la Fase 2).
"""

from __future__ import annotations

import json
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


@register_model("persistence")
class PersistenceAdapter:
    """Implementa `application.ports.model_adapter.ModelAdapterPort`."""

    name = "persistence"
    family = ModelFamily.NAIVE
    supports = {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}

    def __init__(self) -> None:
        self._horizons: tuple[int, ...] = ()

    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None:
        horizons = tuple(int(h) for h in spec.params["horizons"])
        if len(horizons) != n_outputs:
            raise ValueError(f"n_outputs={n_outputs} no coincide con horizons={horizons}")
        self._horizons = horizons

    def fit(self, train: Sequences, val: Sequences, training: Any, callbacks: Any = None) -> FitResult:
        return FitResult(epochs=0, best_epoch=0)

    def predict(self, X: Sequences) -> Predictions:
        last = last_step_value(X)
        y_pred = np.repeat(last.reshape(-1, 1), len(self._horizons), axis=1)
        return Predictions(y_pred=y_pred, anchor_dates=X.anchor_dates, horizons=self._horizons)

    def save(self, path: Path) -> None:
        path.write_text(
            json.dumps({"model": self.name, "horizons": list(self._horizons)}), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path, device: Device) -> "PersistenceAdapter":
        data = json.loads(path.read_text(encoding="utf-8"))
        adapter = cls()
        adapter._horizons = tuple(data["horizons"])
        return adapter
