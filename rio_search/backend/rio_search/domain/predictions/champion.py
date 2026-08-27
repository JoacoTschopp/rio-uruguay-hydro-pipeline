"""`Champion`: agregado raiz del contexto Predictions (docs/rio_search_plan.md §3.2, §3.8).

Invariante que protege (§3.2): "Un `Forecast` declara `as_of` ..., `run_id` del campeon y
`device`" -- este objeto es la fuente de verdad de "cual run de MLflow es el campeon vigente
para un target", fijada por `application.predictions.promote_champion.PromoteChampion` y leida
por `application.predictions.issue_daily_forecast.IssueDailyForecast`. Sin dependencias del
proyecto (regla de `domain`): quien persiste esto es
`infrastructure.persistence.champion_store.SqliteChampionStore`.
"""

from __future__ import annotations

from dataclasses import dataclass

from rio_search.domain.shared.target_variable import TargetVariable


@dataclass(frozen=True, slots=True)
class Champion:
    target: TargetVariable
    run_id: str
    model_name: str
    metric_name: str
    metric_value: float
    promoted_at: str  # ISO 8601 UTC
    registered_model_name: str | None = None
    registered_model_version: str | None = None
    # Nota libre de la promocion -- usada por el agente principal para dejar constancia de que
    # un campeon es "provisorio" (§8 del plan: "revisar weather.ml con el usuario tras la
    # primera corrida registrada") sin inventar un campo de dominio nuevo para eso.
    note: str | None = None

    def as_tags(self) -> dict[str, str]:
        """Tags `rio_search.champion_*` (§3.8) para el run corto de `daily_forecast`."""
        tags = {
            "champion_run_id": self.run_id,
            "champion_model_name": self.model_name,
            "champion_metric_name": self.metric_name,
            "champion_metric_value": f"{self.metric_value:.6f}",
            "champion_promoted_at": self.promoted_at,
        }
        if self.registered_model_name is not None:
            tags["champion_registered_model_name"] = self.registered_model_name
        if self.registered_model_version is not None:
            tags["champion_registered_model_version"] = self.registered_model_version
        return tags
