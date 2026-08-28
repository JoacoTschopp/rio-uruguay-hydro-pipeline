"""`RidgeAdapter` (Fase 9, docs/rio_search_plan.md §3.3, §5): segundo modelo enchufable,
agregado *solo* con este archivo + un YAML nuevo (`configs/experiments/ridge_baseline_v1.yaml`) --
sin tocar `domain/` ni `application/` (criterio de cierre de la Fase 9, verificado con
`git diff --stat`). Reusa exactamente el mismo `ModelAdapterPort` (duck typing, igual que los
adaptadores naive de la Fase 2 y `BaseTorchAdapter` de la Fase 3) y el mismo `Sequences.X`
`(N, lookback, n_features)` que ya construye `infrastructure.datasets.sequence_builder` para
BiLSTM -- la ventana de `sequence.lookback_days` **es** el "ridge con lags" del plan (§5, Fase 9):
se aplana `(lookback, n_features)` a un vector `(lookback * n_features,)` por fila, así cada
feature rezagado dentro de la ventana entra como una columna explícita de la regresión (a
diferencia de la LSTM, que recorre la secuencia, `sklearn.linear_model.Ridge` no modela el tiempo
por sí solo; el aplanado es lo que le da "memoria" de los `lookback_days` anteriores).

Primer adaptador de `ModelFamily.SKLEARN` (Fase 2 ya definía el enum, Fase 3 solo usó `NAIVE`/
`TORCH`): `RunSearch._prepare_trial_data` (Decision 040) ya trata "cualquier familia que no sea
NAIVE" igual -- pasa por `BuildFeatureMatrix` con las columnas reales de `features.groups` --
así que no hizo falta ninguna rama nueva ahí, la Fase 9 lo confirma en la práctica.

Multi-output real (no una única regresión multi-salida de sklearn): un `Ridge` por columna de
horizonte, cada uno ajustado sólo con las filas que tienen ese target no-nulo -- mismo problema
que huecos reales de calendario le plantea a `BaseTorchAdapter` (Decision 043, §2.1), pero
`Ridge.fit()` no acepta NaN en absoluto (a diferencia del enmascarado por batch de PyTorch), así
que acá se enmascara por fila **antes** de llamar a `.fit()`. Un `Ridge` con `n_outputs=1`
(`per_horizon`) es el mismo bucle con una sola vuelta -- "un adaptador que soporte `n_outputs=1`
ya soporta `per_horizon` gratis" (§3.3) también vale para este adaptador.

Sin entrenamiento iterativo (Ridge se resuelve en forma cerrada, Decision #13 no aplica) --
igual que los baselines naive (Fase 2, `FitResult(epochs=0, ...)`), pero acá se reporta
`epochs=1` con una única "curva" de 1 punto (loss = MSE medio sobre horizontes válidos): a
diferencia de naive, este modelo sí aprende parámetros de un ajuste real, y un punto de
`train/loss`+`val/loss` en MLflow es más útil para comparar tiempo/costo (§3.12) que nada.

Serializacion (mismo criterio pragmatico que Decision 039 para torch: sin flavor de MLflow,
artefacto plano propio, ver `base_torch_adapter.py`) -- `pickle` de la lista de `Ridge` (uno
por horizonte) + `architecture.json` con metadatos. `pickle`/`sklearn` no importan pandas al
operar sobre `numpy.ndarray` puro (nunca un `DataFrame`), así que esto no viola la Decision #9
(`test_no_pandas_in_env` lo sigue verificando: pandas no está instalado en el entorno).
"""

from __future__ import annotations

import json
import pickle
import time
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge

from rio_search.domain.experiments.fit_result import FitResult
from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_registry import register_model
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.types import Predictions


@register_model("ridge")
class RidgeAdapter:
    """Implementa `application.ports.model_adapter.ModelAdapterPort` (duck typing, mismo
    criterio que los adaptadores naive/torch -- no hereda el Protocol)."""

    name = "ridge"
    family = ModelFamily.SKLEARN
    supports = {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}

    def __init__(self) -> None:
        self._spec: ModelSpec | None = None
        self._horizons: tuple[int, ...] = ()
        self._n_features: int = 0
        self._n_outputs: int = 0
        self._alpha: float = 1.0
        self._models: list[Ridge] | None = None

    # --- application.ports.model_adapter.ModelAdapterPort ---
    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None:
        horizons = tuple(int(h) for h in spec.params.get("horizons", []))
        if horizons and len(horizons) != n_outputs:
            raise ValueError(f"n_outputs={n_outputs} no coincide con horizons={horizons}")
        self._spec = spec
        self._horizons = horizons
        self._n_features = n_features
        self._n_outputs = n_outputs
        self._alpha = float(spec.params.get("alpha", 1.0))
        self._models = None

    def fit(
        self,
        train: Sequences,
        val: Sequences,
        training: Any,
        callbacks: Any = None,
        train_y: np.ndarray | None = None,
        val_y: np.ndarray | None = None,
    ) -> FitResult:
        if train_y is None or val_y is None:
            raise ValueError(
                f"{self.name}.fit() requiere train_y/val_y (Targets.y, mismo contrato que "
                "BaseTorchAdapter, Decision 040): entrena regresion supervisada real contra el "
                "target futuro, no contra el propio Sequences.X (a diferencia de los baselines "
                "naive, Fase 2)."
            )

        start = time.perf_counter()
        X_train = self._flatten(train.X)
        X_val = self._flatten(val.X)
        n_outputs = train_y.shape[1]

        models: list[Ridge] = []
        train_sq_errors: list[float] = []
        val_sq_errors: list[float] = []

        for j in range(n_outputs):
            y_col = train_y[:, j]
            mask = np.isfinite(y_col)
            model = Ridge(alpha=self._alpha)
            if mask.any():
                model.fit(X_train[mask], y_col[mask])
            else:
                # Columna de horizonte sin ningun target valido en TRAIN (huecos de calendario
                # extremos, §2.1): un Ridge "nulo" (ajustado a un unico punto en el origen) para
                # no romper el resto del trial -- prediccion constante 0.0, coherente con no
                # tener senial de entrenamiento.
                model.fit(np.zeros((1, X_train.shape[1])), np.zeros(1))
            models.append(model)

            train_pred = model.predict(X_train)
            if mask.any():
                train_sq_errors.append(float(np.mean((train_pred[mask] - y_col[mask]) ** 2)))

            val_col = val_y[:, j]
            val_mask = np.isfinite(val_col)
            if val_mask.any():
                val_pred = model.predict(X_val)
                val_sq_errors.append(float(np.mean((val_pred[val_mask] - val_col[val_mask]) ** 2)))

        self._models = models
        elapsed = time.perf_counter() - start

        train_loss = float(np.mean(train_sq_errors)) if train_sq_errors else float("nan")
        val_loss = float(np.mean(val_sq_errors)) if val_sq_errors else float("nan")
        n_train = X_train.shape[0]
        samples_per_s = (n_train / elapsed) if elapsed > 0 else 0.0

        return FitResult(
            epochs=1,
            best_epoch=1,
            train_losses=(train_loss,),
            val_losses=(val_loss,),
            epoch_seconds=(elapsed,),
            train_to_best_epoch_s=elapsed,
            train_samples_per_s=samples_per_s,
        )

    def predict(self, X: Sequences) -> Predictions:
        if self._models is None:
            raise RuntimeError(f"{self.name}.predict() llamado antes de build()+fit()/load()")
        x_flat = self._flatten(X.X)
        columns = [model.predict(x_flat) for model in self._models]
        y_pred = np.stack(columns, axis=1).astype(np.float64)
        return Predictions(y_pred=y_pred, anchor_dates=X.anchor_dates, horizons=self._horizons)

    def save(self, path: Path) -> None:
        if self._models is None:
            raise RuntimeError(f"{self.name}.save() llamado antes de build()+fit()")
        out_dir = path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "ridge_models.pkl").open("wb") as f:
            pickle.dump(self._models, f)
        architecture = {
            "model": self.name,
            "n_features": self._n_features,
            "n_outputs": self._n_outputs,
            "horizons": list(self._horizons),
            "alpha": self._alpha,
            "params": dict(self._spec.params) if self._spec is not None else {},
        }
        (out_dir / "architecture.json").write_text(
            json.dumps(architecture, indent=2, default=str), encoding="utf-8"
        )
        (out_dir / "README.md").write_text(
            f"{self.name}: pickle.dump(list[sklearn.linear_model.Ridge]) + architecture.json "
            "(mismo criterio pragmatico que Decision 039, docs/decisions.md, para torch) -- sin "
            "flavor de MLflow. Cargar con `RidgeAdapter.load(path, device)`.\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, device: Device) -> "RidgeAdapter":
        src_dir = path.parent
        architecture = json.loads((src_dir / "architecture.json").read_text(encoding="utf-8"))
        with (src_dir / "ridge_models.pkl").open("rb") as f:
            models = pickle.load(f)
        adapter = cls()
        adapter._n_features = int(architecture["n_features"])
        adapter._n_outputs = int(architecture["n_outputs"])
        adapter._horizons = tuple(architecture["horizons"])
        adapter._alpha = float(architecture["alpha"])
        adapter._spec = ModelSpec(
            name=architecture["model"],
            horizon_strategy=HorizonStrategy.MULTI_OUTPUT,
            params=architecture.get("params", {}),
            family=ModelFamily.SKLEARN,
        )
        adapter._models = models
        return adapter

    # --- helpers ---
    @staticmethod
    def _flatten(x: np.ndarray) -> np.ndarray:
        """`(N, lookback, n_features)` -> `(N, lookback * n_features)`: cada feature rezagado
        dentro de la ventana entra como una columna explicita de la regresion ("ridge con
        lags", §5, Fase 9)."""
        return np.ascontiguousarray(x).reshape(x.shape[0], -1).astype(np.float64)
