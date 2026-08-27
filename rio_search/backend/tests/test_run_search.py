"""Tests offline de `application.experiments.run_search.RunSearch` (Fase 2,
docs/rio_search_plan.md §3.2, §3.5, §5): dataset sintetico + `TrackingPort`/`DatasetRepository`/
`GitProvenancePort`/`DeviceResolver` falsos (mismo patron que `tests/test_refresh_dataset.py`,
Fase 1) para no tocar Databricks/MLflow. El `ModelRegistry` y los adaptadores naive son los
reales (`infrastructure.models`): lo que se fake-ea es la frontera con el mundo exterior
(Databricks/MLflow/reloj del sistema para device), no la logica de dominio/aplicacion.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml

from rio_search.application.datasets.refresh_dataset import RefreshDataset
from rio_search.application.experiments.run_search import RunSearch, RunSearchDependencies
from rio_search.application.ports.tracking import RunHandle
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.experiments.code_provenance import CodeProvenance
from rio_search.domain.experiments.run_status import RunStatus
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.experiments.experiment_config_loader import load_experiment_config
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch

CONFIGS_DIR = Path(__file__).resolve().parents[1] / "configs" / "experiments"
N_DAYS = 1600
FECHA_MIN = date(2014, 1, 1)


def _synthetic_gold_dataframe(horizons: tuple[int, ...]) -> pl.DataFrame:
    """Serie diaria continua (como `training_dataset_v0`, §2.1: "sin huecos de calendario"):
    caudal con estacionalidad + tendencia leve, y los targets `caudal_t_mas_{h}d` como LEAD
    real (valor observado h dias despues), igual que en Gold (no se vuelven a calcular)."""
    dates = [FECHA_MIN + timedelta(days=i) for i in range(N_DAYS)]
    values = [1000.0 + 400.0 * math.sin(2 * math.pi * i / 365.25) + 0.05 * i for i in range(N_DAYS)]
    df = pl.DataFrame({"fecha": dates, "caudal_actual_m3s": values})
    for h in horizons:
        df = df.with_columns(pl.col("caudal_actual_m3s").shift(-h).alias(f"caudal_t_mas_{h}d"))
    return df


class FakeDatasetRepository:
    """Mismo rol que `FakeRepository` en `tests/test_refresh_dataset.py` (Fase 1)."""

    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df
        self.calls: list[tuple[str, bool]] = []

    def load(self, mode: str = "ensure_latest", force: bool = False):
        self.calls.append((mode, force))
        version = DatasetVersion(
            delta_version=268,
            sha256="b" * 64,
            rows=self._df.height,
            fecha_min=str(self._df["fecha"].min()),
            fecha_max=str(self._df["fecha"].max()),
            columns=tuple(self._df.columns),
        )
        return version, self._df


class FakeDeviceResolver:
    def resolve(self, preferred: str = "auto") -> Device:
        return Device(type="cpu", name="test-cpu")


class FakeGitProvenance:
    def capture(self) -> CodeProvenance:
        return CodeProvenance(
            git_sha="deadbeefcafe",
            git_branch="feature/rio-search",
            git_remote="origin",
            git_dirty=False,
            github_url="https://github.com/JoacoTschopp/rio-uruguay-hydro-pipeline/tree/deadbeefcafe/rio_search",
            uncommitted_patch="",
        )


@dataclass
class _RunRecord:
    run_id: str
    experiment_path: str
    run_name: str
    nested: bool
    tags: dict[str, str]
    params: dict[str, Any]
    metrics: dict[str, float]
    artifact_dirs: list[tuple[str, list[str]]]
    meta_datasets: list[dict[str, str]]


class FakeTrackingPort:
    def __init__(self) -> None:
        self.runs: list[_RunRecord] = []
        self._stack: list[_RunRecord] = []
        self._counter = 0

    @contextmanager
    def start_run(self, experiment_path: str, run_name: str, nested: bool = False):
        self._counter += 1
        record = _RunRecord(
            run_id=f"run-{self._counter}",
            experiment_path=experiment_path,
            run_name=run_name,
            nested=nested,
            tags={},
            params={},
            metrics={},
            artifact_dirs=[],
            meta_datasets=[],
        )
        self.runs.append(record)
        self._stack.append(record)
        try:
            yield RunHandle(run_id=record.run_id, experiment_id="exp-1")
        finally:
            self._stack.pop()

    def set_tags(self, tags: dict[str, str]) -> None:
        self._stack[-1].tags.update(tags)

    def log_params(self, params: dict[str, Any]) -> None:
        self._stack[-1].params.update(params)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self._stack[-1].metrics.update(metrics)

    def log_artifact_dir(self, local_dir: Path, artifact_path: str) -> None:
        self._stack[-1].artifact_dirs.append((artifact_path, sorted(p.name for p in local_dir.iterdir())))

    def log_meta_dataset(self, name: str, digest: str, source_path: str, context: str) -> None:
        self._stack[-1].meta_datasets.append(
            {"name": name, "digest": digest, "source_path": source_path, "context": context}
        )


def _loaded_config(model_name: str, tmp_path: Path):
    """Reusa los YAML reales de `configs/experiments/` (mismos que corren contra Databricks),
    solo cambiando `dataset.refresh` a `offline` (no importa: el repositorio esta fakeado)."""
    real_path = CONFIGS_DIR / f"{model_name}_baseline_v1.yaml"
    data = yaml.safe_load(real_path.read_text(encoding="utf-8"))
    data["dataset"]["refresh"] = "offline"
    test_path = tmp_path / real_path.name
    test_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_experiment_config(test_path)


def _deps(df: pl.DataFrame) -> tuple[RunSearchDependencies, FakeTrackingPort]:
    stopwatch = PerfCounterStopwatch(cuda_sync=False)
    repository = FakeDatasetRepository(df)
    refresh_dataset = RefreshDataset(
        repository=repository, feature_catalog=FeatureCatalog(groups=()), stopwatch=stopwatch
    )
    tracking = FakeTrackingPort()
    deps = RunSearchDependencies(
        refresh_dataset=refresh_dataset,
        device_resolver=FakeDeviceResolver(),
        git_provenance=FakeGitProvenance(),
        model_registry=_real_model_registry(),
        tracking=tracking,
        stopwatch=stopwatch,
        stopwatch_factory=lambda: PerfCounterStopwatch(cuda_sync=False),
    )
    return deps, tracking


def _real_model_registry():
    import rio_search.infrastructure.models  # noqa: F401 - registra persistence/climatology/seasonal_naive
    from rio_search.domain.models.model_registry import ModelRegistry

    return ModelRegistry()


HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)


def test_persistence_search_has_zero_skill_vs_itself_for_every_horizon(tmp_path: Path) -> None:
    df = _synthetic_gold_dataframe(HORIZONS)
    deps, tracking = _deps(df)
    loaded = _loaded_config("persistence", tmp_path)

    search = RunSearch(deps).execute(loaded)

    assert search.status is RunStatus.FINISHED
    assert len(search.trials) == 1
    trial = search.trials[0]
    assert trial.status is RunStatus.FINISHED
    assert trial.test_metrics is not None and trial.val_metrics is not None

    for h in HORIZONS:
        skill_test = trial.test_metrics.horizon(h).get("skill_vs_persistence")
        skill_val = trial.val_metrics.horizon(h).get("skill_vs_persistence")
        assert skill_test == 0.0, f"skill de persistencia (test) deberia ser 0.0 exacto en h={h}"
        assert skill_val == 0.0, f"skill de persistencia (val) deberia ser 0.0 exacto en h={h}"


def test_search_run_records_tags_params_time_metrics_and_meta_dataset(tmp_path: Path) -> None:
    df = _synthetic_gold_dataframe(HORIZONS)
    deps, tracking = _deps(df)
    loaded = _loaded_config("persistence", tmp_path)

    RunSearch(deps).execute(loaded)

    parent = tracking.runs[0]
    assert parent.nested is False
    assert parent.tags["git_sha"] == "deadbeefcafe"
    assert parent.tags["device"] == "cpu"
    assert parent.tags["dataset_delta_version"] == "268"
    assert parent.tags["model"] == "persistence"
    assert "time/search_total_s" in parent.metrics
    assert "time/dataset_validate_s" in parent.metrics
    assert len(parent.meta_datasets) == 1
    assert "delta268" in parent.meta_datasets[0]["name"]
    assert any(artifact_path == "code" for artifact_path, _ in parent.artifact_dirs)

    trial_record = tracking.runs[1]
    assert trial_record.nested is True
    assert trial_record.metrics["test/rmse/h01"] >= 0.0
    assert "time/eval_val_s" in trial_record.metrics
    assert "time/eval_test_s" in trial_record.metrics
    assert "time/predict_test_s" in trial_record.metrics
    assert "time/predict_per_sample_ms" in trial_record.metrics
    assert "time/model_log_s" in trial_record.metrics

    artifact_paths = {path for path, _ in trial_record.artifact_dirs}
    assert {"config", "split", "features", "predictions", "timings", "code", "model"} <= artifact_paths

    predictions_files = next(files for path, files in trial_record.artifact_dirs if path == "predictions")
    assert "val.parquet" in predictions_files
    assert "test.parquet" in predictions_files


@pytest.mark.parametrize("model_name", ["persistence", "climatology", "seasonal_naive"])
def test_each_naive_baseline_search_runs_end_to_end(model_name: str, tmp_path: Path) -> None:
    df = _synthetic_gold_dataframe(HORIZONS)
    deps, tracking = _deps(df)
    loaded = _loaded_config(model_name, tmp_path)

    search = RunSearch(deps).execute(loaded)

    trial = search.trials[0]
    assert trial.test_metrics is not None
    mean_rmse = trial.test_metrics.mean("rmse")
    assert not math.isnan(mean_rmse)
    assert mean_rmse >= 0.0
