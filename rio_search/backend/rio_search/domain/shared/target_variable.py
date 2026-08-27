"""`TargetVariable`: caudal | nivel (docs/rio_search_plan.md §2.1, §4.1). Sin dependencias del
proyecto (regla de `domain`)."""

from __future__ import annotations

from enum import Enum


class TargetVariable(str, Enum):
    CAUDAL = "caudal"
    NIVEL = "nivel"

    @property
    def column_prefix(self) -> str:
        """Prefijo real en Gold: `caudal_t_mas_{h}d` pero `nivel_rio_t_mas_{h}d` (no
        `nivel_t_mas_{h}d`) -- así están nombradas las columnas en `training_dataset_v0`."""
        return "caudal" if self is TargetVariable.CAUDAL else "nivel_rio"

    def target_column(self, horizon: int) -> str:
        """p. ej. `CAUDAL.target_column(7)` -> `"caudal_t_mas_7d"`."""
        return f"{self.column_prefix}_t_mas_{horizon}d"

    def target_columns(self, horizons: tuple[int, ...]) -> tuple[str, ...]:
        return tuple(self.target_column(h) for h in horizons)

    @property
    def actual_column(self) -> str:
        """Columna de estado "hoy" en Gold (no LEAD): `caudal_actual_m3s` / `nivel_rio_actual_m`
        (Fase 2, docs/rio_search_plan.md §5). Es "el propio target rezagado" que consumen los
        baselines naive (persistence/climatology/seasonal_naive, §3.3): no usan feature groups,
        solo la serie del propio target."""
        return "caudal_actual_m3s" if self is TargetVariable.CAUDAL else "nivel_rio_actual_m"
