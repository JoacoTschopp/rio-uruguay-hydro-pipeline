"""Modelos Pydantic de la API (Fase 4, docs/rio_search_plan.md §3.9, §5: "OpenAPI documentada;
FastAPI la genera sola si los endpoints estan bien tipados"). Traducen los DTOs de
`application`/`domain` (dataclasses) a la forma que via HTTP -- separados a proposito de esos
DTOs para que un cambio de forma de la API (paginacion, campos opcionales, etc.) no obligue a
tocar `application`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    run_name: str
    experiment_id: str
    parent_run_id: str | None
    status: str
    start_time_ms: int | None
    end_time_ms: int | None
    artifact_uri: str
    tags: dict[str, str]
    params: dict[str, str]
    metrics: dict[str, float]


class SearchOut(BaseModel):
    search: RunOut
    trials: list[RunOut]


class SearchListOut(BaseModel):
    searches: list[SearchOut]


class RunListOut(BaseModel):
    runs: list[RunOut]


class RunDetailOut(BaseModel):
    run: RunOut
    children: list[RunOut]


class RunComparisonOut(BaseModel):
    runs: list[RunOut]
    missing_run_ids: list[str]
    param_diff: dict[str, dict[str, str | None]]


class MetricPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: int
    timestamp_ms: int
    value: float


class MetricSeriesOut(BaseModel):
    run_id: str
    metric: str
    points: list[MetricPointOut]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    label: str
    config_path: str
    status: str
    created_at: str
    started_at: str | None
    ended_at: str | None
    exit_code: int | None
    pid: int | None
    extra: dict[str, str]


class JobListOut(BaseModel):
    jobs: list[JobOut]


class JobSubmitIn(BaseModel):
    config: str  # nombre de archivo relativo a configs/experiments/ (p. ej. "persistence_baseline_v1.yaml")
    label: str | None = None


class DatasetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    delta_version: int
    sha256: str
    rows: int
    fecha_min: str
    fecha_max: str
    columns: list[str]
    punto_prediccion: str | None
    exported_at: str | None


class DatasetOut(BaseModel):
    dataset_version: DatasetVersionOut
    cache_path: str
    mode: str


class FeatureGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    columns: list[str]
    default_on: bool
    description: str


class FeatureCatalogOut(BaseModel):
    groups: list[FeatureGroupOut]
