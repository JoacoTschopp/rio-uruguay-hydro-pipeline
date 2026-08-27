"""`ApiDependencies` (Fase 4, docs/rio_search_plan.md §5): agrupa lo que `interfaces/api/main.py`
necesita para resolver cada endpoint, construido una sola vez por `interfaces/container.py`
(composition root, §3.2) -- mismo patron que `RunSearchDependencies` en `application.experiments.
run_search`. Los tests de la API (`tests/test_api_*.py`) construyen esta misma clase con
`TrackingReadPort`/`JobRunner` falsos en vez de tocar Databricks (§5: "tests con `TestClient` y
un `TrackingPort` falso")."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rio_search.application.experiments.compare_runs import CompareRuns
from rio_search.application.experiments.get_run_detail import GetRunDetail
from rio_search.application.experiments.list_runs import ListRuns
from rio_search.application.experiments.list_searches import ListSearches
from rio_search.application.ports.job_runner import JobRunner
from rio_search.application.ports.snapshot_sync import SnapshotSyncPort
from rio_search.application.ports.tracking_read import TrackingReadPort
from rio_search.domain.datasets.feature_catalog import FeatureCatalog


@dataclass(frozen=True, slots=True)
class ApiDependencies:
    reader: TrackingReadPort
    list_runs: ListRuns
    list_searches: ListSearches
    get_run_detail: GetRunDetail
    compare_runs: CompareRuns
    job_runner: JobRunner
    experiments_dir: Path
    snapshot_sync: SnapshotSyncPort
    feature_catalog: FeatureCatalog
