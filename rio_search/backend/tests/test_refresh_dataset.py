"""Tests de `RefreshDataset` (Fase 1, docs/rio_search_plan.md §3.2, §5): primer paso
obligatorio de `RunSearch` (Decision #10) -- delega en `DatasetRepository`, valida el catalogo
de features contra las columnas reales y mide su propio tiempo con el `Stopwatch`."""

from __future__ import annotations

import polars as pl
import pytest

from rio_search.application.datasets.refresh_dataset import RefreshDataset
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch


def _dataset_version(columns: tuple[str, ...]) -> DatasetVersion:
    return DatasetVersion(
        delta_version=268,
        sha256="a" * 64,
        rows=100,
        fecha_min="2020-01-01",
        fecha_max="2020-04-10",
        columns=columns,
    )


class FakeRepository:
    def __init__(self, dataset_version: DatasetVersion, df: pl.DataFrame) -> None:
        self._dataset_version = dataset_version
        self._df = df
        self.calls: list[tuple[str, bool]] = []

    def load(self, mode: str = "ensure_latest", force: bool = False):
        self.calls.append((mode, force))
        return self._dataset_version, self._df


def _catalog(columns: tuple[str, ...]) -> FeatureCatalog:
    return FeatureCatalog.from_dict({"groups": {"g": {"default_on": True, "columns": list(columns)}}})


def test_execute_returns_dataset_version_and_dataframe() -> None:
    columns = ("fecha", "caudal_actual_m3s")
    dataset_version = _dataset_version(columns)
    df = pl.DataFrame({"fecha": ["2020-01-01"], "caudal_actual_m3s": [100.0]})
    repository = FakeRepository(dataset_version, df)
    use_case = RefreshDataset(repository=repository, feature_catalog=_catalog(columns))

    result = use_case.execute(mode="offline")

    assert result.dataset_version is dataset_version
    assert result.dataframe is df
    assert repository.calls == [("offline", False)]


def test_execute_validates_catalog_and_fails_clearly_when_schema_shrinks() -> None:
    dataset_version = _dataset_version(("fecha",))  # a la app "se le fue" una columna del catalogo
    df = pl.DataFrame({"fecha": ["2020-01-01"]})
    repository = FakeRepository(dataset_version, df)
    catalog = _catalog(("fecha", "caudal_actual_m3s"))  # el catalogo todavia pide la columna que falta
    use_case = RefreshDataset(repository=repository, feature_catalog=catalog)

    with pytest.raises(ValueError, match="caudal_actual_m3s"):
        use_case.execute(mode="offline")


def test_execute_passes_mode_and_force_through() -> None:
    columns = ("fecha",)
    repository = FakeRepository(_dataset_version(columns), pl.DataFrame({"fecha": ["2020-01-01"]}))
    use_case = RefreshDataset(repository=repository, feature_catalog=_catalog(columns))

    use_case.execute(mode="ensure_latest", force=True)

    assert repository.calls == [("ensure_latest", True)]


def test_execute_records_dataset_validate_time_metric() -> None:
    columns = ("fecha",)
    repository = FakeRepository(_dataset_version(columns), pl.DataFrame({"fecha": ["2020-01-01"]}))
    stopwatch = PerfCounterStopwatch(cuda_sync=False)
    use_case = RefreshDataset(repository=repository, feature_catalog=_catalog(columns), stopwatch=stopwatch)

    use_case.execute(mode="offline")

    assert "time/dataset_validate_s" in stopwatch.as_metrics()


def test_execute_works_without_explicit_stopwatch() -> None:
    columns = ("fecha",)
    repository = FakeRepository(_dataset_version(columns), pl.DataFrame({"fecha": ["2020-01-01"]}))
    use_case = RefreshDataset(repository=repository, feature_catalog=_catalog(columns))  # sin stopwatch
    result = use_case.execute(mode="offline")
    assert result.dataset_version.columns == columns
