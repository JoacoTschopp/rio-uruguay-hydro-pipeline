"""Puerto de alias de Unity Catalog (Decision #12, docs/rio_search_plan.md §3.5: "alias
`champion_<target>` apunta a la version campeona"). Separado de `TrackingPort` (Fase 2) a
proposito: `TrackingPort` es la frontera de escritura de `RunSearch` (jerarquia de runs, tags,
metricas) y no necesita saber de alias de modelos registrados -- solo `PromoteChampion` (Fase 6)
llama esto, despues de que un run ya registro una version via `TrackingPort.register_model`."""

from __future__ import annotations

from typing import Protocol


class ModelAliasPort(Protocol):
    def set_alias(self, name: str, alias: str, version: str) -> None:
        """`name` con formato completo `<catalog>.<schema>.<model>` (p. ej.
        `weather.ml.rio_search_bilstm`); `alias` sin el `@` (p. ej. `champion_caudal`)."""
        ...
