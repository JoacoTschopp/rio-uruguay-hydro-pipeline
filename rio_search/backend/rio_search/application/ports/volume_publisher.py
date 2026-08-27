"""Puerto de publicacion opcional al Volume (Fase 6, docs/rio_search_plan.md §3.8, paso 5:
"publica el parquet al Volume `weather.raw.gold_export_volume/forecasts/` para que Databricks lo
pueda consumir despues (tabla Delta = fase posterior, no en esta entrega)"). Solo se invoca con
`--publish` (§4.2, `rio-search predict run --publish`)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class VolumePublisherPort(Protocol):
    def publish(self, local_path: Path, remote_name: str) -> str:
        """Sube `local_path` a `forecasts/<remote_name>` en el Volume y devuelve la ruta
        remota completa (`/Volumes/...`)."""
        ...
