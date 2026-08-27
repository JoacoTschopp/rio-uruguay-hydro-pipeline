"""`BacktestRecent` (Fase 6, docs/rio_search_plan.md §3.8, §3.9): "cada dia que llega un
observado nuevo se compara contra lo que se predijo". Recorre los pronosticos recientes
guardados por `IssueDailyForecast` (`ForecastRepositoryPort`) y, para cada `ForecastPoint` cuya
`target_date` ya tiene un valor observado en el dataset actual, calcula el error. Puntos cuya
`target_date` todavia no llego (o llego pero Gold no la tiene, §2.1: huecos de calendario en el
target) quedan con `observed=None`/`error=None` -- no se descartan, la UI los muestra como
"pendiente".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from rio_search.application.ports.dataset_repository import DatasetRepository
from rio_search.application.ports.forecast_repository import ForecastRepositoryPort
from rio_search.domain.shared.target_variable import TargetVariable

DEFAULT_MAX_FORECASTS = 30


@dataclass(frozen=True, slots=True)
class BacktestPoint:
    forecast_run_id: str | None
    issued_at: str
    as_of: date
    horizon: int
    target_date: date
    predicted: float
    observed: float | None
    error: float | None  # observado - predicho; None si todavia no hay observado

    @property
    def abs_error(self) -> float | None:
        return abs(self.error) if self.error is not None else None


class BacktestRecent:
    def __init__(
        self, forecast_repository: ForecastRepositoryPort, dataset_repository: DatasetRepository
    ) -> None:
        self._forecast_repository = forecast_repository
        self._dataset_repository = dataset_repository

    def execute(
        self, target: TargetVariable, max_forecasts: int = DEFAULT_MAX_FORECASTS
    ) -> tuple[BacktestPoint, ...]:
        forecasts = self._forecast_repository.list_recent(target, max_results=max_forecasts)
        if not forecasts:
            return ()

        # `mode="offline"`: `IssueDailyForecast` ya refresco el dataset en su propia corrida; el
        # backtest (leido por la UI en cada visita a "Pronostico de hoy") no debe volver a pegarle
        # a Databricks (mismo criterio que `GET /api/datasets?mode=offline` por default, Fase 4).
        _, df = self._dataset_repository.load(mode="offline")
        actual = _actual_by_date(df, target)

        points: list[BacktestPoint] = []
        for forecast in forecasts:
            for point in forecast.points:
                observed = actual.get(point.target_date)
                error = (observed - point.value) if observed is not None else None
                points.append(
                    BacktestPoint(
                        forecast_run_id=forecast.forecast_run_id,
                        issued_at=forecast.issued_at,
                        as_of=forecast.as_of,
                        horizon=point.horizon,
                        target_date=point.target_date,
                        predicted=point.value,
                        observed=observed,
                        error=error,
                    )
                )
        return tuple(points)


def _actual_by_date(df: pl.DataFrame, target: TargetVariable) -> dict[date, float]:
    rows = df.select(["fecha", target.actual_column]).drop_nulls().iter_rows(named=True)
    return {row["fecha"]: float(row[target.actual_column]) for row in rows}
