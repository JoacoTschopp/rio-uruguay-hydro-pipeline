"""`Forecast`/`ForecastPoint`: agregado del contexto Predictions (docs/rio_search_plan.md §3.2,
§3.8). Invariante que protege (§3.2): "Un `Forecast` declara `as_of` (ultimo dia con inputs
completos), `dataset_version`, `run_id` del campeon y `device`". Sin dependencias del proyecto
(regla de `domain`): quien lo construye es `application.predictions.issue_daily_forecast.
IssueDailyForecast`, quien lo persiste es `infrastructure.persistence.forecast_repository`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from rio_search.domain.shared.target_variable import TargetVariable


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """`value` en las unidades nativas de Gold (m3/s para caudal, m para nivel) -- ningun
    transform experimental se aplica a las columnas de target (§3.6: los transforms solo tocan
    columnas de *features*), asi que la salida del modelo ya esta en la escala correcta."""

    horizon: int
    target_date: date
    value: float

    def __post_init__(self) -> None:
        if self.horizon <= 0:
            raise ValueError(f"ForecastPoint.horizon debe ser positivo, recibido {self.horizon}")


@dataclass(frozen=True, slots=True)
class Forecast:
    target: TargetVariable
    as_of: date
    issued_at: str  # ISO 8601 UTC
    dataset_delta_version: int
    dataset_sha256: str
    champion_run_id: str
    champion_model_name: str
    device_type: str
    data_lag_days: int
    points: tuple[ForecastPoint, ...]
    forecast_run_id: str | None = None  # run corto en el experimento `daily_forecast` (§3.8)
    published_path: str | None = None  # ruta en el Volume si se publico (--publish, §3.8 paso 5)

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("Forecast requiere al menos un ForecastPoint")
        horizons = [p.horizon for p in self.points]
        if len(horizons) != len(set(horizons)):
            raise ValueError(f"Forecast.points tiene horizontes duplicados: {horizons}")

    @property
    def horizons(self) -> tuple[int, ...]:
        return tuple(sorted(p.horizon for p in self.points))

    def point_for(self, horizon: int) -> ForecastPoint:
        for point in self.points:
            if point.horizon == horizon:
                return point
        raise KeyError(f"Forecast no tiene el horizonte {horizon}; disponibles: {self.horizons}")

    def as_tags(self) -> dict[str, str]:
        """Tags `rio_search.*` del run corto en `daily_forecast` (§3.8)."""
        return {
            "target": self.target.value,
            "as_of": self.as_of.isoformat(),
            "dataset_delta_version": str(self.dataset_delta_version),
            "dataset_sha256": self.dataset_sha256,
            "champion_run_id": self.champion_run_id,
            "champion_model_name": self.champion_model_name,
            "device": self.device_type,
            "data_lag_days": str(self.data_lag_days),
        }
