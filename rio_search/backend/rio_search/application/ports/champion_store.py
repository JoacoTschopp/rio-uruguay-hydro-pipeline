"""Puerto de persistencia local del campeon vigente (Fase 6, docs/rio_search_plan.md §3.5:
"Copia local en SQLite para operar sin red"). `PromoteChampion` escribe, `IssueDailyForecast`
lee -- separados por el mismo motivo que `TrackingPort`/`TrackingReadPort` (Fase 4)."""

from __future__ import annotations

from typing import Protocol

from rio_search.domain.predictions.champion import Champion
from rio_search.domain.shared.target_variable import TargetVariable


class ChampionStorePort(Protocol):
    def set(self, champion: Champion) -> None:
        """Upsert por `target`: cada target (`caudal`/`nivel`) tiene un unico campeon vigente."""
        ...

    def get(self, target: TargetVariable) -> Champion | None:
        """`None` si nunca se promovio un campeon para este target."""
        ...

    def history(self, target: TargetVariable, max_results: int = 50) -> list[Champion]:
        """Todas las promociones pasadas de este target, mas recientes primero (auditoria de
        `§8`: "revision de nombres, aliases y politica de versiones")."""
        ...
