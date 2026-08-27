"""`TrainingSpec`: bloque `training:` del YAML de experimento (Fase 2, docs/rio_search_plan.md
§4.1). Los baselines naive (Fase 2) no entrenan (`FitResult.epochs == 0` siempre) y solo usan
`seed`/`device`; el resto de los campos existe para que la Fase 3 (BiLSTM) reuse el mismo VO sin
cambiar `ExperimentConfig`. Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TrainingSpec:
    max_epochs: int = 1
    batch_size: int = 1
    optimizer_name: str = "adam"
    optimizer_lr: float = 0.001
    optimizer_weight_decay: float = 0.0
    loss: str = "mse"
    early_stopping_monitor: str = "val/loss"
    early_stopping_patience: int = 25
    grad_clip: float = 0.0
    seed: int = 42
    device: str = "auto"  # application.ports.device_resolver.PreferredDevice

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TrainingSpec":
        data = data or {}
        optimizer = data.get("optimizer") or {}
        early_stopping = data.get("early_stopping") or {}
        return cls(
            max_epochs=int(data.get("max_epochs", 1)),
            batch_size=int(data.get("batch_size", 1)),
            optimizer_name=str(optimizer.get("name", "adam")),
            optimizer_lr=float(optimizer.get("lr", 0.001)),
            optimizer_weight_decay=float(optimizer.get("weight_decay", 0.0)),
            loss=str(data.get("loss", "mse")),
            early_stopping_monitor=str(early_stopping.get("monitor", "val/loss")),
            early_stopping_patience=int(early_stopping.get("patience", 25)),
            grad_clip=float(data.get("grad_clip", 0.0)),
            seed=int(data.get("seed", 42)),
            device=str(data.get("device", "auto")),
        )
