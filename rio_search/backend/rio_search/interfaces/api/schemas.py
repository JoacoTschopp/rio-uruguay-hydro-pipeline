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


# ----------------------------------------------------------------------
# Fase 6 -- Predicciones (§3.8, §3.9): campeon vigente + pronostico diario + backtest movil.
# ----------------------------------------------------------------------


class ChampionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    target: str
    run_id: str
    model_name: str
    metric_name: str
    metric_value: float
    promoted_at: str
    registered_model_name: str | None
    registered_model_version: str | None
    note: str | None


class PromoteChampionIn(BaseModel):
    run_id: str
    target: str = "caudal"
    metric_name: str = "val/kge/mean"
    note: str | None = None


class PredictRunIn(BaseModel):
    """`POST /api/forecasts/run` (boton "Predecir hoy"): dispara `rio-search predict run
    --target <target>` con el campeon vigente, nunca reentrena. Devuelve un `JobOut` como
    `POST /api/jobs` -- se sigue el mismo job por `GET /api/jobs/{id}` y su log por
    `GET /api/jobs/{id}/log` (SSE)."""

    target: str = "caudal"


class ForecastPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    horizon: int
    target_date: str
    value: float


class ForecastOut(BaseModel):
    target: str
    as_of: str
    issued_at: str
    dataset_delta_version: int
    dataset_sha256: str
    champion_run_id: str
    champion_model_name: str
    device_type: str
    data_lag_days: int
    forecast_run_id: str | None
    published_path: str | None
    points: list[ForecastPointOut]


class ForecastHistoryOut(BaseModel):
    forecasts: list[ForecastOut]


class BacktestPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    forecast_run_id: str | None
    issued_at: str
    as_of: str
    horizon: int
    target_date: str
    predicted: float
    observed: float | None
    error: float | None


class BacktestOut(BaseModel):
    target: str
    points: list[BacktestPointOut]


# ----------------------------------------------------------------------
# Fase 7 -- Research (§3.10, §3.9): biblioteca de documentos, notas por seccion y BibTeX.
# ----------------------------------------------------------------------


class DocumentOut(BaseModel):
    slug: str
    title: str
    authors: list[str]
    year: int
    type: str
    venue: str | None
    doi_url: str | None
    tags: list[str]
    file: str | None
    added_at: str


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]


class LinkIn(BaseModel):
    kind: str  # "decision" | "run"
    ref: str


class LinkOut(BaseModel):
    kind: str
    ref: str


class NoteOut(BaseModel):
    slug: str
    sections: dict[str, str]
    links: list[LinkOut]


class NoteUpdateIn(BaseModel):
    sections: dict[str, str] = {}
    links: list[LinkIn] = []


class TagsUpdateIn(BaseModel):
    tags: str  # separados por coma (Tag.parse_many, §3.10)


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    note: NoteOut


class ExportBibtexOut(BaseModel):
    output_path: str
    entry_count: int
    keys: list[str]
