"""Sincronizacion del snapshot de Gold (Decision #10, docs/rio_search_plan.md §3.6).

Porta la logica de `notebooks_local/gold_export/export_gold_dataset.py` (`sync`,
`needs_download`, verificacion `sha256`) a la app: sin pandas (Polars en el resto de la capa
de datos, Decision #9) y usando el SDK de Databricks (`infrastructure.databricks.sdk_client`)
en vez de `subprocess` sobre la CLI. Protocolo de frescura completo:

1. `DESCRIBE HISTORY <tabla> LIMIT 1` (`GoldCatalogPort`) -> version Delta actual de Gold.
2. Baja `manifest.json` del Volume (siempre, es liviano).
3. Si el manifest esta atras de Gold -> dispara un run ad hoc de `Export_Gold_Snapshot`
   (`jobs submit`, mismo patron que un submit ad hoc de notebook) y vuelve a bajar el manifest.
4. Si el `sha256` del parquet en cache difiere de `manifest.file_sha256` (o `force`) -> baja
   el parquet y verifica el hash.
5. Construye la `DatasetVersion` y la devuelve pineada junto con la ruta local al parquet.

Modos: `ensure_latest` (los 5 pasos), `volume_as_is` (salta el paso 3), `offline` (solo cache
local; falla si no hay). El catalogo de features (`configs/feature_groups.yaml`) se valida
contra `DatasetVersion.columns` en la Fase 1 (`RefreshDataset`), no aca.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Protocol

from rio_search.application.ports.gold_catalog import GoldCatalogPort
from rio_search.application.ports.snapshot_sync import RefreshMode
from rio_search.application.ports.stopwatch import Stopwatch
from rio_search.domain.datasets.dataset_version import DatasetVersion

GOLD_TABLE = "weather.gold.training_dataset_v0"
VOLUME_DIR = "/Volumes/weather/raw/gold_export_volume"
VOLUME_PARQUET = f"{VOLUME_DIR}/training_dataset_v0.parquet"
VOLUME_MANIFEST = f"{VOLUME_DIR}/manifest.json"
EXPORT_NOTEBOOK_PATH = (
    "/Workspace/Users/joaquintschopp@gmail.com/rio-uruguay-hydro-pipeline/"
    "notebooks/05_Gold/Export_Gold_Snapshot"
)


class VolumeFiles(Protocol):
    def download(self, path: str) -> bytes: ...


class JobSubmitter(Protocol):
    def submit_notebook(self, notebook_path: str, run_name: str) -> None: ...


class _NullStopwatch:
    """Usado cuando no se pasa un `Stopwatch` real: no mide nada, pero sostiene el `with`."""

    def track(self, name: str):  # noqa: ANN201 - context manager generico
        return nullcontext()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def needs_download(
    local_manifest: dict[str, Any] | None,
    remote_manifest: dict[str, Any],
    force: bool,
    cache_exists: bool,
) -> bool:
    """Misma regla que `export_gold_dataset.needs_download`: version Delta distinta, cache
    ausente, o `force` explicito (Decision #10)."""
    if force or not cache_exists or local_manifest is None:
        return True
    return local_manifest.get("delta_version") != remote_manifest.get("delta_version")


class GoldSnapshotSync:
    """Implementa `application.ports.snapshot_sync.SnapshotSyncPort`."""

    def __init__(
        self,
        gold_catalog: GoldCatalogPort,
        files: VolumeFiles,
        job_submitter: JobSubmitter,
        cache_dir: Path,
        stopwatch: Stopwatch | None = None,
        log: Any = print,
        gold_table: str = GOLD_TABLE,
        volume_parquet: str = VOLUME_PARQUET,
        volume_manifest: str = VOLUME_MANIFEST,
        export_notebook_path: str = EXPORT_NOTEBOOK_PATH,
    ) -> None:
        self._gold_catalog = gold_catalog
        self._files = files
        self._job_submitter = job_submitter
        self._cache_dir = cache_dir
        self._stopwatch: Stopwatch | _NullStopwatch = stopwatch or _NullStopwatch()
        self._log = log
        self._gold_table = gold_table
        self._volume_parquet = volume_parquet
        self._volume_manifest = volume_manifest
        self._export_notebook_path = export_notebook_path

    @property
    def cache_parquet(self) -> Path:
        return self._cache_dir / "training_dataset_v0.parquet"

    @property
    def cache_manifest(self) -> Path:
        return self._cache_dir / "manifest.json"

    def refresh(
        self, mode: RefreshMode = "ensure_latest", force: bool = False
    ) -> tuple[DatasetVersion, Path]:
        if mode == "offline":
            return self._refresh_offline()

        with self._stopwatch.track("dataset_refresh_s"):
            gold_version: int | None = None
            if mode == "ensure_latest":
                with self._stopwatch.track("dataset_gold_version_s"):
                    gold_version = self._gold_catalog.current_delta_version(self._gold_table)

            with self._stopwatch.track("dataset_manifest_s"):
                remote_manifest = self._download_manifest()

            # dataset_export_job_s queda en ~0 si el manifest no esta atras de Gold (no dispara nada).
            with self._stopwatch.track("dataset_export_job_s"):
                stale = (
                    mode == "ensure_latest"
                    and gold_version is not None
                    and int(remote_manifest.get("delta_version", -1)) < gold_version
                )
                if stale:
                    self._log(
                        f"Manifest en delta {remote_manifest.get('delta_version')}, Gold en "
                        f"{gold_version}: disparando Export_Gold_Snapshot..."
                    )
                    self._job_submitter.submit_notebook(
                        self._export_notebook_path,
                        run_name="rio_search_export_gold_snapshot_adhoc",
                    )
                    remote_manifest = self._download_manifest()

            dataset_version = self._download_and_verify(remote_manifest, force)

        return dataset_version, self.cache_parquet

    def _refresh_offline(self) -> tuple[DatasetVersion, Path]:
        if not self.cache_parquet.exists() or not self.cache_manifest.exists():
            raise RuntimeError(
                f"mode=offline pero no hay cache local en {self._cache_dir}; corre "
                "ensure_latest una vez para poblarlo."
            )
        manifest = json.loads(self.cache_manifest.read_text(encoding="utf-8"))
        return DatasetVersion.from_manifest(manifest), self.cache_parquet

    def _download_manifest(self) -> dict[str, Any]:
        raw = self._files.download(self._volume_manifest)
        return json.loads(raw.decode("utf-8"))

    def _download_and_verify(self, remote_manifest: dict[str, Any], force: bool) -> DatasetVersion:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        local_manifest = (
            json.loads(self.cache_manifest.read_text(encoding="utf-8"))
            if self.cache_manifest.exists()
            else None
        )
        must_download = needs_download(local_manifest, remote_manifest, force, self.cache_parquet.exists())

        if must_download:
            with self._stopwatch.track("dataset_download_s"):
                self._log(f"Bajando parquet (delta {remote_manifest.get('delta_version')})...")
                parquet_bytes = self._files.download(self._volume_parquet)
                self.cache_parquet.write_bytes(parquet_bytes)

            with self._stopwatch.track("dataset_verify_s"):
                actual_hash = sha256_of(self.cache_parquet)
                expected_hash = remote_manifest.get("file_sha256")
                if expected_hash and actual_hash != expected_hash:
                    raise RuntimeError(
                        f"Hash del parquet descargado ({actual_hash}) no coincide con el "
                        f"manifest ({expected_hash}); descarga corrupta, reintentar."
                    )

            self.cache_manifest.write_text(
                json.dumps(remote_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            self._log(
                f"Version Delta sin cambios ({remote_manifest.get('delta_version')}); usando cache local."
            )

        return DatasetVersion.from_manifest(remote_manifest)
