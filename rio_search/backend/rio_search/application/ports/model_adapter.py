"""`ModelAdapterPort` (Fase 2, docs/rio_search_plan.md §3.3): interfaz que implementa cada
modelo enchufable (`persistence`, `climatology`, `seasonal_naive` en esta fase; `bilstm`,
`ridge`, ... despues). Importa `Sequences`/`Predictions` de `infrastructure` (no solo de
`domain`): mismo criterio pragmatico que ya usa `application.datasets.build_feature_matrix`
(Fase 1) importando `infrastructure.preprocess.*` -- son los contenedores de datos (con NumPy)
que fluyen entre la capa de datasets (Fase 1) y los adaptadores de modelo (Fase 2), y viven en
`infrastructure` porque el dominio de este repo se mantiene sin dependencias de terceros.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from rio_search.domain.experiments.fit_result import FitResult
from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.experiments.training_spec import TrainingSpec
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.types import Predictions


class FitCallbacks(Protocol):
    def on_epoch_end(self, epoch: int, train_loss: float, val_loss: float) -> None: ...


class ModelAdapterPort(Protocol):
    name: str
    family: ModelFamily
    supports: set[HorizonStrategy]

    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None:
        """`spec.params` trae los horizontes reales bajo `"horizons"` (inyectados por
        `RunSearch` desde `dataset.horizons` del YAML, no vienen del bloque `model:`)."""
        ...

    def fit(
        self,
        train: Sequences,
        val: Sequences,
        training: TrainingSpec,
        callbacks: FitCallbacks | None = None,
    ) -> FitResult:
        """Para los baselines naive (Fase 2) es un no-op deterministico
        (`FitResult(epochs=0, ...)`): no hay entrenamiento iterativo (Decision #13 no aplica)."""
        ...

    def predict(self, X: Sequences) -> Predictions: ...

    def save(self, path: Path) -> None: ...

    @classmethod
    def load(cls, path: Path, device: Device) -> "ModelAdapterPort": ...
