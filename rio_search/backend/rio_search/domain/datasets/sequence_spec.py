"""`SequenceSpec` y `TargetSpec`: parametros de ventaneo y de targets (docs/rio_search_plan.md
§3.6, §4.1: bloques `sequence:` y `dataset:` del YAML de experimento). Sin dependencias del
proyecto (regla de `domain`); quien construye los tensores es
`infrastructure.datasets.sequence_builder.SequenceBuilder` /
`infrastructure.datasets.target_builder.TargetBuilder`.
"""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.shared.target_variable import TargetVariable


@dataclass(frozen=True, slots=True)
class SequenceSpec:
    lookback_days: int

    def __post_init__(self) -> None:
        if self.lookback_days <= 0:
            raise ValueError(f"lookback_days debe ser positivo, recibido {self.lookback_days}")


@dataclass(frozen=True, slots=True)
class TargetSpec:
    target: TargetVariable
    horizons: tuple[int, ...]
    strategy: HorizonStrategy

    def __post_init__(self) -> None:
        if not self.horizons:
            raise ValueError("TargetSpec requiere al menos un horizonte")
