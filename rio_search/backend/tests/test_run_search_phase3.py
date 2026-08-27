"""Tests offline de la Fase 3 sobre `RunSearch` (docs/rio_search_plan.md §3.2, §3.3, §4.1,
§5): `bilstm` (family `torch`, via `BuildFeatureMatrix`, Decision 041 -- incluye el glob
`"caudal_*"` sin resolver del YAML de ejemplo), `multi_output` vs `per_horizon` (runs nietos de
MLflow), y la busqueda de hiperparametros (`search:` grid/random/tpe). Todo con `TrackingPort`/
`DatasetRepository`/`GitProvenancePort`/`DeviceResolver` falsos, dataset sintetico, sin tocar
Databricks/MLflow real (mismo patron que `tests/test_run_search.py`, Fase 2)."""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from rio_search.application.datasets.build_feature_matrix import BuildFeatureMatrix
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

HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)
N_DAYS = 1400
FECHA_MIN = date(2015, 1, 1)


def _synthetic_gold_dataframe() -> pl.DataFrame:
    dates = [FECHA_MIN + timedelta(days=i) for i in range(N_DAYS)]
    base = [1000.0 + 400.0 * math.sin(2 * math.pi * i / 365.25) + 0.05 * i for i in range(N_DAYS)]
    df = pl.DataFrame(
        {
            "fecha": dates,
            "caudal_actual_m3s": base,
            "caudal_lag_1d": [base[max(0, i - 1)] for i in range(N_DAYS)],
        }
    )
    for h in HORIZONS:
        df = df.with_columns(pl.col("caudal_actual_m3s").shift(-h).alias(f"caudal_t_mas_{h}d"))
    return df


def _catalog() -> FeatureCatalog:
    return FeatureCatalog.from_dict(
        {
            "groups": {
                "caudal_estado": {
                    "default_on": True,
                    "columns": ["caudal_actual_m3s", "caudal_lag_1d"],
                }
            }
        }
    )


class FakeDatasetRepository:
    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df

    def load(self, mode: str = "ensure_latest", force: bool = False):
        version = DatasetVersion(
            delta_version=300,
            sha256="c" * 64,
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
    parent_run_id: str | None
    tags: dict[str, str]
    params: dict[str, Any]
    metrics: dict[str, float]
    metric_steps: list[tuple[str, float, int | None]]
    artifact_dirs: list[tuple[str, list[str]]]
    meta_datasets: list[dict[str, str]]
    registered: list[dict[str, str]]


class FakeTrackingPort:
    """Extiende el fake de `test_run_search.py` (Fase 2) con `register_model` (Fase 3, UC)."""

    def __init__(self) -> None:
        self.runs: list[_RunRecord] = []
        self._stack: list[_RunRecord] = []
        self._counter = 0
        self._registered_versions: dict[str, int] = {}

    @contextmanager
    def start_run(self, experiment_path: str, run_name: str, nested: bool = False):
        self._counter += 1
        record = _RunRecord(
            run_id=f"run-{self._counter}",
            experiment_path=experiment_path,
            run_name=run_name,
            nested=nested,
            parent_run_id=self._stack[-1].run_id if nested and self._stack else None,
            tags={},
            params={},
            metrics={},
            metric_steps=[],
            artifact_dirs=[],
            meta_datasets=[],
            registered=[],
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
        for k, v in metrics.items():
            self._stack[-1].metric_steps.append((k, v, step))

    def log_artifact_dir(self, local_dir: Path, artifact_path: str) -> None:
        self._stack[-1].artifact_dirs.append((artifact_path, sorted(p.name for p in local_dir.iterdir())))

    def log_meta_dataset(self, name: str, digest: str, source_path: str, context: str) -> None:
        self._stack[-1].meta_datasets.append(
            {"name": name, "digest": digest, "source_path": source_path, "context": context}
        )

    def register_model(self, run_id: str, artifact_path: str, name: str) -> str:
        self._registered_versions[name] = self._registered_versions.get(name, 0) + 1
        version = str(self._registered_versions[name])
        self._stack[-1].registered.append({"run_id": run_id, "artifact_path": artifact_path, "name": name})
        return version


def _write_config(tmp_path: Path, overrides: dict[str, Any]) -> Path:
    base: dict[str, Any] = {
        "name": "bilstm_test",
        "description": "test",
        "dataset": {
            "source": "gold_training_dataset_v0",
            "refresh": "offline",
            "version": "latest",
            "target": "caudal",
            "horizons": list(HORIZONS),
        },
        "provenance": {"require_clean_git": False},
        "split": {
            "policy": "rolling_365",
            "embargo_days": 14,
            "train_window": {"start": "2015-01-01"},
        },
        "features": {
            "groups": ["caudal_estado"],
            "experimental_transforms": [
                {"name": "log1p", "columns": ["caudal_*"], "version": 1},
            ],
            "imputation": {"method": "ffill_median", "max_ffill_days": 3},
            "scaling": "standard",
        },
        "sequence": {"lookback_days": 10},
        "model": {
            "name": "bilstm",
            "horizon_strategy": "multi_output",
            "params": {"hidden_size": 8, "num_layers": 1, "dropout": 0.0},
        },
        "training": {
            "max_epochs": 3,
            "batch_size": 32,
            "optimizer": {"name": "adam", "lr": 0.01, "weight_decay": 0.0},
            "loss": "mse",
            "early_stopping": {"monitor": "val/loss", "patience": 3},
            "grad_clip": 1.0,
            "seed": 42,
            "device": "cpu",
        },
        "tracking": {
            "experiment": "/Users/test/rio_search/bilstm",
            "tags": {},
            "register_model": False,
        },
    }
    _deep_update(base, overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    return path


def _deep_update(base: dict[str, Any], overrides: dict[str, Any]) -> None:
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def _deps() -> tuple[RunSearchDependencies, FakeTrackingPort]:
    df = _synthetic_gold_dataframe()
    stopwatch = PerfCounterStopwatch(cuda_sync=False)
    repository = FakeDatasetRepository(df)
    catalog = _catalog()
    refresh_dataset = RefreshDataset(repository=repository, feature_catalog=catalog, stopwatch=stopwatch)
    tracking = FakeTrackingPort()
    deps = RunSearchDependencies(
        refresh_dataset=refresh_dataset,
        device_resolver=FakeDeviceResolver(),
        git_provenance=FakeGitProvenance(),
        model_registry=_real_model_registry(),
        tracking=tracking,
        stopwatch=stopwatch,
        stopwatch_factory=lambda: PerfCounterStopwatch(cuda_sync=False),
        build_feature_matrix=BuildFeatureMatrix(catalog),
    )
    return deps, tracking


def _real_model_registry():
    import rio_search.infrastructure.models  # noqa: F401 - registra bilstm/persistence/etc
    from rio_search.domain.models.model_registry import ModelRegistry

    return ModelRegistry()


def test_bilstm_multi_output_runs_end_to_end_with_glob_transform_and_epoch_curves(tmp_path: Path) -> None:
    """Ejercita el fix del glob (Decision 041, `"caudal_*"` sin resolver del YAML de ejemplo)
    dentro del flujo real de `RunSearch` con un modelo `torch` (no naive): si el bug no
    estuviera resuelto, `BuildFeatureMatrix` fallaria con `ColumnNotFoundError` de Polars."""
    config_path = _write_config(tmp_path, {})
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    search = RunSearch(deps).execute(loaded)

    assert search.status is RunStatus.FINISHED
    assert len(search.trials) == 1
    trial = search.trials[0]
    assert trial.status is RunStatus.FINISHED
    assert trial.val_metrics is not None and trial.test_metrics is not None
    assert len(trial.test_metrics.horizons) == len(HORIZONS)

    trial_record = tracking.runs[1]
    assert trial_record.nested is True
    assert "time/train_total_s" in trial_record.metrics
    assert "time/trial_total_s" in trial_record.metrics
    assert "time/train_to_best_epoch_s" in trial_record.metrics
    assert "time/train_samples_per_s" in trial_record.metrics

    # Curvas de loss por epoch (step-wise, §3.12): al menos un punto de train/loss con step>=1.
    loss_points = [(v, step) for k, v, step in trial_record.metric_steps if k == "train/loss"]
    assert len(loss_points) >= 1
    assert all(step is not None and step >= 1 for _, step in loss_points)

    artifact_paths = {path for path, _ in trial_record.artifact_dirs}
    assert {"config", "split", "features", "predictions", "timings", "code", "model"} <= artifact_paths
    model_files = next(files for path, files in trial_record.artifact_dirs if path == "model")
    assert "model_state_dict.pth" in model_files
    assert "architecture.json" in model_files

    # El feature_columns logueado en spec.json debe incluir la columna expandida del glob.
    spec_dir_files = next(files for path, files in trial_record.artifact_dirs if path == "features")
    assert "spec.json" in spec_dir_files


def test_bilstm_multi_output_registers_model_in_uc_when_configured(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"tracking": {"register_model": True}})
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    RunSearch(deps).execute(loaded)

    trial_record = tracking.runs[1]
    assert trial_record.registered == [
        {"run_id": trial_record.run_id, "artifact_path": "model", "name": "weather.ml.rio_search_bilstm"}
    ]
    assert trial_record.tags["registered_model_name"] == "weather.ml.rio_search_bilstm"
    assert trial_record.tags["registered_model_version"] == "1"


def test_bilstm_per_horizon_registers_one_model_per_horizon_in_uc_when_configured(tmp_path: Path) -> None:
    """`RunSearch._run_single_horizon` reusa el mismo `register_model` que `multi_output`
    (Decision 042/043): con `per_horizon` + `register_model: true`, cada uno de los 8 runs
    nietos registra su propio `weather.ml.rio_search_bilstm_h{NN}` -- sin cobertura offline
    hasta este test, el camino real (Fase 3, `bilstm_baseline_v1_per_horizon.yaml`) lo deja en
    `register_model: false` a propósito para no crear 8 versiones en la corrida de demostración."""
    config_path = _write_config(
        tmp_path, {"model": {"horizon_strategy": "per_horizon"}, "tracking": {"register_model": True}}
    )
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    RunSearch(deps).execute(loaded)

    grandchildren = [r for r in tracking.runs if r.run_name.startswith("h")]
    assert len(grandchildren) == len(HORIZONS)
    for h, r in zip(HORIZONS, grandchildren, strict=True):
        expected_name = f"weather.ml.rio_search_bilstm_h{h:02d}"
        assert r.registered == [{"run_id": r.run_id, "artifact_path": "model", "name": expected_name}]
        assert r.tags["registered_model_name"] == expected_name
        assert r.tags["registered_model_version"] == "1"


def test_bilstm_per_horizon_opens_one_grandchild_run_per_horizon(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"model": {"horizon_strategy": "per_horizon"}})
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    search = RunSearch(deps).execute(loaded)

    trial = search.trials[0]
    assert trial.test_metrics is not None
    assert len(trial.test_metrics.horizons) == len(HORIZONS)
    assert {hm.horizon for hm in trial.test_metrics.horizons} == set(HORIZONS)

    # search_run(0) + trial_run(1) + 8 runs nietos = 10.
    assert len(tracking.runs) == 1 + 1 + len(HORIZONS)
    grandchildren = [r for r in tracking.runs if r.run_name.startswith("h")]
    assert len(grandchildren) == len(HORIZONS)
    trial_run_id = tracking.runs[1].run_id
    assert all(r.parent_run_id == trial_run_id for r in grandchildren)
    for r in grandchildren:
        assert "test/rmse/h" in ",".join(r.metrics)  # alguna metrica de un unico horizonte
        assert "time/train_total_s" in r.metrics

    trial_record = tracking.runs[1]
    assert "time/train_total_s" in trial_record.metrics  # suma de los 8 nietos
    model_files_paths = [path for path, _ in trial_record.artifact_dirs if path == "model"]
    assert model_files_paths  # manifest de per_horizon_runs.json a nivel trial


def test_per_horizon_and_multi_output_are_comparable_same_metric_keys(tmp_path: Path) -> None:
    (tmp_path / "multi").mkdir()
    (tmp_path / "per_h").mkdir()
    config_multi = load_experiment_config(_write_config(tmp_path / "multi", {}))
    config_per_h = load_experiment_config(
        _write_config(tmp_path / "per_h", {"model": {"horizon_strategy": "per_horizon"}})
    )

    deps_a, _ = _deps()
    deps_b, _ = _deps()
    search_a = RunSearch(deps_a).execute(config_multi)
    search_b = RunSearch(deps_b).execute(config_per_h)

    keys_a = set(search_a.trials[0].test_metrics.as_mlflow_metrics())
    keys_b = set(search_b.trials[0].test_metrics.as_mlflow_metrics())
    assert keys_a == keys_b


def test_search_grid_runs_one_trial_per_combination(tmp_path: Path) -> None:
    overrides = {
        "search": {
            "strategy": "grid",
            "n_trials": 10,
            "objective": "val/kge/mean",
            "space": {"sequence.lookback_days": [5, 10]},
        }
    }
    config_path = _write_config(tmp_path, overrides)
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    search = RunSearch(deps).execute(loaded)

    assert len(search.trials) == 2  # 2 valores discretos, grid cartesiano -> 2 combinaciones
    # Verificamos via los params logueados del trial (mas confiable que ModelSpec, que no
    # incluye 'sequence').
    trial_records = [r for r in tracking.runs if r.nested]
    lookbacks = sorted(int(r.params["sequence.lookback_days"]) for r in trial_records)
    assert lookbacks == [5, 10]
    assert "time/search_total_s" in tracking.runs[0].metrics
    assert tracking.runs[0].tags["search_strategy"] == "grid"


def test_search_random_respects_n_trials_and_seed_is_reproducible_choice_set(tmp_path: Path) -> None:
    overrides = {
        "search": {
            "strategy": "random",
            "n_trials": 3,
            "objective": "val/kge/mean",
            "space": {"sequence.lookback_days": [5, 10, 15]},
        }
    }
    config_path = _write_config(tmp_path, overrides)
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    search = RunSearch(deps).execute(loaded)

    assert len(search.trials) == 3
    trial_records = [r for r in tracking.runs if r.nested]
    lookbacks = [int(r.params["sequence.lookback_days"]) for r in trial_records]
    assert all(lb in (5, 10, 15) for lb in lookbacks)


def test_search_tpe_uses_optuna_and_reports_objective_back(tmp_path: Path) -> None:
    overrides = {
        "search": {
            "strategy": "tpe",
            "n_trials": 3,
            "objective": "val/kge/mean",
            "space": {"sequence.lookback_days": [5, 10, 15]},
        }
    }
    config_path = _write_config(tmp_path, overrides)
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    search = RunSearch(deps).execute(loaded)

    assert len(search.trials) == 3
    for trial in search.trials:
        assert trial.val_metrics is not None
        assert not math.isnan(trial.val_metrics.mean("kge"))


def test_search_trial_configs_log_their_own_overridden_params(tmp_path: Path) -> None:
    """Cada trial de una busqueda debe loguear su propia config con overrides aplicados, no la
    del YAML base tal cual (de lo contrario `config/experiment.yaml` mentiria sobre que
    hiperparametros produjeron esas metricas)."""
    overrides = {
        "search": {
            "strategy": "grid",
            "n_trials": 10,
            "objective": "val/kge/mean",
            "space": {"model.params.hidden_size": [4, 16]},
        }
    }
    config_path = _write_config(tmp_path, overrides)
    loaded = load_experiment_config(config_path)
    deps, tracking = _deps()

    RunSearch(deps).execute(loaded)

    trial_records = [r for r in tracking.runs if r.nested and not r.run_name.startswith("h")]
    hidden_sizes = sorted(int(r.params["model.params.hidden_size"]) for r in trial_records)
    assert hidden_sizes == [4, 16]
