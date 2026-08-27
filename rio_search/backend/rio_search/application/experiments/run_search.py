"""`RunSearch` (Fase 2, docs/rio_search_plan.md §3.2, §3.5, §5): caso de uso principal del
contexto Experiments. Llama `RefreshDataset` (Fase 1) una sola vez y reusa su resultado para
todos los trials (Decision #10), abre la jerarquia de runs busqueda -> trial en MLflow
(`TrackingPort`, §3.5) y, para cada trial, resuelve el adaptador de modelo (`ModelRegistryPort`,
§3.3), lo entrena/evalua y loguea metricas/tiempos/procedencia/artefactos.

Alcance de esta fase: solo la familia `naive` (`persistence`, `climatology`, `seasonal_naive`,
§5 "sin entrenamiento"), un unico trial por busqueda (`config.trials()` sin bloque `search:`,
§4.1) y estrategia `multi_output` (el bucle `per_horizon`, "en la aplicacion", es Fase 3).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import polars as pl

from rio_search.application.datasets.build_split import BuildSplit, SplitDataFrames
from rio_search.application.datasets.refresh_dataset import RefreshDataset
from rio_search.application.experiments.evaluate_predictions import EvaluatePredictions
from rio_search.application.ports.device_resolver import DeviceResolver
from rio_search.application.ports.git_provenance import GitProvenancePort
from rio_search.application.ports.model_registry import ModelRegistryPort
from rio_search.application.ports.stopwatch import Stopwatch
from rio_search.application.ports.tracking import TrackingPort
from rio_search.domain.datasets.sequence_spec import SequenceSpec
from rio_search.domain.experiments.experiment_config import ExperimentConfig
from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.experiments.run_status import RunStatus
from rio_search.domain.experiments.search import Search
from rio_search.domain.experiments.trial import Trial
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.datasets.sequence_builder import SequenceBuilder, Sequences
from rio_search.infrastructure.datasets.target_builder import TargetBuilder, Targets
from rio_search.infrastructure.experiments.experiment_config_loader import LoadedExperimentConfig
from rio_search.infrastructure.models.types import Predictions
from rio_search.infrastructure.tracking.artifacts import (
    timings_payload,
    write_code_artifacts,
    write_json_artifact,
)
from rio_search.infrastructure.tracking.params import flatten_params

# .../backend/rio_search/application/experiments/run_search.py -> .../backend/rio_search (raiz)
PACKAGE_DIR = Path(__file__).resolve().parents[2]

# Mismo path que `infrastructure.datasets.gold_snapshot_sync.VOLUME_PARQUET` (Fase 0/1): origen
# del `MetaDataset` (§3.5). No se importa desde ahi para no acoplar `application` a esa
# constante interna de `GoldSnapshotSync`; es la ruta publicada del snapshot de Gold.
VOLUME_PARQUET = "/Volumes/weather/raw/gold_export_volume/training_dataset_v0.parquet"

REFERENCE_MODEL_NAME = "persistence"


@dataclass(frozen=True, slots=True)
class RunSearchDependencies:
    """Agrupa las dependencias de `RunSearch` para que `container.py` las arme una sola vez."""

    refresh_dataset: RefreshDataset
    device_resolver: DeviceResolver
    git_provenance: GitProvenancePort
    model_registry: ModelRegistryPort
    tracking: TrackingPort
    stopwatch: Stopwatch  # compartido con `RefreshDataset` (mide `time/dataset_refresh_s`, §3.12)
    stopwatch_factory: Callable[[], Stopwatch]  # uno nuevo por trial (evita pisar claves entre trials)


class RunSearch:
    def __init__(self, deps: RunSearchDependencies, build_split: BuildSplit | None = None) -> None:
        self._deps = deps
        self._build_split = build_split or BuildSplit()
        self._evaluate = EvaluatePredictions()

    def execute(self, loaded: LoadedExperimentConfig) -> Search:
        config = loaded.config
        deps = self._deps

        trials: list[Trial] = []
        trial_seconds: list[float] = []

        started_at = datetime.now(timezone.utc)
        search_run_name = f"search__{config.name}__{started_at.strftime('%Y%m%d-%H%M')}"

        with deps.tracking.start_run(config.tracking.experiment, search_run_name, nested=False) as search_run:
            # `search_total_s` envuelve todo el trabajo sustancial (resolver device, capturar
            # procedencia, refrescar el dataset, correr los trials) pero se cierra *antes* de
            # loguearlo -- el run padre sigue abierto (seguimos dentro del `with` de arriba) asi
            # que loguear metricas/artefactos despues de cerrar el stopwatch no requiere volver a
            # abrir nada.
            with deps.stopwatch.track("search_total_s"):
                device = deps.device_resolver.resolve(preferred=config.training.device)
                provenance = deps.git_provenance.capture()
                if config.provenance.require_clean_git:
                    provenance.ensure_clean()

                refresh_result = deps.refresh_dataset.execute(mode=config.dataset.refresh)
                dataset_version = refresh_result.dataset_version
                df = refresh_result.dataframe

                if config.dataset.version != "latest":
                    expected = config.dataset.version.removeprefix("delta-")
                    if str(dataset_version.delta_version) != expected:
                        raise ValueError(
                            f"dataset.version={config.dataset.version!r} pero se descargo "
                            f"delta_version={dataset_version.delta_version} (reproduccion exacta fallida)."
                        )

                history_dates, history_values = _full_history(df, config.dataset.target)

                search_tags = _base_tags(config, dataset_version, loaded.config_sha256, device, provenance)
                search_tags["started_at"] = started_at.isoformat()
                deps.tracking.set_tags(search_tags)
                deps.tracking.log_params(flatten_params(loaded.raw_dict))
                deps.tracking.log_meta_dataset(
                    name=f"training_dataset_v0@delta{dataset_version.delta_version}",
                    digest=dataset_version.sha256[:8],
                    source_path=VOLUME_PARQUET,
                    context="search",
                )

                for i, trial_config in enumerate(config.trials()):
                    trial, trial_total_s = self._run_trial(
                        trial_config=trial_config,
                        trial_index=i,
                        loaded=loaded,
                        df=df,
                        dataset_version=dataset_version,
                        device=device,
                        provenance=provenance,
                        history_dates=history_dates,
                        history_values=history_values,
                        base_tags=search_tags,
                    )
                    trials.append(trial)
                    trial_seconds.append(trial_total_s)

            deps.tracking.log_metrics(deps.stopwatch.as_metrics())
            deps.tracking.log_metrics(_search_time_metrics(trial_seconds, deps.stopwatch))
            with tempfile.TemporaryDirectory() as tmp:
                write_code_artifacts(Path(tmp), provenance, PACKAGE_DIR)
                deps.tracking.log_artifact_dir(Path(tmp), artifact_path="code")
            deps.tracking.set_tags({"ended_at": datetime.now(timezone.utc).isoformat()})

        return Search(
            name=config.name,
            experiment_path=config.tracking.experiment,
            status=RunStatus.FINISHED,
            trials=tuple(trials),
            run_id=search_run.run_id,
        )

    def _run_trial(
        self,
        trial_config: ExperimentConfig,
        trial_index: int,
        loaded: LoadedExperimentConfig,
        df: pl.DataFrame,
        dataset_version: Any,
        device: Device,
        provenance: Any,
        history_dates: tuple,
        history_values: np.ndarray,
        base_tags: dict[str, str],
    ) -> tuple[Trial, float]:
        deps = self._deps
        model = trial_config.model
        horizons = trial_config.dataset.horizons
        target = trial_config.dataset.target

        if model.horizon_strategy is not HorizonStrategy.MULTI_OUTPUT:
            raise NotImplementedError(
                f"horizon_strategy={model.horizon_strategy.value!r}: el bucle 'per_horizon' es "
                "Fase 3 (docs/rio_search_plan.md §3.3); esta fase solo corre multi_output."
            )

        adapter_cls = deps.model_registry.get(model.name)
        if model.horizon_strategy not in adapter_cls.supports:
            raise ValueError(f"{model.name!r} no soporta horizon_strategy={model.horizon_strategy.value!r}")
        model_spec = model.with_family(adapter_cls.family)
        model_spec = replace(model_spec, params={**model_spec.params, "horizons": list(horizons)})

        trial_stopwatch = deps.stopwatch_factory()

        with trial_stopwatch.track("trial_total_s"):
            with trial_stopwatch.track("preprocess_s"):
                split_dfs = self._build_split.execute(df, trial_config.split, horizons)
                train_seq, train_targets = _build_sequences_and_targets(
                    split_dfs.train, target, horizons, trial_config.sequence.lookback_days
                )
                val_seq, val_targets = _build_sequences_and_targets(
                    split_dfs.val, target, horizons, trial_config.sequence.lookback_days
                )
                test_seq, test_targets = _build_sequences_and_targets(
                    split_dfs.test, target, horizons, trial_config.sequence.lookback_days
                )

            adapter = adapter_cls()
            adapter.build(model_spec, n_features=1, n_outputs=len(horizons), device=device)
            if hasattr(adapter, "set_history"):
                adapter.set_history(history_dates, history_values)

            reference_adapter = deps.model_registry.get(REFERENCE_MODEL_NAME)()
            reference_spec = ModelSpec(
                name=REFERENCE_MODEL_NAME,
                horizon_strategy=HorizonStrategy.MULTI_OUTPUT,
                params={"horizons": list(horizons)},
            )
            reference_adapter.build(reference_spec, n_features=1, n_outputs=len(horizons), device=device)

            with trial_stopwatch.track("train_total_s"):
                adapter.fit(train_seq, val_seq, trial_config.training)

            with trial_stopwatch.track("eval_val_s"):
                val_pred = adapter.predict(val_seq)
                val_ref = reference_adapter.predict(val_seq)
                val_metrics = self._evaluate.execute(
                    "val", horizons, val_targets.y, val_pred.y_pred, val_ref.y_pred
                )

            with trial_stopwatch.track("predict_test_s"):
                test_pred = adapter.predict(test_seq)

            with trial_stopwatch.track("eval_test_s"):
                test_ref = reference_adapter.predict(test_seq)
                test_metrics = self._evaluate.execute(
                    "test", horizons, test_targets.y, test_pred.y_pred, test_ref.y_pred
                )

            n_test = len(test_seq.anchor_dates)
            predict_test_s = trial_stopwatch.elapsed("predict_test_s") or 0.0
            predict_per_sample_ms = (predict_test_s / n_test * 1000.0) if n_test else 0.0

        started_at = datetime.now(timezone.utc)
        trial_run_name = (
            f"{model.name}__{target.value}__{model.horizon_strategy.value}__"
            f"{trial_config.split.policy}__{started_at.strftime('%Y%m%d-%H%M')}"
        )

        with deps.tracking.start_run(
            trial_config.tracking.experiment, trial_run_name, nested=True
        ) as trial_run:
            deps.tracking.set_tags(base_tags)
            deps.tracking.log_params(flatten_params(loaded.raw_dict))
            deps.tracking.log_metrics(val_metrics.as_mlflow_metrics())
            deps.tracking.log_metrics(test_metrics.as_mlflow_metrics())
            deps.tracking.log_metrics(trial_stopwatch.as_metrics())
            deps.tracking.log_metrics({"time/predict_per_sample_ms": predict_per_sample_ms})

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_json_artifact(tmp_dir, "experiment.yaml.json", loaded.raw_dict)
                (tmp_dir / "experiment.yaml").write_text(loaded.raw_yaml, encoding="utf-8")
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="config")

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_json_artifact(tmp_dir, "split.json", _split_payload(split_dfs))
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="split")

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_json_artifact(
                    tmp_dir,
                    "spec.json",
                    {"feature_columns": [target.actual_column], "experimental_transforms": []},
                )
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="features")

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                _predictions_dataframe(val_pred, val_targets).write_parquet(tmp_dir / "val.parquet")
                _predictions_dataframe(test_pred, test_targets).write_parquet(tmp_dir / "test.parquet")
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="predictions")

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_json_artifact(tmp_dir, "timings.json", timings_payload(trial_stopwatch))
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="timings")

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_code_artifacts(tmp_dir, provenance, PACKAGE_DIR)
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="code")

            with trial_stopwatch.track("model_log_s"), tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                adapter.save(tmp_dir / "model_state.json")
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="model")
            # `model_log_s` se mide despues de haber logueado el resto de `time/*` (§3.12): se
            # sube aparte, no requiere otra ronda de `as_metrics()`.
            deps.tracking.log_metrics({"time/model_log_s": trial_stopwatch.elapsed("model_log_s") or 0.0})

        trial = Trial(
            name=trial_run_name,
            model=model_spec,
            status=RunStatus.FINISHED,
            run_id=trial_run.run_id,
            val_metrics=val_metrics,
            test_metrics=test_metrics,
        )
        trial_total_s = trial_stopwatch.elapsed("trial_total_s") or 0.0
        return trial, trial_total_s


def _base_tags(
    config: ExperimentConfig, dataset_version: Any, config_sha256: str, device: Device, provenance: Any
) -> dict[str, str]:
    return {
        **device.as_tags(),
        **provenance.as_tags(),
        "model": config.model.name,
        "target": config.dataset.target.value,
        "horizon_strategy": config.model.horizon_strategy.value,
        "split_policy": config.split.policy,
        "train_start": _train_window_repr(config.split),
        "dataset_delta_version": str(dataset_version.delta_version),
        "dataset_sha256": dataset_version.sha256,
        "config_sha256": config_sha256,
        "feature_groups": ",".join(config.features.groups),
        "experimental_transforms": ",".join(t.key for t in config.features.experimental_transforms),
    }


def _train_window_repr(split: Any) -> str:
    window = split.train_window
    return window.start.isoformat() if window.start is not None else f"years={window.years}"


def _build_sequences_and_targets(
    split_df: pl.DataFrame, target: TargetVariable, horizons: tuple[int, ...], lookback_days: int
) -> tuple[Sequences, Targets]:
    seq = SequenceBuilder(SequenceSpec(lookback_days=lookback_days)).build(
        split_df, feature_columns=[target.actual_column]
    )
    targets = TargetBuilder(target, horizons).build(split_df, anchor_dates=seq.anchor_dates)
    return seq, targets


def _full_history(df: pl.DataFrame, target: TargetVariable) -> tuple[tuple, np.ndarray]:
    """Serie diaria completa (todo `df`, sin recortar por split) del target -- la unica fuente
    que `seasonal_naive.set_history()` necesita (docstring del adaptador, §3.3)."""
    ordered = df.select(["fecha", target.actual_column]).sort("fecha")
    dates = tuple(ordered.get_column("fecha").to_list())
    values = ordered.get_column(target.actual_column).to_numpy().astype(np.float64)
    return dates, values


def _predictions_dataframe(predictions: Predictions, targets: Targets) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for i, anchor in enumerate(predictions.anchor_dates):
        for j, horizon in enumerate(predictions.horizons):
            observado = float(targets.y[i, j])
            predicho = float(predictions.y_pred[i, j])
            rows.append(
                {
                    "fecha_anchor": anchor,
                    "horizonte": horizon,
                    "fecha_objetivo": anchor + timedelta(days=horizon),
                    "observado": observado if np.isfinite(observado) else None,
                    "predicho": predicho if np.isfinite(predicho) else None,
                }
            )
    if not rows:
        return pl.DataFrame(
            schema={
                "fecha_anchor": pl.Date,
                "horizonte": pl.Int64,
                "fecha_objetivo": pl.Date,
                "observado": pl.Float64,
                "predicho": pl.Float64,
            }
        )
    return pl.DataFrame(rows)


def _split_payload(split_dfs: SplitDataFrames) -> dict[str, Any]:
    split = split_dfs.split
    return {
        "policy": split.policy,
        "anchor": split.anchor.isoformat(),
        "train": _range_payload(split.train, split_dfs.train.height),
        "val": _range_payload(split.val, split_dfs.val.height),
        "test": _range_payload(split.test, split_dfs.test.height),
    }


def _range_payload(date_range: Any, rows: int) -> dict[str, Any]:
    return {"start": date_range.start.isoformat(), "end": date_range.end.isoformat(), "rows": rows}


def _search_time_metrics(trial_seconds: list[float], stopwatch: Stopwatch) -> dict[str, float]:
    """`search_total_s` es el wall-clock real de `RunSearch.execute` (medido por el propio
    `stopwatch.track("search_total_s")` que envuelve device/procedencia/refresh/trials, §3.12);
    `search_overhead_s = search_total_s - suma de trials` (§3.12: "total - suma de trials")."""
    total_s = stopwatch.elapsed("search_total_s") or 0.0
    if not trial_seconds:
        return {"time/search_trials": 0.0, "time/search_total_s": total_s}
    trial_sum = sum(trial_seconds)
    return {
        "time/search_trials": float(len(trial_seconds)),
        "time/search_trial_mean_s": trial_sum / len(trial_seconds),
        "time/search_trial_max_s": max(trial_seconds),
        "time/search_total_s": total_s,
        "time/search_overhead_s": max(0.0, total_s - trial_sum),
    }
