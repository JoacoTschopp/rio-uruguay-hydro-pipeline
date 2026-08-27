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


def build_api_dependencies(
    profile: str = DEFAULT_PROFILE,
    warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    feature_groups_path: Path = DEFAULT_FEATURE_GROUPS_PATH,
    experiments_dir: Path = DEFAULT_EXPERIMENTS_DIR,
    read_cache_path: Path = DEFAULT_READ_CACHE_PATH,
    jobs_dir: Path = DEFAULT_JOBS_DIR,
    job_lock_path: Path = DEFAULT_JOB_LOCK_PATH,
):
    """Composition root de la API (Fase 4, §5): construye el `ApiDependencies` real que
    `interfaces/api/main.py::create_app()` usa cuando no recibe uno inyectado (los tests de la
    API pasan su propio `ApiDependencies` con `TrackingReadPort`/`JobRunner` falsos, §5)."""
    from rio_search.application.experiments.compare_runs import CompareRuns
    from rio_search.application.experiments.get_run_detail import GetRunDetail
    from rio_search.application.experiments.list_runs import ListRuns
    from rio_search.application.experiments.list_searches import ListSearches
    from rio_search.interfaces.api.dependencies import ApiDependencies

    reader = build_tracking_reader(profile=profile, cache_path=read_cache_path)
    list_runs = ListRuns(reader=reader, base_path=rio_search_experiment_base_path(profile))
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
    )
