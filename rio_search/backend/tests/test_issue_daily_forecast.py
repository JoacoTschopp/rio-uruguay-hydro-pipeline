"""Tests offline de `application.predictions.issue_daily_forecast.IssueDailyForecast` (Fase 6,
docs/rio_search_plan.md §3.8): protocolo completo con puertos falsos (dataset, tracking de
lectura/escritura, descarga de artefactos, campeon, device, git) -- ningun test de este archivo
toca Databricks/MLflow real. El `ModelRegistry`/`PersistenceAdapter` son los reales
(`infrastructure.models`, mismo criterio que `tests/test_run_search.py`, Fase 2): lo que se
fake-ea es la frontera con el mundo exterior, no la logica de dominio/aplicacion.

Escenario: un campeon `persistence` (baseline naive, Fase 2) sobre un unico feature
(`caudal_actual_m3s`) -- el modelo mas simple posible que igual ejercita el protocolo completo:
reconstruccion del pipeline desde `split/split.json` (Decision 04x), `AsOfPolicy` con datos
reales faltantes en la cola (ver `_dataset()`), ventaneo, prediccion, `Forecast`, tiempos y tags.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml

import rio_search.infrastructure.models  # noqa: F401 - registra PersistenceAdapter (efecto secundario)
from rio_search.application.datasets.refresh_dataset import RefreshDataset
from rio_search.application.ports.tracking import RunHandle
from rio_search.application.predictions.issue_daily_forecast import (
    IssueDailyForecast,
    IssueDailyForecastDependencies,
)
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.experiments.code_provenance import CodeProvenance
from rio_search.domain.models.model_registry import ModelRegistry
from rio_search.domain.predictions.champion import Champion
from rio_search.domain.shared.device import Device
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch

N_DAYS = 220
FECHA_MIN = date(2020, 1, 1)
N_NULL_TAIL = 5  # ultimos 5 dias sin dato crudo (§2.1: huecos reales en la cola de Gold)
MAX_FFILL_DAYS = 3
LOOKBACK_DAYS = 5


def _dataset() -> tuple[pl.DataFrame, list[date], list[float | None]]:
    dates = [FECHA_MIN + timedelta(days=i) for i in range(N_DAYS)]
    values: list[float | None] = [1000.0 + i for i in range(N_DAYS)]
    for i in range(N_DAYS - N_NULL_TAIL, N_DAYS):
        values[i] = None
    df = pl.DataFrame({"fecha": dates, "caudal_actual_m3s": values})
    return df, dates, values


class FakeDatasetRepository:
    def __init__(self, df: pl.DataFrame) -> None:
        self._df = df
        self.calls: list[str] = []

    def load(self, mode: str = "ensure_latest", force: bool = False):
        self.calls.append(mode)
        version = DatasetVersion(
            delta_version=270,
            sha256="b" * 64,
            rows=self._df.height,
            fecha_min=str(self._df["fecha"].min()),
            fecha_max=str(self._df["fecha"].max()),
            columns=tuple(self._df.columns),
        )
        return version, self._df


class FakeDeviceResolver:
    def __init__(self, device: Device) -> None:
        self._device = device

    def resolve(self, preferred: str = "auto") -> Device:
        return self._device


class FakeGitProvenance:
    def capture(self) -> CodeProvenance:
        return CodeProvenance(
            git_sha="deadbeefcafe",
            git_branch="feature/rio-search",
            git_remote="origin",
            git_dirty=False,
            github_url="https://github.com/JoacoTschopp/rio-uruguay-hydro-pipeline/tree/deadbeefcafe/rio_search",
        )


class FakeChampionStore:
    def __init__(self, champion: Champion | None) -> None:
        self._champion = champion

    def get(self, target: TargetVariable) -> Champion | None:
        return self._champion if self._champion and self._champion.target == target else None

    def set(self, champion: Champion) -> None:
        self._champion = champion

    def history(self, target: TargetVariable, max_results: int = 50):
        return [self._champion] if self._champion else []


class _RunRecordLike:
    def __init__(self, run_id: str, tags: dict[str, str], metrics: dict[str, float]) -> None:
        self.run_id = run_id
        self._tags = tags
        self.metrics = metrics

    def rio_search_tag(self, name: str) -> str | None:
        return self._tags.get(name)


class FakeTrackingReader:
    def __init__(self, runs: dict[str, _RunRecordLike]) -> None:
        self._runs = runs

    def get_run(self, run_id: str):
        return self._runs.get(run_id)

    def list_runs(self, experiment_names, max_results: int = 500):
        return list(self._runs.values())

    def list_children(self, parent_run_id: str, experiment_id: str, max_results: int = 200):
        return []

    def get_metric_history(self, run_id: str, metric_key: str):
        return []


class FakeArtifactRepository:
    def __init__(self, mapping: dict[tuple[str, str], Path]) -> None:
        self._mapping = mapping
        self.calls: list[tuple[str, str]] = []

    def download(self, run_id: str, artifact_path: str, dst_dir: Path) -> Path:
        self.calls.append((run_id, artifact_path))
        key = (run_id, artifact_path)
        if key not in self._mapping:
            raise FileNotFoundError(f"sin artefacto falso para {key}")
        return self._mapping[key]


@dataclass
class _RunLog:
    run_id: str
    experiment_path: str
    run_name: str
    tags: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_dirs: list[tuple[str, list[str]]] = field(default_factory=list)
    meta_datasets: list[dict[str, str]] = field(default_factory=list)


class FakeTrackingPort:
    def __init__(self) -> None:
        self.runs: list[_RunLog] = []
        self._stack: list[_RunLog] = []
        self._counter = 0

    @contextmanager
    def start_run(self, experiment_path: str, run_name: str, nested: bool = False):
        self._counter += 1
        record = _RunLog(
            run_id=f"forecast-run-{self._counter}", experiment_path=experiment_path, run_name=run_name
        )
        self.runs.append(record)
        self._stack.append(record)
        try:
            yield RunHandle(run_id=record.run_id, experiment_id="exp-daily-forecast")
        finally:
            self._stack.pop()

    def set_tags(self, tags: dict[str, str]) -> None:
        self._stack[-1].tags.update(tags)

    def log_params(self, params: dict[str, Any]) -> None:
        pass

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        self._stack[-1].metrics.update(metrics)

    def log_artifact_dir(self, local_dir: Path, artifact_path: str) -> None:
        self._stack[-1].artifact_dirs.append((artifact_path, sorted(p.name for p in local_dir.iterdir())))

    def log_meta_dataset(self, name: str, digest: str, source_path: str, context: str) -> None:
        self._stack[-1].meta_datasets.append(
            {"name": name, "digest": digest, "source_path": source_path, "context": context}
        )

    def register_model(self, run_id: str, artifact_path: str, name: str) -> str:
        raise AssertionError("IssueDailyForecast nunca deberia registrar un modelo nuevo")


class FakeForecastRepository:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save(self, forecast) -> None:
        self.saved.append(forecast)

    def latest(self, target: TargetVariable):
        return self.saved[-1] if self.saved else None

    def list_recent(self, target: TargetVariable, max_results: int = 30):
        return list(reversed(self.saved))[:max_results]


class FakeVolumePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[Path, str]] = []

    def publish(self, local_path: Path, remote_name: str) -> str:
        self.published.append((local_path, remote_name))
        return f"/Volumes/weather/raw/gold_export_volume/forecasts/{remote_name}"


def _write_champion_artifacts(
    tmp_path: Path, train_start: date, train_end: date
) -> dict[tuple[str, str], Path]:
    run_id = "champ-1"

    config = {
        "name": "persistence_test",
        "description": "test",
        "dataset": {
            "source": "gold_training_dataset_v0",
            "refresh": "offline",
            "version": "latest",
            "target": "caudal",
            "horizons": [1, 2],
        },
        "provenance": {"require_clean_git": False},
        "split": {
            "policy": "rolling_365",
            "embargo_days": 0,
            "train_window": {"start": train_start.isoformat()},
        },
        "features": {
            "groups": ["caudal_estado"],
            "exclude": [],
            "experimental_transforms": [],
            "imputation": {"method": "ffill_median", "max_ffill_days": MAX_FFILL_DAYS},
            "scaling": "none",
        },
        "sequence": {"lookback_days": LOOKBACK_DAYS},
        "model": {"name": "persistence", "horizon_strategy": "multi_output", "params": {}},
        "training": {"seed": 42, "device": "auto"},
        "tracking": {"experiment": "/Users/test/rio_search/baselines", "register_model": False},
    }
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "experiment.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    split_dir = tmp_path / "split"
    split_dir.mkdir()
    (split_dir / "split.json").write_text(
        json.dumps(
            {
                "policy": "rolling_365",
                "anchor": train_end.isoformat(),
                "train": {"start": train_start.isoformat(), "end": train_end.isoformat(), "rows": 1},
            }
        ),
        encoding="utf-8",
    )

    features_dir = tmp_path / "features"
    features_dir.mkdir()
    spec_payload = {"feature_columns": ["caudal_actual_m3s"], "experimental_transforms": []}
    (features_dir / "spec.json").write_text(json.dumps(spec_payload), encoding="utf-8")

    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model_state.json").write_text(
        json.dumps({"model": "persistence", "horizons": [1, 2]}), encoding="utf-8"
    )

    return {
        (run_id, "config"): config_dir,
        (run_id, "split"): split_dir,
        (run_id, "features"): features_dir,
        (run_id, "model"): model_dir,
    }


def _build(
    tmp_path: Path, publish_forecast_repository: FakeForecastRepository | None = None
) -> tuple[IssueDailyForecast, dict[str, Any]]:
    df, dates, values = _dataset()
    train_start = dates[0]
    train_end = dates[180]  # bien antes de la cola con nulos
    artifact_mapping = _write_champion_artifacts(tmp_path, train_start, train_end)

    catalog = FeatureCatalog.from_dict(
        {"groups": {"caudal_estado": {"default_on": True, "columns": ["caudal_actual_m3s"]}}}
    )
    stopwatch = PerfCounterStopwatch(cuda_sync=False)
    refresh_dataset = RefreshDataset(
        repository=FakeDatasetRepository(df), feature_catalog=catalog, stopwatch=stopwatch
    )
    champion = Champion(
        target=TargetVariable.CAUDAL,
        run_id="champ-1",
        model_name="persistence",
        metric_name="val/kge/mean",
        metric_value=0.0,
        promoted_at="2026-08-27T18:00:00+00:00",
        note="campeon provisorio",
    )
    tracking_reader = FakeTrackingReader(
        {"champ-1": _RunRecordLike("champ-1", {"model": "persistence", "target": "caudal"}, {})}
    )
    tracking = FakeTrackingPort()
    forecast_repository = publish_forecast_repository or FakeForecastRepository()
    volume_publisher = FakeVolumePublisher()

    deps = IssueDailyForecastDependencies(
        refresh_dataset=refresh_dataset,
        device_resolver=FakeDeviceResolver(Device(type="cpu", name="test-cpu")),
        git_provenance=FakeGitProvenance(),
        champion_store=FakeChampionStore(champion),
        tracking_reader=tracking_reader,
        artifact_repository=FakeArtifactRepository(artifact_mapping),
        tracking=tracking,
        model_registry=ModelRegistry(),
        feature_catalog=catalog,
        forecast_repository=forecast_repository,
        stopwatch=stopwatch,
        experiment_base_path="/Users/test/rio_search",
        artifacts_cache_dir=tmp_path / "cache",
        volume_publisher=volume_publisher,
    )
    context = {
        "dates": dates,
        "values": values,
        "tracking": tracking,
        "forecast_repository": forecast_repository,
        "volume_publisher": volume_publisher,
        "stopwatch": stopwatch,
    }
    return IssueDailyForecast(deps), context


def test_issue_daily_forecast_end_to_end_with_persistence_champion(tmp_path: Path) -> None:
    use_case, ctx = _build(tmp_path)

    forecast = use_case.execute(target=TargetVariable.CAUDAL)

    dates = ctx["dates"]
    # ffill(limit=3) sobre una cola de 5 nulos consecutivos llena los primeros 3, deja los
    # ultimos 2 sin completar -- as_of es el 3er dia desde el final (ver docstring del modulo).
    expected_as_of = dates[-3]
    last_known_value = 1000.0 + (N_DAYS - N_NULL_TAIL - 1)  # ultimo valor crudo no nulo

    assert forecast.as_of == expected_as_of
    assert forecast.data_lag_days >= 2  # al menos los 2 dias que ffill no pudo completar
    assert forecast.champion_run_id == "champ-1"
    assert forecast.champion_model_name == "persistence"
    assert forecast.device_type == "cpu"
    assert forecast.dataset_delta_version == 270
    assert {p.horizon for p in forecast.points} == {1, 2}
    for point in forecast.points:
        # persistence: predice el ultimo valor observado (ya ffill-eado) para todo horizonte.
        assert point.value == pytest.approx(last_known_value)
        assert point.target_date == expected_as_of + timedelta(days=point.horizon)

    assert ctx["forecast_repository"].saved == [forecast]

    tracking = ctx["tracking"]
    assert len(tracking.runs) == 1
    run = tracking.runs[0]
    assert run.experiment_path == "/Users/test/rio_search/daily_forecast"
    assert run.tags["champion_run_id"] == "champ-1"
    assert run.tags["as_of"] == expected_as_of.isoformat()
    assert run.tags["device"] == "cpu"
    for key in ("time/total_s", "time/model_load_s", "time/preprocess_s", "time/predict_s"):
        assert key in run.metrics
    assert any(path == "forecast" for path, _ in run.artifact_dirs)

    # nunca publica sin --publish
    assert ctx["volume_publisher"].published == []
    assert forecast.published_path is None


def test_issue_daily_forecast_publishes_when_requested(tmp_path: Path) -> None:
    use_case, ctx = _build(tmp_path)

    forecast = use_case.execute(target=TargetVariable.CAUDAL, publish=True)

    assert len(ctx["volume_publisher"].published) == 1
    local_path, remote_name = ctx["volume_publisher"].published[0]
    assert not local_path.exists()  # tempdir ya se limpio, pero se subio antes de borrarse
    assert remote_name.startswith("caudal_")
    assert forecast.published_path == f"/Volumes/weather/raw/gold_export_volume/forecasts/{remote_name}"
    assert ctx["forecast_repository"].saved[-1].published_path == forecast.published_path


def test_issue_daily_forecast_respects_as_of_override(tmp_path: Path) -> None:
    use_case, ctx = _build(tmp_path)
    dates = ctx["dates"]
    override = dates[100]

    forecast = use_case.execute(target=TargetVariable.CAUDAL, as_of_override=override)

    assert forecast.as_of == override
    expected_value = 1000.0 + 100
    assert all(p.value == pytest.approx(expected_value) for p in forecast.points)


def test_issue_daily_forecast_raises_without_a_promoted_champion(tmp_path: Path) -> None:
    use_case, ctx = _build(tmp_path)
    use_case._deps = _replace_champion_store(use_case._deps, FakeChampionStore(None))
    with pytest.raises(RuntimeError, match="No hay campeon promovido"):
        use_case.execute(target=TargetVariable.CAUDAL)


def test_issue_daily_forecast_device_resolver_is_invoked_per_run(tmp_path: Path) -> None:
    """Decision #6 (§3.4): el device se resuelve en cada re-ejecucion de prediccion, no una
    sola vez -- corridas sucesivas en CPU vs. CUDA deben poder dar dispositivos distintos."""
    use_case, ctx = _build(tmp_path)
    first = use_case.execute(target=TargetVariable.CAUDAL)
    assert first.device_type == "cpu"

    gpu_device = Device(type="cuda", name="fake-gpu")
    use_case._deps = _replace_device_resolver(use_case._deps, FakeDeviceResolver(gpu_device))
    second = use_case.execute(target=TargetVariable.CAUDAL)
    assert second.device_type == "cuda"


def _replace_champion_store(deps, store):
    from dataclasses import replace

    return replace(deps, champion_store=store)


def _replace_device_resolver(deps, resolver):
    from dataclasses import replace

    return replace(deps, device_resolver=resolver)
