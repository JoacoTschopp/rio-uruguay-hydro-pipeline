"""Puerto de persistencia de pronosticos (Fase 6, docs/rio_search_plan.md §3.8: "guarda
`Forecast` en SQLite + `data/forecasts/*.parquet`"). `IssueDailyForecast` escribe,
`BacktestRecent` y la API (`GET /api/forecasts/*`) leen.
"""

from __future__ import annotations

from typing import Protocol

from rio_search.domain.predictions.forecast import Forecast
from rio_search.domain.shared.target_variable import TargetVariable


class ForecastRepositoryPort(Protocol):
    def save(self, forecast: Forecast) -> None:
        """Persiste en SQLite (metadata + puntos) y en un parquet nuevo bajo
        `data/forecasts/` (§3.8) -- nunca pisa un pronostico anterior, cada `issued_at` es un
        registro nuevo (permite el backtest movil de `BacktestRecent`)."""
        ...

    def latest(self, target: TargetVariable) -> Forecast | None:
        """El pronostico mas reciente por `issued_at` para este target, o `None`."""
        ...

    def list_recent(self, target: TargetVariable, max_results: int = 30) -> list[Forecast]:
        """Mas recientes primero (`GET /api/forecasts/history`, §3.9)."""
        ...
