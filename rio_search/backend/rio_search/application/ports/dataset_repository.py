"""Puerto del repositorio de datasets (Fase 1, docs/rio_search_plan.md §3.6): envuelve el
protocolo de frescura (`SnapshotSyncPort`, Decision #10) y expone el parquet como
`pl.DataFrame` -- Polars, nunca pandas (Decision #9). Es el unico puerto de `application` que
tipa con Polars: `application` puede depender de Polars (igual que de `pathlib`), la regla de
"sin dependencias del proyecto" es solo para `domain` (§3.2).
"""

from __future__ import annotations

from typing import Protocol

import polars as pl

from rio_search.application.ports.snapshot_sync import RefreshMode
from rio_search.domain.datasets.dataset_version import DatasetVersion


class DatasetRepository(Protocol):
    def load(
        self, mode: RefreshMode = "ensure_latest", force: bool = False
    ) -> tuple[DatasetVersion, pl.DataFrame]:
        """Descarga/valida el snapshot (protocolo de frescura, §3.6) y devuelve la
        `DatasetVersion` pineada junto con el `pl.DataFrame` completo cargado del parquet."""
        ...
