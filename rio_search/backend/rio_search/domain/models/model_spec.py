"""`ModelSpec`: nombre + hiperparametros de un modelo enchufable (Fase 2, docs/rio_search_plan.md
§3.3, §4.1: bloque `model:` del YAML de experimento). `family` no viene del YAML -- lo resuelve
`RunSearch` a partir de la clase que devuelve el `ModelRegistry` (`adapter_cls.family`), asi el
YAML nunca puede declarar una familia que no coincide con el adaptador real registrado. Sin
dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.models.model_family import ModelFamily


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str
    horizon_strategy: HorizonStrategy
    params: dict[str, Any] = field(default_factory=dict)
    family: ModelFamily | None = None

    def with_family(self, family: ModelFamily) -> "ModelSpec":
        return replace(self, family=family)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelSpec":
        return cls(
            name=str(data["name"]),
            horizon_strategy=HorizonStrategy(data.get("horizon_strategy", "multi_output")),
            params=dict(data.get("params") or {}),
        )
