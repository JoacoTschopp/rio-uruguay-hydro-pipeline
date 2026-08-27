"""Puerto de sincronizacion del snapshot de Gold (Decision #10, docs/rio_search_plan.md §3.6)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from rio_search.domain.datasets.dataset_version import DatasetVersion

RefreshMode = Literal["ensure_latest", "volume_as_is", "offline"]


class SnapshotSyncPort(Protocol):
    def refresh(
        self, mode: RefreshMode = "ensure_latest", force: bool = False
    ) -> tuple[DatasetVersion, Path]:
        """Protocolo de frescura completo (§3.6): version Delta de Gold -> manifest -> disparo
        opcional de `Export_Gold_Snapshot` -> descarga y verificacion `sha256` del parquet.
        Devuelve la `DatasetVersion` pineada y la ruta local al parquet."""
        ...
