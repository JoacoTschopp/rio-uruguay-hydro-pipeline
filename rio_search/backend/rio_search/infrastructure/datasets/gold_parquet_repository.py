"""`GoldParquetDatasetRepository` (Fase 1, docs/rio_search_plan.md §3.2, §5): implementa
`application.ports.dataset_repository.DatasetRepository` sobre `SnapshotSyncPort` (Fase 0),
leyendo el parquet en cache con Polars (Decision #9)."""

from __future__ import annotations

import polars as pl

from rio_search.application.ports.snapshot_sync import RefreshMode, SnapshotSyncPort
from rio_search.domain.datasets.dataset_version import DatasetVersion


class GoldParquetDatasetRepository:
    """Implementa `application.ports.dataset_repository.DatasetRepository`."""

    def __init__(self, snapshot_sync: SnapshotSyncPort) -> None:
        self._snapshot_sync = snapshot_sync

    def load(
        self, mode: RefreshMode = "ensure_latest", force: bool = False
    ) -> tuple[DatasetVersion, pl.DataFrame]:
        dataset_version, path = self._snapshot_sync.refresh(mode=mode, force=force)
        df = pl.read_parquet(path)
        return dataset_version, df
