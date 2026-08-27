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
from rio_search.infrastructure.datasets.gold_snapshot_sync import GoldSnapshotSync
from rio_search.infrastructure.provenance.git_provenance import GitProvenance
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = BACKEND_DIR / "data" / "gold_snapshot"


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
