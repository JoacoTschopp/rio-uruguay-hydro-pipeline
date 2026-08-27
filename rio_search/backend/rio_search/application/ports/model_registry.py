"""Puerto del registro de modelos enchufables (Fase 2, docs/rio_search_plan.md §3.3). La
implementacion real (`domain.models.model_registry.ModelRegistry`) es estructuralmente
compatible con este Protocol (duck typing): `RunSearch` depende de este puerto, no de la clase
concreta, para poder inyectar un registro falso en tests offline (§5).
"""

from __future__ import annotations

from typing import Protocol

from rio_search.application.ports.model_adapter import ModelAdapterPort


class ModelRegistryPort(Protocol):
    def get(self, name: str) -> type[ModelAdapterPort]: ...

    def names(self) -> tuple[str, ...]: ...
