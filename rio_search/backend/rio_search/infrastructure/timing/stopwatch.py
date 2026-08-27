"""Implementacion del `Stopwatch` con `time.perf_counter()` + `torch.cuda.synchronize()`
(Decisiones #13 y #14, docs/rio_search_plan.md §3.12)."""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

import torch


class PerfCounterStopwatch:
    """Implementa `application.ports.stopwatch.Stopwatch`.

    Guarda la ultima medicion de cada `name` (para `as_metrics`) y el historial completo
    (para series como `train_epoch_s` por `step=epoch`).
    """

    def __init__(self, cuda_sync: bool = True) -> None:
        self._elapsed: dict[str, float] = {}
        self._history: dict[str, list[float]] = defaultdict(list)
        self._cuda_sync = cuda_sync

    @contextmanager
    def track(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            if self._cuda_sync and torch.cuda.is_available():
                torch.cuda.synchronize()
            elapsed = time.perf_counter() - start
            self._elapsed[name] = elapsed
            self._history[name].append(elapsed)

    def elapsed(self, name: str) -> float | None:
        return self._elapsed.get(name)

    def history(self, name: str) -> list[float]:
        return list(self._history.get(name, []))

    def as_metrics(self, prefix: str = "time/") -> dict[str, float]:
        return {f"{prefix}{name}": value for name, value in self._elapsed.items()}
