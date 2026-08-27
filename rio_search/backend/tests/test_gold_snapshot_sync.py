"""Tests offline de `GoldSnapshotSync` (Decision #10, docs/rio_search_plan.md §3.6), con un
SDK de Databricks falso (`GoldCatalogPort`, `VolumeFiles`, `JobSubmitter`): nada de esto toca
Databricks real."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from rio_search.infrastructure.datasets.gold_snapshot_sync import GoldSnapshotSync, needs_download
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch

MANIFEST_71_COLS = {
    "delta_version": 263,
    "rows": 9732,
    "fecha_min": "2000-01-01",
    "fecha_max": "2026-08-23",
    "punto_prediccion": "ana_74100000",
    "columns": [f"col_{i}" for i in range(71)],
    "file_name": "training_dataset_v0.parquet",
    "exported_at": "2026-08-26T07:40:27+00:00",
}


def _manifest_with_hash(base: dict[str, Any], parquet: bytes) -> dict[str, Any]:
    manifest = dict(base)
    manifest["file_sha256"] = hashlib.sha256(parquet).hexdigest()
    return manifest


class FakeGoldCatalog:
    def __init__(self, version: int) -> None:
        self.version = version
        self.calls = 0

    def current_delta_version(self, table: str) -> int:
        self.calls += 1
        return self.version


class FakeVolumeFiles:
    def __init__(self, manifest: dict[str, Any], parquet: bytes) -> None:
        self.manifest = manifest
        self.parquet = parquet
        self.download_calls: list[str] = []

    def download(self, path: str) -> bytes:
        self.download_calls.append(path)
        if path.endswith("manifest.json"):
            return json.dumps(self.manifest).encode("utf-8")
        if path.endswith(".parquet"):
            return self.parquet
        raise FileNotFoundError(path)


class FakeJobSubmitter:
    def __init__(self, files: FakeVolumeFiles, new_manifest: dict[str, Any]) -> None:
        self._files = files
        self._new_manifest = new_manifest
        self.calls: list[tuple[str, str]] = []

    def submit_notebook(self, notebook_path: str, run_name: str) -> None:
        self.calls.append((notebook_path, run_name))
        self._files.manifest = self._new_manifest  # simula que el run ad hoc regenero el manifest


def _sync(
    tmp_path: Path,
    gold_catalog: FakeGoldCatalog,
    files: FakeVolumeFiles,
    job_submitter: FakeJobSubmitter,
) -> GoldSnapshotSync:
    return GoldSnapshotSync(
        gold_catalog=gold_catalog,
        files=files,
        job_submitter=job_submitter,
        cache_dir=tmp_path / "cache",
        stopwatch=PerfCounterStopwatch(cuda_sync=False),
    )


def test_needs_download_pure_rules() -> None:
    remote = {"delta_version": 5}
    assert needs_download(None, remote, force=False, cache_exists=False) is True
    assert needs_download({"delta_version": 5}, remote, force=False, cache_exists=True) is False
    assert needs_download({"delta_version": 4}, remote, force=False, cache_exists=True) is True
    assert needs_download({"delta_version": 5}, remote, force=True, cache_exists=True) is True


def test_ensure_latest_up_to_date_downloads_once_and_no_job(tmp_path: Path) -> None:
    parquet = b"fake-parquet-bytes"
    manifest = _manifest_with_hash(MANIFEST_71_COLS, parquet)
    catalog = FakeGoldCatalog(version=263)
    files = FakeVolumeFiles(manifest, parquet)
    job = FakeJobSubmitter(files, new_manifest=manifest)
    sync = _sync(tmp_path, catalog, files, job)

    dataset_version, path = sync.refresh(mode="ensure_latest")

    assert catalog.calls == 1
    assert job.calls == []
    assert dataset_version.delta_version == 263
    assert len(dataset_version.columns) == 71
    assert path.exists()
    assert path.read_bytes() == parquet


def test_ensure_latest_stale_manifest_triggers_export_job(tmp_path: Path) -> None:
    parquet_old = b"old-parquet"
    parquet_new = b"new-parquet-83-cols"
    stale_manifest = _manifest_with_hash(MANIFEST_71_COLS, parquet_old)
    fresh_manifest = _manifest_with_hash(
        {**MANIFEST_71_COLS, "delta_version": 264, "columns": [f"col_{i}" for i in range(83)]},
        parquet_new,
    )
    catalog = FakeGoldCatalog(version=264)
    files = FakeVolumeFiles(stale_manifest, parquet_new)
    job = FakeJobSubmitter(files, new_manifest=fresh_manifest)
    sync = _sync(tmp_path, catalog, files, job)

    dataset_version, path = sync.refresh(mode="ensure_latest")

    assert len(job.calls) == 1
    assert job.calls[0][0].endswith("Export_Gold_Snapshot")
    assert dataset_version.delta_version == 264
    assert len(dataset_version.columns) == 83  # 71 -> 83, criterio de cierre de la Fase 0
    assert path.read_bytes() == parquet_new


def test_volume_as_is_never_queries_gold_or_submits_job(tmp_path: Path) -> None:
    parquet = b"fake-parquet-bytes"
    manifest = _manifest_with_hash(MANIFEST_71_COLS, parquet)
    catalog = FakeGoldCatalog(version=999)  # muy adelante; no deberia importar en volume_as_is
    files = FakeVolumeFiles(manifest, parquet)
    job = FakeJobSubmitter(files, new_manifest=manifest)
    sync = _sync(tmp_path, catalog, files, job)

    dataset_version, _ = sync.refresh(mode="volume_as_is")

    assert catalog.calls == 0
    assert job.calls == []
    assert dataset_version.delta_version == 263


def test_offline_without_cache_raises(tmp_path: Path) -> None:
    catalog = FakeGoldCatalog(version=263)
    files = FakeVolumeFiles({}, b"")
    job = FakeJobSubmitter(files, new_manifest={})
    sync = _sync(tmp_path, catalog, files, job)

    with pytest.raises(RuntimeError):
        sync.refresh(mode="offline")
    assert files.download_calls == []


def test_offline_with_cache_uses_it_without_network(tmp_path: Path) -> None:
    parquet = b"fake-parquet-bytes"
    manifest = _manifest_with_hash(MANIFEST_71_COLS, parquet)
    catalog = FakeGoldCatalog(version=263)
    files = FakeVolumeFiles(manifest, parquet)
    job = FakeJobSubmitter(files, new_manifest=manifest)
    sync = _sync(tmp_path, catalog, files, job)
    sync.refresh(mode="ensure_latest")  # puebla el cache
    files.download_calls.clear()

    dataset_version, path = sync.refresh(mode="offline")

    assert files.download_calls == []  # offline no toca la red
    assert dataset_version.delta_version == 263
    assert path.exists()


def test_sha256_mismatch_raises(tmp_path: Path) -> None:
    parquet = b"fake-parquet-bytes"
    manifest = dict(MANIFEST_71_COLS)
    manifest["file_sha256"] = "0" * 64  # hash incorrecto a proposito
    catalog = FakeGoldCatalog(version=263)
    files = FakeVolumeFiles(manifest, parquet)
    job = FakeJobSubmitter(files, new_manifest=manifest)
    sync = _sync(tmp_path, catalog, files, job)

    with pytest.raises(RuntimeError, match="Hash"):
        sync.refresh(mode="ensure_latest")


def test_second_refresh_with_same_version_uses_cache(tmp_path: Path) -> None:
    parquet = b"fake-parquet-bytes"
    manifest = _manifest_with_hash(MANIFEST_71_COLS, parquet)
    catalog = FakeGoldCatalog(version=263)
    files = FakeVolumeFiles(manifest, parquet)
    job = FakeJobSubmitter(files, new_manifest=manifest)
    sync = _sync(tmp_path, catalog, files, job)
    sync.refresh(mode="ensure_latest")
    files.download_calls.clear()

    sync.refresh(mode="ensure_latest")

    # Solo se vuelve a bajar el manifest (liviano), no el parquet (version sin cambios).
    assert files.download_calls == [sync._volume_manifest]


def test_stopwatch_records_time_metrics(tmp_path: Path) -> None:
    parquet = b"fake-parquet-bytes"
    manifest = _manifest_with_hash(MANIFEST_71_COLS, parquet)
    catalog = FakeGoldCatalog(version=263)
    files = FakeVolumeFiles(manifest, parquet)
    job = FakeJobSubmitter(files, new_manifest=manifest)
    stopwatch = PerfCounterStopwatch(cuda_sync=False)
    sync = GoldSnapshotSync(
        gold_catalog=catalog,
        files=files,
        job_submitter=job,
        cache_dir=tmp_path / "cache",
        stopwatch=stopwatch,
    )

    sync.refresh(mode="ensure_latest")

    metrics = stopwatch.as_metrics()
    for key in (
        "time/dataset_refresh_s",
        "time/dataset_gold_version_s",
        "time/dataset_manifest_s",
        "time/dataset_export_job_s",
        "time/dataset_download_s",
        "time/dataset_verify_s",
    ):
        assert key in metrics, f"falta {key} en los tiempos (§3.12)"
