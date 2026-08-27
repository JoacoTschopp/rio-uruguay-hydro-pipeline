"""Composition root (§3.2, docs/rio_search_plan.md): unico lugar donde `interfaces` conoce
`infrastructure`. `application`/`domain` nunca importan de aca."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from databricks.sdk import WorkspaceClient

from rio_search.infrastructure.databricks.sdk_client import (
    DEFAULT_PROFILE,
    DEFAULT_WAREHOUSE_ID,
    DatabricksGoldCatalog,
    DatabricksJobSubmitter,
    DatabricksStatementExecutor,
    DatabricksVolumeFiles,
    build_workspace_client,
)
from rio_search.infrastructure.datasets.feature_catalog_loader import load_feature_catalog
from rio_search.infrastructure.datasets.gold_parquet_repository import GoldParquetDatasetRepository
from rio_search.infrastructure.datasets.gold_snapshot_sync import GoldSnapshotSync
from rio_search.infrastructure.provenance.git_provenance import GitProvenance
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = BACKEND_DIR / "data" / "gold_snapshot"
DEFAULT_FEATURE_GROUPS_PATH = BACKEND_DIR / "configs" / "feature_groups.yaml"
DEFAULT_EXPERIMENTS_DIR = BACKEND_DIR / "configs" / "experiments"
DEFAULT_READ_CACHE_PATH = BACKEND_DIR / "data" / "read_cache.sqlite3"
DEFAULT_JOBS_DIR = BACKEND_DIR / "data" / "jobs"
DEFAULT_JOB_LOCK_PATH = DEFAULT_JOBS_DIR / "rio_search.lock"
# Fase 6 (Predicciones, §5): copia local del campeon vigente, pronosticos emitidos y cache de
# artefactos descargados del campeon (config/split/features/model, §3.8 paso 2).
DEFAULT_CHAMPIONS_DB_PATH = BACKEND_DIR / "data" / "champions.sqlite3"
DEFAULT_FORECASTS_DB_PATH = BACKEND_DIR / "data" / "forecasts.sqlite3"
DEFAULT_FORECASTS_PARQUET_DIR = BACKEND_DIR / "data" / "forecasts"
DEFAULT_CHAMPION_ARTIFACTS_DIR = BACKEND_DIR / "data" / "champion_artifacts"

# Fase 7 (Research, §3.10): la biblioteca vive fuera de `backend/`, en `rio_search/research/` y
# `rio_search/thesis/common/` (§3.1) -- no en `backend/data/` como el resto del estado local,
# porque es un entregable versionado del repo (catalog/notes en git; solo los PDF de
# `documents/` estan gitignored), no cache/estado descartable.
RIO_SEARCH_DIR = BACKEND_DIR.parent
DEFAULT_RESEARCH_CATALOG_DIR = RIO_SEARCH_DIR / "research" / "catalog"
DEFAULT_RESEARCH_NOTES_DIR = RIO_SEARCH_DIR / "research" / "notes"
DEFAULT_RESEARCH_DOCUMENTS_DIR = RIO_SEARCH_DIR / "research" / "documents"
DEFAULT_REFERENCES_BIB_PATH = RIO_SEARCH_DIR / "thesis" / "common" / "references.bib"
# Fase 8 (Tesis LaTeX, §3.11): `rio-search thesis export` escribe aca, igual que
# `references.bib` de arriba -- son entregables versionados de la tesis, no cache descartable.
DEFAULT_THESIS_FIGURES_DIR = RIO_SEARCH_DIR / "thesis" / "figures"
DEFAULT_THESIS_TABLES_DIR = RIO_SEARCH_DIR / "thesis" / "tables"


@dataclass
class DatabricksCollaborators:
    """Adaptadores reales sobre `databricks-sdk`, listos para componer `GoldSnapshotSync`,
    el CLI de `init-schema` y el run `smoke` de MLflow."""

    client: WorkspaceClient
    statements: DatabricksStatementExecutor
    gold_catalog: DatabricksGoldCatalog
    volume_files: DatabricksVolumeFiles
    job_submitter: DatabricksJobSubmitter


def build_databricks_collaborators(
    profile: str = DEFAULT_PROFILE, warehouse_id: str = DEFAULT_WAREHOUSE_ID
) -> DatabricksCollaborators:
    client = build_workspace_client(profile=profile)
    statements = DatabricksStatementExecutor(client, warehouse_id=warehouse_id)
    return DatabricksCollaborators(
        client=client,
        statements=statements,
        gold_catalog=DatabricksGoldCatalog(statements),
        volume_files=DatabricksVolumeFiles(client),
        job_submitter=DatabricksJobSubmitter(client),
    )


def build_gold_snapshot_sync(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    stopwatch: PerfCounterStopwatch | None = None,
) -> GoldSnapshotSync:
    collaborators = build_databricks_collaborators(profile=profile, warehouse_id=warehouse_id)
    return GoldSnapshotSync(
        gold_catalog=collaborators.gold_catalog,
        files=collaborators.volume_files,
        job_submitter=collaborators.job_submitter,
        cache_dir=cache_dir,
        stopwatch=stopwatch or PerfCounterStopwatch(),
    )


def build_git_provenance() -> GitProvenance:
    return GitProvenance()


def build_feature_catalog(path: Path = DEFAULT_FEATURE_GROUPS_PATH):
    """`FeatureCatalog` cargado de `configs/feature_groups.yaml` (Fase 1, §3.6)."""
    return load_feature_catalog(path)


def build_gold_parquet_repository(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    stopwatch: PerfCounterStopwatch | None = None,
) -> GoldParquetDatasetRepository:
    """`DatasetRepository` (Fase 1, §3.2) sobre el mismo `GoldSnapshotSync` de la Fase 0."""
    sync = build_gold_snapshot_sync(
        profile=profile, warehouse_id=warehouse_id, cache_dir=cache_dir, stopwatch=stopwatch
    )
    return GoldParquetDatasetRepository(sync)


def build_refresh_dataset(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    feature_groups_path: Path = DEFAULT_FEATURE_GROUPS_PATH,
    stopwatch: PerfCounterStopwatch | None = None,
):
    """`RefreshDataset` (Fase 1, §3.2): primer paso obligatorio de `RunSearch` (Fase 2)."""
    from rio_search.application.datasets.refresh_dataset import RefreshDataset

    sw = stopwatch or PerfCounterStopwatch()
    repository = build_gold_parquet_repository(
        profile=profile, warehouse_id=warehouse_id, cache_dir=cache_dir, stopwatch=sw
    )
    catalog = build_feature_catalog(feature_groups_path)
    return RefreshDataset(repository=repository, feature_catalog=catalog, stopwatch=sw)


def build_model_registry():
    """`ModelRegistry` (Fase 2, §3.3) con los adaptadores ya registrados: importar
    `infrastructure.models` dispara los `@register_model` de `naive/*` (persistence,
    climatology, seasonal_naive)."""
    import rio_search.infrastructure.models  # noqa: F401 - efecto secundario: registra adaptadores
    from rio_search.domain.models.model_registry import ModelRegistry

    return ModelRegistry()


def build_tracking(profile: str = DEFAULT_PROFILE):
    """`MlflowDatabricksTracking` (Fase 2, §3.5)."""
    from rio_search.infrastructure.tracking.mlflow_databricks import MlflowDatabricksTracking

    return MlflowDatabricksTracking(profile=profile)


def build_run_search(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    feature_groups_path: Path = DEFAULT_FEATURE_GROUPS_PATH,
):
    """`RunSearch` (Fase 2/3, §3.2, §5): compone `RefreshDataset` (Fase 1), el resolutor de
    device, la procedencia git, el registro de modelos, `BuildFeatureMatrix` (Fase 1/3: lo
    necesitan los modelos que no son `naive`, Decision 040) y el tracking de MLflow. El
    `Stopwatch` compartido con `RefreshDataset` es el mismo objeto que mide
    `time/dataset_refresh_s` (§3.12): por eso `RunSearch` lo recibe ya cableado, no crea el
    suyo."""
    from rio_search.application.datasets.build_feature_matrix import BuildFeatureMatrix
    from rio_search.application.experiments.run_search import RunSearch, RunSearchDependencies
    from rio_search.infrastructure.device.torch_device_resolver import TorchDeviceResolver

    stopwatch = PerfCounterStopwatch()
    refresh_dataset = build_refresh_dataset(
        profile=profile,
        warehouse_id=warehouse_id,
        cache_dir=cache_dir,
        feature_groups_path=feature_groups_path,
        stopwatch=stopwatch,
    )
    deps = RunSearchDependencies(
        refresh_dataset=refresh_dataset,
        device_resolver=TorchDeviceResolver(),
        git_provenance=build_git_provenance(),
        model_registry=build_model_registry(),
        tracking=build_tracking(profile=profile),
        stopwatch=stopwatch,
        stopwatch_factory=PerfCounterStopwatch,
        build_feature_matrix=BuildFeatureMatrix(build_feature_catalog(feature_groups_path)),
    )
    return RunSearch(deps)


# ----------------------------------------------------------------------
# Fase 6 -- Predicciones (§3.8, §5): `PromoteChampion`, `IssueDailyForecast`, `BacktestRecent`.
# ----------------------------------------------------------------------


def build_champion_store(db_path: Path = DEFAULT_CHAMPIONS_DB_PATH):
    """`ChampionStorePort` real (Decision #12, §3.5: "copia local en SQLite")."""
    from rio_search.infrastructure.persistence.champion_store import SqliteChampionStore

    return SqliteChampionStore(db_path)


def build_forecast_repository(
    db_path: Path = DEFAULT_FORECASTS_DB_PATH, parquet_dir: Path = DEFAULT_FORECASTS_PARQUET_DIR
):
    """`ForecastRepositoryPort` real (§3.8 paso 4: "SQLite + `data/forecasts/*.parquet`")."""
    from rio_search.infrastructure.persistence.forecast_repository import SqliteForecastRepository

    return SqliteForecastRepository(db_path, parquet_dir)


def build_model_alias(profile: str = DEFAULT_PROFILE):
    """`ModelAliasPort` real (Decision #12: alias `champion_<target>` en Unity Catalog)."""
    from rio_search.infrastructure.tracking.mlflow_model_alias import MlflowModelAlias

    return MlflowModelAlias(profile=profile)


def build_artifact_repository(profile: str = DEFAULT_PROFILE):
    """`ArtifactRepositoryPort` real (§3.8 paso 2: descarga `config/`, `split/`, `features/`,
    `model/` del run campeon)."""
    from rio_search.infrastructure.tracking.mlflow_artifact_repository import MlflowArtifactRepository

    return MlflowArtifactRepository(profile=profile)


def build_volume_publisher(profile: str = DEFAULT_PROFILE, warehouse_id: str = DEFAULT_WAREHOUSE_ID):
    """`VolumePublisherPort` real (§3.8 paso 5, `--publish`)."""
    from rio_search.infrastructure.databricks.volume_publisher import DatabricksVolumePublisher

    collaborators = build_databricks_collaborators(profile=profile, warehouse_id=warehouse_id)
    return DatabricksVolumePublisher(collaborators.volume_files)


def build_promote_champion(
    profile: str = DEFAULT_PROFILE, championsdb_path: Path = DEFAULT_CHAMPIONS_DB_PATH
):
    """`PromoteChampion` (§3.5, §4.2: `rio-search champions set`)."""
    from rio_search.application.predictions.promote_champion import PromoteChampion

    return PromoteChampion(
        reader=build_tracking_reader(profile=profile),
        store=build_champion_store(championsdb_path),
        model_alias=build_model_alias(profile=profile),
    )


def build_issue_daily_forecast(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    feature_groups_path: Path = DEFAULT_FEATURE_GROUPS_PATH,
    champions_db_path: Path = DEFAULT_CHAMPIONS_DB_PATH,
    forecasts_db_path: Path = DEFAULT_FORECASTS_DB_PATH,
    forecasts_parquet_dir: Path = DEFAULT_FORECASTS_PARQUET_DIR,
    champion_artifacts_dir: Path = DEFAULT_CHAMPION_ARTIFACTS_DIR,
):
    """`IssueDailyForecast` (§3.8): mismo patron de `Stopwatch` compartido con `RefreshDataset`
    que `build_run_search` (Fase 2/3) -- `time/dataset_refresh_s` queda bajo el mismo reloj que
    `time/model_load_s`/`preprocess_s`/`predict_s`/`total_s` de esta corrida."""
    from rio_search.application.predictions.issue_daily_forecast import (
        IssueDailyForecast,
        IssueDailyForecastDependencies,
    )
    from rio_search.infrastructure.device.torch_device_resolver import TorchDeviceResolver

    stopwatch = PerfCounterStopwatch()
    refresh_dataset = build_refresh_dataset(
        profile=profile,
        warehouse_id=warehouse_id,
        cache_dir=cache_dir,
        feature_groups_path=feature_groups_path,
        stopwatch=stopwatch,
    )
    deps = IssueDailyForecastDependencies(
        refresh_dataset=refresh_dataset,
        device_resolver=TorchDeviceResolver(),
        git_provenance=build_git_provenance(),
        champion_store=build_champion_store(champions_db_path),
        tracking_reader=build_tracking_reader(profile=profile),
        artifact_repository=build_artifact_repository(profile=profile),
        tracking=build_tracking(profile=profile),
        model_registry=build_model_registry(),
        feature_catalog=build_feature_catalog(feature_groups_path),
        forecast_repository=build_forecast_repository(forecasts_db_path, forecasts_parquet_dir),
        stopwatch=stopwatch,
        experiment_base_path=rio_search_experiment_base_path(profile),
        artifacts_cache_dir=champion_artifacts_dir,
        volume_publisher=build_volume_publisher(profile=profile, warehouse_id=warehouse_id),
    )
    return IssueDailyForecast(deps)


def build_backtest_recent(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    forecasts_db_path: Path = DEFAULT_FORECASTS_DB_PATH,
    forecasts_parquet_dir: Path = DEFAULT_FORECASTS_PARQUET_DIR,
):
    """`BacktestRecent` (§3.8, §3.9: "backtest movil" de la pagina Pronostico de hoy)."""
    from rio_search.application.predictions.backtest_recent import BacktestRecent

    return BacktestRecent(
        forecast_repository=build_forecast_repository(forecasts_db_path, forecasts_parquet_dir),
        dataset_repository=build_gold_parquet_repository(
            profile=profile, warehouse_id=warehouse_id, cache_dir=cache_dir
        ),
    )


# ----------------------------------------------------------------------
# Fase 4 -- Backend API (§3.9, §5): lectura de MLflow con cache SQLite, JobRunner y el bundle
# `ApiDependencies` que consume `interfaces/api/main.py`.
# ----------------------------------------------------------------------


def build_tracking_reader(profile: str = DEFAULT_PROFILE, cache_path: Path = DEFAULT_READ_CACHE_PATH):
    """`TrackingReadPort` real (Fase 4, §5) cacheado en SQLite (criterio de TTL documentado en
    `infrastructure.tracking.cached_reader`)."""
    from rio_search.infrastructure.persistence.sqlite_cache import SqliteReadCache
    from rio_search.infrastructure.tracking.cached_reader import CachedTrackingReader
    from rio_search.infrastructure.tracking.mlflow_read import MlflowDatabricksTrackingReader

    inner = MlflowDatabricksTrackingReader(profile=profile)
    cache = SqliteReadCache(cache_path)
    return CachedTrackingReader(inner=inner, cache=cache)


def rio_search_experiment_base_path(profile: str = DEFAULT_PROFILE) -> str:
    """`/Users/<profile>/rio_search` (§3.5): raiz de las 'familias' de experimento."""
    return f"/Users/{profile}/rio_search"


def _search_run_command(profile: str, warehouse_id: str):
    """`command_builder` de `SubprocessJobRunner` (Fase 4, §5): el mismo comando que un usuario
    correria a mano (`rio-search search run <config>`), invocado como modulo con el mismo
    interprete que corre la API (`sys.executable`) para no depender de que el `.venv` tenga el
    script de consola instalado en el PATH."""
    import sys

    def build(config_path: Path) -> list[str]:
        return [
            sys.executable,
            "-m",
            "rio_search.interfaces.cli.main",
            "search",
            "run",
            str(config_path),
            "--profile",
            profile,
            "--warehouse-id",
            warehouse_id,
        ]

    return build


def build_job_runner(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    jobs_dir: Path = DEFAULT_JOBS_DIR,
    lock_path: Path = DEFAULT_JOB_LOCK_PATH,
):
    """`SubprocessJobRunner` (Fase 4, §5): un job (una búsqueda) a la vez, con el
    `ProcessLock` portado de `ana_historic_backfill/lock.py` para que tampoco pise a un
    `rio-search search run` corrido a mano en paralelo (aviso operativo de la Fase 3)."""
    from rio_search.infrastructure.jobs.process_lock import ProcessLock
    from rio_search.infrastructure.jobs.subprocess_job_runner import SubprocessJobRunner

    return SubprocessJobRunner(
        command_builder=_search_run_command(profile, warehouse_id),
        log_dir=jobs_dir,
        lock=ProcessLock(lock_path),
        cwd=BACKEND_DIR,
    )


# ----------------------------------------------------------------------
# Fase 7 -- Research (§3.10, §5): biblioteca de documentos, notas y exportacion a BibTeX. Sin
# Databricks/MLflow (Decision #3: sin LLM, biblioteca local); solo filesystem.
# ----------------------------------------------------------------------


def build_document_store(
    catalog_dir: Path = DEFAULT_RESEARCH_CATALOG_DIR,
    notes_dir: Path = DEFAULT_RESEARCH_NOTES_DIR,
    documents_dir: Path = DEFAULT_RESEARCH_DOCUMENTS_DIR,
):
    """`DocumentStorePort` real (§3.10: catalog/*.yaml + notes/*.md + documents/*, sin base de
    datos -- el repo es la base)."""
    from rio_search.infrastructure.research.filesystem_document_store import FileSystemDocumentStore

    return FileSystemDocumentStore(catalog_dir=catalog_dir, notes_dir=notes_dir, documents_dir=documents_dir)


def build_bibliography_exporter():
    """`BibliographyExportPort` real (§3.10: formatea + escribe `references.bib`)."""
    from rio_search.infrastructure.research.bibtex_exporter import FileBibtexExporter

    return FileBibtexExporter()


def build_add_document(store=None):
    from rio_search.application.research.add_document import AddDocument

    return AddDocument(store=store or build_document_store())


def build_update_note(store=None):
    from rio_search.application.research.update_note import UpdateNote

    return UpdateNote(store=store or build_document_store())


def build_tag_document(store=None):
    from rio_search.application.research.tag_document import TagDocument

    return TagDocument(store=store or build_document_store())


def build_export_bibtex(store=None, exporter=None):
    from rio_search.application.research.export_bibtex import ExportBibtex

    return ExportBibtex(
        store=store or build_document_store(), exporter=exporter or build_bibliography_exporter()
    )


def build_export_thesis_artifacts(
    profile: str = DEFAULT_PROFILE,
    read_cache_path: Path = DEFAULT_READ_CACHE_PATH,
    figures_dir: Path = DEFAULT_THESIS_FIGURES_DIR,
    tables_dir: Path = DEFAULT_THESIS_TABLES_DIR,
):
    """`ExportThesisArtifacts` (Fase 8, §3.11, §4.2: `rio-search thesis export`). Reusa el mismo
    `TrackingReadPort` cacheado en SQLite de la Fase 4 (`build_tracking_reader`) -- no hace
    falta un puerto nuevo, solo lee runs ya logueados."""
    from rio_search.application.thesis.export_thesis_artifacts import ExportThesisArtifacts

    return ExportThesisArtifacts(
        reader=build_tracking_reader(profile=profile, cache_path=read_cache_path),
        figures_dir=figures_dir,
        tables_dir=tables_dir,
    )


def build_api_dependencies(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    feature_groups_path: Path = DEFAULT_FEATURE_GROUPS_PATH,
    experiments_dir: Path = DEFAULT_EXPERIMENTS_DIR,
    read_cache_path: Path = DEFAULT_READ_CACHE_PATH,
    jobs_dir: Path = DEFAULT_JOBS_DIR,
    job_lock_path: Path = DEFAULT_JOB_LOCK_PATH,
    champions_db_path: Path = DEFAULT_CHAMPIONS_DB_PATH,
    forecasts_db_path: Path = DEFAULT_FORECASTS_DB_PATH,
    forecasts_parquet_dir: Path = DEFAULT_FORECASTS_PARQUET_DIR,
    research_catalog_dir: Path = DEFAULT_RESEARCH_CATALOG_DIR,
    research_notes_dir: Path = DEFAULT_RESEARCH_NOTES_DIR,
    research_documents_dir: Path = DEFAULT_RESEARCH_DOCUMENTS_DIR,
):
    """Composition root de la API (Fase 4, §5): construye el `ApiDependencies` real que
    `interfaces/api/main.py::create_app()` usa cuando no recibe uno inyectado (los tests de la
    API pasan su propio `ApiDependencies` con `TrackingReadPort`/`JobRunner` falsos, §5).

    Fase 6 (§3.9, "Pronostico de hoy"): agrega `promote_champion` (`POST /api/champions`),
    `champion_store`/`forecast_repository` (`GET /api/champions`, `GET /api/forecasts/*`) y
    `backtest_recent` (`GET /api/forecasts/backtest`) -- todos de solo lectura o de escritura
    liviana (SQLite local + alias UC), nunca disparan `IssueDailyForecast` (esa corrida pesada
    queda en el CLI/Task Scheduler, Decision 044: nunca dos procesos pegandole a Databricks/
    MLflow a la vez con el mismo perfil, y la API ya tiene su propio `JobRunner` serializado
    para eso -- exponer un endpoint que dispare inferencia agregaria una segunda cola paralela
    sin necesidad real para el criterio de cierre de esta fase).

    Fase 7 (§3.10, "Research"): agrega `document_store`/`add_document`/`update_note`/
    `tag_document`/`export_bibtex` -- sin Databricks/MLflow (Decision #3: biblioteca local, sin
    LLM), solo filesystem sobre `rio_search/research/` y `rio_search/thesis/common/`."""
    from rio_search.application.experiments.compare_runs import CompareRuns
    from rio_search.application.experiments.get_run_detail import GetRunDetail
    from rio_search.application.experiments.list_runs import ListRuns
    from rio_search.application.experiments.list_searches import ListSearches
    from rio_search.interfaces.api.dependencies import ApiDependencies

    reader = build_tracking_reader(profile=profile, cache_path=read_cache_path)
    list_runs = ListRuns(reader=reader, base_path=rio_search_experiment_base_path(profile))
    document_store = build_document_store(
        catalog_dir=research_catalog_dir, notes_dir=research_notes_dir, documents_dir=research_documents_dir
    )
    return ApiDependencies(
        reader=reader,
        list_runs=list_runs,
        list_searches=ListSearches(list_runs=list_runs),
        get_run_detail=GetRunDetail(reader=reader),
        compare_runs=CompareRuns(reader=reader),
        job_runner=build_job_runner(
            profile=profile, warehouse_id=warehouse_id, jobs_dir=jobs_dir, lock_path=job_lock_path
        ),
        experiments_dir=experiments_dir,
        snapshot_sync=build_gold_snapshot_sync(
            profile=profile, warehouse_id=warehouse_id, cache_dir=cache_dir
        ),
        feature_catalog=build_feature_catalog(feature_groups_path),
        promote_champion=build_promote_champion(profile=profile, championsdb_path=champions_db_path),
        champion_store=build_champion_store(champions_db_path),
        forecast_repository=build_forecast_repository(forecasts_db_path, forecasts_parquet_dir),
        backtest_recent=build_backtest_recent(
            profile=profile,
            warehouse_id=warehouse_id,
            cache_dir=cache_dir,
            forecasts_db_path=forecasts_db_path,
            forecasts_parquet_dir=forecasts_parquet_dir,
        ),
        document_store=document_store,
        add_document=build_add_document(document_store),
        update_note=build_update_note(document_store),
        tag_document=build_tag_document(document_store),
        export_bibtex=build_export_bibtex(document_store),
        references_bib_path=DEFAULT_REFERENCES_BIB_PATH,
    )
