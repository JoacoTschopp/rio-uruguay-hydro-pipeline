"""Tests de `GoldParquetDatasetRepository` (Fase 1, docs/rio_search_plan.md §3.2, §5):
delega en `SnapshotSyncPort` (Fase 0) y carga el parquet resultante con Polars."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.infrastructure.datasets.gold_parquet_repository import GoldParquetDatasetRepository


class FakeSnapshotSync:
    def __init__(self, dataset_version: DatasetVersion, path: Path) -> None:
        self._dataset_version = dataset_version
        self._path = path
        self.calls: list[tuple[str, bool]] = []

    def refresh(self, mode: str = "ensure_latest", force: bool = False):
        self.calls.append((mode, force))
        return self._dataset_version, self._path


def test_load_reads_parquet_from_snapshot_sync_path(tmp_path: Path) -> None:
    parquet_path = tmp_path / "training_dataset_v0.parquet"
    pl.DataFrame({"fecha": ["2020-01-01"], "caudal_actual_m3s": [123.4]}).write_parquet(parquet_path)
    dataset_version = DatasetVersion(
        delta_version=1,
        sha256="a" * 64,
        rows=1,
        fecha_min="2020-01-01",
        fecha_max="2020-01-01",
        columns=("fecha", "caudal_actual_m3s"),
    )
    sync = FakeSnapshotSync(dataset_version, parquet_path)
    repository = GoldParquetDatasetRepository(sync)

    result_version, df = repository.load(mode="offline")

    assert result_version is dataset_version
    assert df.height == 1
    assert df["caudal_actual_m3s"].to_list() == [123.4]
    assert sync.calls == [("offline", False)]


def test_load_passes_mode_and_force_through(tmp_path: Path) -> None:
    parquet_path = tmp_path / "training_dataset_v0.parquet"
    pl.DataFrame({"x": [1]}).write_parquet(parquet_path)
    dataset_version = DatasetVersion(
        delta_version=1,
        sha256="a" * 64,
        rows=1,
        fecha_min="2020-01-01",
        fecha_max="2020-01-01",
        columns=("x",),
    )
    sync = FakeSnapshotSync(dataset_version, parquet_path)
    repository = GoldParquetDatasetRepository(sync)

    repository.load(mode="ensure_latest", force=True)

    assert sync.calls == [("ensure_latest", True)]
