"""Puerto de medicion de tiempos (Decisiones #13 y #14, docs/rio_search_plan.md §3.12).

El tiempo no limita nada, pero se registra todo: es un resultado de la tesis, no telemetria.
Claves fijas, siempre en segundos, siempre bajo `time/*` (ver la tabla de §3.12).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol


class Stopwatch(Protocol):
    def track(self, name: str) -> AbstractContextManager[None]:
        """`with stopwatch.track("train_total"): ...` — perf_counter(), y en CUDA
        sincroniza antes de detener el reloj para que la ejecucion asincronica de la
        GPU no subestime el tiempo."""
        ...

    def elapsed(self, name: str) -> float | None:
        """Ultima medicion de `name`, o None si nunca se trackeo."""
        ...

    def history(self, name: str) -> list[float]:
        """Todas las mediciones de `name` en orden (p. ej. `train_epoch_s` por epoch)."""
        ...

    def as_metrics(self, prefix: str = "time/") -> dict[str, float]:
        """Ultima medicion de cada nombre trackeado, con el prefijo fijo `time/`."""
        ...
