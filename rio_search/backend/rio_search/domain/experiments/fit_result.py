"""`FitResult`: resultado de `ModelAdapterPort.fit` (Fase 2, docs/rio_search_plan.md §3.3).
Para los baselines naive (Fase 2) es siempre `epochs=0` (no hay entrenamiento iterativo,
Decision #13 no aplica: son deterministicos). La Fase 3 (BiLSTM) lo llena con curvas reales.
Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FitResult:
    epochs: int
    best_epoch: int
    train_losses: tuple[float, ...] = ()
    val_losses: tuple[float, ...] = ()
