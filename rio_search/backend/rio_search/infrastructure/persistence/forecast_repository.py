"""`SqliteForecastRepository` (Fase 6, docs/rio_search_plan.md §3.8 paso 4: "guarda `Forecast`
en SQLite + `data/forecasts/*.parquet`"). Implementa
`application.ports.forecast_repository.ForecastRepositoryPort`: metadata + puntos en SQLite
(consulta rapida para la API/UI, mismo criterio que `infrastructure.persistence.sqlite_cache`),
y un parquet nuevo por corrida bajo `data/forecasts/` (Polars, Decision #9) -- la copia
"de archivo" que pide el plan, trazable por nombre de archivo (`<target>_<as_of>_<issued_at>.
parquet`).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import polars as pl

from rio_search.domain.predictions.forecast import Forecast, ForecastPoint
from rio_search.domain.shared.target_variable import TargetVariable

_UNSAFE_CHARS = re.compile(r"[^0-9A-Za-z_.-]")


class SqliteForecastRepository:
    """Implementa `application.ports.forecast_repository.ForecastRepositoryPort`."""

    def __init__(self, db_path: Path, parquet_dir: Path) -> None:
        self._db_path = db_path
        self._parquet_dir = parquet_dir
        db_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS forecasts ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL, as_of TEXT NOT NULL, "
            "issued_at TEXT NOT NULL, payload TEXT NOT NULL, parquet_path TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_forecasts_target_issued "
            "ON forecasts (target, issued_at DESC)"
        )
        self._conn.commit()

    def save(self, forecast: Forecast) -> None:
        parquet_path = self._parquet_path(forecast)
        _write_parquet(forecast, parquet_path)
        payload = json.dumps(_to_dict(forecast), ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO forecasts (target, as_of, issued_at, payload, parquet_path) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                forecast.target.value,
                forecast.as_of.isoformat(),
                forecast.issued_at,
                payload,
                str(parquet_path),
            ),
        )
        self._conn.commit()

    def latest(self, target: TargetVariable) -> Forecast | None:
        row = self._conn.execute(
            "SELECT payload FROM forecasts WHERE target = ? ORDER BY issued_at DESC LIMIT 1",
            (target.value,),
        ).fetchone()
        if row is None:
            return None
        return _from_dict(json.loads(row[0]))

    def list_recent(self, target: TargetVariable, max_results: int = 30) -> list[Forecast]:
        rows = self._conn.execute(
            "SELECT payload FROM forecasts WHERE target = ? ORDER BY issued_at DESC LIMIT ?",
            (target.value, max_results),
        ).fetchall()
        return [_from_dict(json.loads(row[0])) for row in rows]

    def close(self) -> None:
        self._conn.close()

    def _parquet_path(self, forecast: Forecast) -> Path:
        safe_issued_at = _UNSAFE_CHARS.sub("-", forecast.issued_at)
        filename = f"{forecast.target.value}_{forecast.as_of.isoformat()}_{safe_issued_at}.parquet"
        return self._parquet_dir / filename


def _write_parquet(forecast: Forecast, path: Path) -> None:
    pl.DataFrame(
        {
            "target": [forecast.target.value] * len(forecast.points),
            "as_of": [forecast.as_of] * len(forecast.points),
            "issued_at": [forecast.issued_at] * len(forecast.points),
            "champion_run_id": [forecast.champion_run_id] * len(forecast.points),
            "champion_model_name": [forecast.champion_model_name] * len(forecast.points),
            "device_type": [forecast.device_type] * len(forecast.points),
            "data_lag_days": [forecast.data_lag_days] * len(forecast.points),
            "dataset_delta_version": [forecast.dataset_delta_version] * len(forecast.points),
            "forecast_run_id": [forecast.forecast_run_id] * len(forecast.points),
            "horizonte": [p.horizon for p in forecast.points],
            "fecha_objetivo": [p.target_date for p in forecast.points],
            "valor": [p.value for p in forecast.points],
        }
    ).write_parquet(path)


def _to_dict(forecast: Forecast) -> dict:
    return {
        "target": forecast.target.value,
        "as_of": forecast.as_of.isoformat(),
        "issued_at": forecast.issued_at,
        "dataset_delta_version": forecast.dataset_delta_version,
        "dataset_sha256": forecast.dataset_sha256,
        "champion_run_id": forecast.champion_run_id,
        "champion_model_name": forecast.champion_model_name,
        "device_type": forecast.device_type,
        "data_lag_days": forecast.data_lag_days,
        "forecast_run_id": forecast.forecast_run_id,
        "published_path": forecast.published_path,
        "points": [
            {"horizon": p.horizon, "target_date": p.target_date.isoformat(), "value": p.value}
            for p in forecast.points
        ],
    }


def _from_dict(data: dict) -> Forecast:
    points = tuple(
        ForecastPoint(
            horizon=int(p["horizon"]),
            target_date=date.fromisoformat(p["target_date"]),
            value=float(p["value"]),
        )
        for p in data["points"]
    )
    return Forecast(
        target=TargetVariable(data["target"]),
        as_of=date.fromisoformat(data["as_of"]),
        issued_at=data["issued_at"],
        dataset_delta_version=int(data["dataset_delta_version"]),
        dataset_sha256=data["dataset_sha256"],
        champion_run_id=data["champion_run_id"],
        champion_model_name=data["champion_model_name"],
        device_type=data["device_type"],
        data_lag_days=int(data["data_lag_days"]),
        points=points,
        forecast_run_id=data.get("forecast_run_id"),
        published_path=data.get("published_path"),
    )
