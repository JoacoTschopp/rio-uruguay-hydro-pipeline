"""`DatabricksVolumePublisher` (Fase 6, docs/rio_search_plan.md §3.8 paso 5): implementa
`application.ports.volume_publisher.VolumePublisherPort` -- publica el parquet de un `Forecast`
en `/Volumes/weather/raw/gold_export_volume/forecasts/` (tabla Delta = fase posterior, fuera de
esta entrega, tal como dice el plan). Solo se ejercita con `--publish` (§4.2)."""

from __future__ import annotations

from pathlib import Path

from rio_search.infrastructure.databricks.sdk_client import DatabricksVolumeFiles

FORECASTS_VOLUME_DIR = "/Volumes/weather/raw/gold_export_volume/forecasts"


class DatabricksVolumePublisher:
    """Implementa `application.ports.volume_publisher.VolumePublisherPort`."""

    def __init__(self, files: DatabricksVolumeFiles, remote_dir: str = FORECASTS_VOLUME_DIR) -> None:
        self._files = files
        self._remote_dir = remote_dir

    def publish(self, local_path: Path, remote_name: str) -> str:
        remote_path = f"{self._remote_dir}/{remote_name}"
        self._files.upload(remote_path, local_path.read_bytes(), overwrite=True)
        return remote_path
