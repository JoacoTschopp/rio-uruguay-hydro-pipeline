"""`FitResult`: resultado de `ModelAdapterPort.fit` (Fase 2, docs/rio_search_plan.md §3.3).
Para los baselines naive (Fase 2) es siempre `epochs=0` (no hay entrenamiento iterativo,
Decision #13 no aplica: son deterministicos). La Fase 3 (`BaseTorchAdapter`, §3.12) lo llena
con curvas reales: `epoch_seconds[i]` es el tiempo del epoch `i+1` (mismo orden que
`train_losses`/`val_losses`, listo para loguear a MLflow con `step=epoch`);
`train_to_best_epoch_s` = tiempo acumulado hasta (e incluyendo) `best_epoch`;
`train_samples_per_s` = throughput de entrenamiento (§3.12). Sin dependencias del proyecto
(regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FitResult:
    epochs: int
    best_epoch: int
    train_losses: tuple[float, ...] = ()
    val_losses: tuple[float, ...] = ()
    epoch_seconds: tuple[float, ...] = ()
    train_to_best_epoch_s: float = 0.0
    train_samples_per_s: float = 0.0
