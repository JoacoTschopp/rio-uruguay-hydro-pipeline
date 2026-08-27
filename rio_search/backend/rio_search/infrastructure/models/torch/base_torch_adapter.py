"""`BaseTorchAdapter` (Fase 3, docs/rio_search_plan.md §3.3, §3.4, §3.12): base comun para
adaptadores PyTorch enchufables. Subclases (p. ej. `bilstm.BiLSTMAdapter`) solo implementan
`_build_network()`; esta clase resuelve el resto del contrato de
`application.ports.model_adapter.ModelAdapterPort`:

* Tensores desde `Sequences.X`/`Targets.y` (ya `float32`/`float64` NumPy, Fase 1) -> `torch`,
  movidos al `Device` resuelto (Decision #6).
* Bucle de entrenamiento con early stopping sobre VAL **por paciencia, nunca por tiempo**
  (Decision #13): `training.max_epochs` es un techo de seguridad (§4.1), no un presupuesto.
* Grad clipping (`training.grad_clip`), seed (`torch.manual_seed`) y determinismo por defecto
  (`cudnn.deterministic`/`cudnn.benchmark`, §3.4) antes de construir la red la primera vez.
* Checkpoint del mejor epoch guardado en CPU (§3.4: "los checkpoints se guardan en CPU para que
  un modelo entrenado en CUDA se pueda re-ejecutar en MPS/CPU sin conversion") y restaurado al
  modelo antes de `predict()`.
* Curvas de loss + `time/train_epoch_s` por epoch (`FitResult.epoch_seconds`, listas para que
  el llamador las loguee a MLflow con `step=epoch`, §3.12) y `train_to_best_epoch_s`/
  `train_samples_per_s`.
* `Targets.y` (Fase 1) puede traer `NaN` por fila/horizonte (huecos reales de calendario en el
  target, §2.1 -- `nivel` sin datos 2025-11-01..2026-03-27, `caudal` sin datos 2026-04-07..05-04;
  no un bug, `EvaluatePredictions` ya lo trata via `coverage`). `fit()` enmascara (`torch.isfinite`)
  antes de la funcion de perdida en cada batch (train) y en VAL: un unico NaN sin enmascarar
  contamina la reduccion `mean()` de PyTorch y diverge el entrenamiento entero desde el primer
  epoch -- hallazgo real (Decision 043, docs/decisions.md), no hipotetico.
* AMP (`torch.autocast`) solo si el device es CUDA (§3.4); en CPU/MPS es un no-op real (no solo
  deshabilitado por flag: nunca se pide `device_type="cuda"` con tensores que no lo son).

Serializacion (Decision 039, docs/decisions.md): sin `mlflow.pytorch.log_model` -- `save()`
escribe `model_state_dict.pth` (`torch.save(state_dict)`, movido a CPU) + `architecture.json`
(metadatos propios: nombre, `n_features`/`n_outputs`, `ModelSpec.params`) en el directorio del
`path` recibido (mismo patron que `infrastructure.tracking.smoke`, Fase 0, y los adaptadores
naive, Fase 2 -- `RunSearch` sube todo el directorio con `log_artifact_dir`, el nombre exacto de
`path` no importa, solo su carpeta). `load()` reconstruye la arquitectura desde
`architecture.json` y hace `torch.load(..., map_location=device)`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from rio_search.domain.experiments.fit_result import FitResult
from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.types import Predictions

_LOSSES: dict[str, type[torch.nn.Module]] = {
    "mse": torch.nn.MSELoss,
    "mae": torch.nn.L1Loss,
    "huber": torch.nn.SmoothL1Loss,
}

_OPTIMIZERS = ("adam", "sgd")


class BaseTorchAdapter:
    """Implementa `application.ports.model_adapter.ModelAdapterPort` (duck typing, sin
    heredar el Protocol -- mismo criterio que los adaptadores naive, Fase 2)."""

    name: str = "base_torch"  # subclase lo pisa (p. ej. "bilstm")
    family = ModelFamily.TORCH
    supports = {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}

    def __init__(self) -> None:
        self._spec: ModelSpec | None = None
        self._horizons: tuple[int, ...] = ()
        self._n_features: int = 0
        self._n_outputs: int = 0
        self._device: Device | None = None
        self._torch_device: torch.device = torch.device("cpu")
        self._model: torch.nn.Module | None = None

    # --- arquitectura: la implementa cada subclase (§3.3, "un archivo nuevo + un YAML") ---
    def _build_network(self) -> torch.nn.Module:
        raise NotImplementedError

    # --- application.ports.model_adapter.ModelAdapterPort ---
    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None:
        horizons = tuple(int(h) for h in spec.params.get("horizons", []))
        if horizons and len(horizons) != n_outputs:
            raise ValueError(f"n_outputs={n_outputs} no coincide con horizons={horizons}")
        self._spec = spec
        self._horizons = horizons
        self._n_features = n_features
        self._n_outputs = n_outputs
        self._device = device
        self._torch_device = torch.device(device.type)

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
                f"{self.name}.fit() requiere train_y/val_y (Targets.y, §3.3, §5): a diferencia "
                "de los baselines naive (Decision 040), un modelo torch entrena regresion "
                "supervisada real contra el target futuro, no contra el propio Sequences.X."
            )

        torch.manual_seed(training.seed)
        if self._torch_device.type == "cuda":
            torch.cuda.manual_seed_all(training.seed)
        # Determinismo por defecto (§3.4): "torch.manual_seed, cudnn.deterministic".
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

        if self._model is None:
            # La red se construye (y sus pesos se inicializan) reciен aca, no en `build()`:
            # necesita el seed de `training` para ser reproducible (Decision #13/§4.3, "misma
            # config + mismo seed + mismo device -> mismas metricas"), y `build()` no recibe
            # `TrainingSpec` (solo `ModelSpec`/device, contrato de §3.3).
            self._model = self._build_network().to(self._torch_device)

        X_train = self._to_torch(train.X)
        y_train = self._to_torch(train_y.astype(np.float32))
        X_val = self._to_torch(val.X)
        y_val = self._to_torch(val_y.astype(np.float32))

        loss_cls = _LOSSES.get(training.loss)
        if loss_cls is None:
            raise ValueError(f"training.loss desconocida: {training.loss!r}. Disponibles: {sorted(_LOSSES)}")
        criterion = loss_cls()
        optimizer = self._build_optimizer(training)

        use_amp = self._torch_device.type == "cuda"
        scaler = torch.amp.GradScaler(device="cuda", enabled=use_amp)

        n_train = X_train.shape[0]
        batch_size = max(1, int(training.batch_size))
        shuffle_generator = torch.Generator(device="cpu").manual_seed(training.seed)

        best_val = float("inf")
        best_epoch = 0
        best_state: dict[str, torch.Tensor] | None = None
        patience_left = max(1, training.early_stopping_patience)
        train_losses: list[float] = []
        val_losses: list[float] = []
        epoch_seconds: list[float] = []

        epoch = 0
        for epoch in range(1, max(1, training.max_epochs) + 1):
            epoch_start = time.perf_counter()
            self._model.train()
            permutation = torch.randperm(n_train, generator=shuffle_generator).to(self._torch_device)
            running_loss = 0.0
            running_valid = 0
            for start in range(0, n_train, batch_size):
                idx = permutation[start : start + batch_size]
                xb, yb = X_train[idx], y_train[idx]
                mask = torch.isfinite(yb)
                if not bool(mask.any()):
                    # Batch entero sin target valido (huecos de calendario reales, §2.1): no
                    # aporta gradiente, se saltea sin romper el resto del epoch.
                    continue
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast(device_type="cuda", enabled=use_amp):
                    pred = self._model(xb)
                    # `Targets.y` (Fase 1) puede traer NaN por fila/horizonte (huecos reales de
                    # calendario en el target, §2.1 -- no un bug: `EvaluatePredictions` ya lo
                    # trata via `coverage`). MSE/MAE/Huber de PyTorch no ignoran NaN por si
                    # solos: un unico NaN en el batch contamina toda la reduccion (`mean()`) y
                    # diverge el entrenamiento entero desde el primer epoch (hallazgo real,
                    # Decision 043). Se enmascara antes de la funcion de perdida.
                    loss = criterion(pred[mask], yb[mask])
                scaler.scale(loss).backward()
                if training.grad_clip and training.grad_clip > 0:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(self._model.parameters(), training.grad_clip)
                scaler.step(optimizer)
                scaler.update()
                n_valid = int(mask.sum().item())
                running_loss += float(loss.detach()) * n_valid
                running_valid += n_valid
            train_loss = running_loss / running_valid if running_valid else float("nan")

            self._model.eval()
            with torch.no_grad():
                val_pred = self._model(X_val)
                val_mask = torch.isfinite(y_val)
                val_loss = (
                    float(criterion(val_pred[val_mask], y_val[val_mask]).detach())
                    if bool(val_mask.any())
                    else float("nan")
                )

            if self._torch_device.type == "cuda":
                torch.cuda.synchronize()
            epoch_seconds.append(time.perf_counter() - epoch_start)
            train_losses.append(train_loss)
            val_losses.append(val_loss)

            if callbacks is not None:
                callbacks.on_epoch_end(epoch, train_loss, val_loss)

            if val_loss < best_val - 1e-9:
                best_val = val_loss
                best_epoch = epoch
                best_state = {k: v.detach().cpu().clone() for k, v in self._model.state_dict().items()}
                patience_left = max(1, training.early_stopping_patience)
            else:
                patience_left -= 1
                if patience_left <= 0:
                    break

        if best_state is not None:
            self._model.load_state_dict(best_state)
        else:
            best_epoch = epoch  # nunca mejoro sobre inf: se queda con el ultimo estado tal cual

        train_total_s = sum(epoch_seconds)
        train_to_best_epoch_s = sum(epoch_seconds[:best_epoch]) if best_epoch else train_total_s
        train_samples_per_s = (n_train * len(epoch_seconds) / train_total_s) if train_total_s > 0 else 0.0

        return FitResult(
            epochs=len(epoch_seconds),
            best_epoch=best_epoch,
            train_losses=tuple(train_losses),
            val_losses=tuple(val_losses),
            epoch_seconds=tuple(epoch_seconds),
            train_to_best_epoch_s=train_to_best_epoch_s,
            train_samples_per_s=train_samples_per_s,
        )

    def predict(self, X: Sequences) -> Predictions:
        if self._model is None:
            raise RuntimeError(f"{self.name}.predict() llamado antes de build()+fit()/load()")
        self._model.eval()
        with torch.no_grad():
            x = self._to_torch(X.X)
            y_pred = self._model(x).detach().cpu().numpy().astype(np.float64)
        return Predictions(y_pred=y_pred, anchor_dates=X.anchor_dates, horizons=self._horizons)

    def save(self, path: Path) -> None:
        if self._model is None:
            raise RuntimeError(f"{self.name}.save() llamado antes de build()+fit()")
        out_dir = path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        state_dict_cpu = {k: v.detach().cpu() for k, v in self._model.state_dict().items()}
        torch.save(state_dict_cpu, out_dir / "model_state_dict.pth")
        architecture = {
            "model": self.name,
            "n_features": self._n_features,
            "n_outputs": self._n_outputs,
            "params": dict(self._spec.params) if self._spec is not None else {},
        }
        (out_dir / "architecture.json").write_text(
            json.dumps(architecture, indent=2, default=str), encoding="utf-8"
        )
        (out_dir / "README.md").write_text(
            f"{self.name}: torch.save(model.state_dict()) + architecture.json (Decision 039, "
            "docs/decisions.md) -- sin mlflow.pytorch.log_model (importa pandas incluso en "
            f"mlflow-skinny). Cargar con `{type(self).__name__}.load(path, device)`.\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, device: Device) -> "BaseTorchAdapter":
        src_dir = path.parent
        architecture = json.loads((src_dir / "architecture.json").read_text(encoding="utf-8"))
        adapter = cls()
        spec = ModelSpec(
            name=architecture["model"],
            horizon_strategy=HorizonStrategy.MULTI_OUTPUT,  # no cambia la arquitectura en si
            params=architecture["params"],
            family=ModelFamily.TORCH,
        )
        adapter.build(
            spec,
            n_features=int(architecture["n_features"]),
            n_outputs=int(architecture["n_outputs"]),
            device=device,
        )
        adapter._model = adapter._build_network().to(adapter._torch_device)
        state_dict = torch.load(src_dir / "model_state_dict.pth", map_location=adapter._torch_device)
        adapter._model.load_state_dict(state_dict)
        adapter._model.eval()
        return adapter

    # --- helpers ---
    def _to_torch(self, array: np.ndarray) -> torch.Tensor:
        """`Sequences.X` (Fase 1) ya es `float32` NumPy contiguo -- `torch.from_numpy` +
        `.to(device)` sin copiar de mas."""
        return torch.from_numpy(np.ascontiguousarray(array)).to(self._torch_device)

    def _build_optimizer(self, training: Any) -> torch.optim.Optimizer:
        if self._model is None:
            raise RuntimeError("_build_optimizer llamado antes de construir la red")
        if training.optimizer_name not in _OPTIMIZERS:
            raise ValueError(
                f"training.optimizer desconocido: {training.optimizer_name!r}. Disponibles: {_OPTIMIZERS}"
            )
        params = self._model.parameters()
        lr = training.optimizer_lr
        weight_decay = training.optimizer_weight_decay
        if training.optimizer_name == "sgd":
            return torch.optim.SGD(params, lr=lr, weight_decay=weight_decay)
        return torch.optim.Adam(params, lr=lr, weight_decay=weight_decay)
