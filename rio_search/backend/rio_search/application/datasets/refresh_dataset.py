"""`RefreshDataset` (Fase 1, docs/rio_search_plan.md §3.2, §5): primer paso obligatorio de
`RunSearch` (Decision #10, implementado ahora aunque `RunSearch` todavia no exista -- la
Fase 2 lo llama tal cual). Descarga/valida el dataset actual via `DatasetRepository` y valida
el catalogo de features contra sus columnas reales, con sus propios tiempos (Stopwatch,
§3.12) ademas de los que ya registra `GoldSnapshotSync` internamente.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import polars as pl

from rio_search.application.ports.dataset_repository import DatasetRepository
from rio_search.application.ports.snapshot_sync import RefreshMode
from rio_search.application.ports.stopwatch import Stopwatch
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.feature_catalog import FeatureCatalog


class _NullStopwatch:
    """Usado cuando no se pasa un `Stopwatch` real: sostiene el `with` sin medir nada."""

    def track(self, name: str) -> Any:  # noqa: ANN401 - context manager generico
        return nullcontext()


@dataclass(frozen=True, slots=True)
class RefreshDatasetResult:
    dataset_version: DatasetVersion
    dataframe: pl.DataFrame


class RefreshDataset:
    """Caso de uso del contexto Datasets: descarga -> valida catalogo -> pinea. `RunSearch`
    (Fase 2) llama a `execute()` una sola vez por busqueda y reusa el resultado en todos
    los trials (Decision #10: "una busqueda descarga y pinea una sola `DatasetVersion`")."""

    def __init__(
        self,
        repository: DatasetRepository,
        feature_catalog: FeatureCatalog,
        stopwatch: Stopwatch | None = None,
    ) -> None:
        self._repository = repository
        self._feature_catalog = feature_catalog
        self._stopwatch: Stopwatch | _NullStopwatch = stopwatch or _NullStopwatch()

    def execute(self, mode: RefreshMode = "ensure_latest", force: bool = False) -> RefreshDatasetResult:
        dataset_version, df = self._repository.load(mode=mode, force=force)
        with self._stopwatch.track("dataset_validate_s"):
            self._feature_catalog.validate_against(dataset_version.columns)
        return RefreshDatasetResult(dataset_version=dataset_version, dataframe=df)
