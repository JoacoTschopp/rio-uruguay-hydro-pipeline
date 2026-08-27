"""`RunSearch` (Fase 2/3, docs/rio_search_plan.md §3.2, §3.5, §5): caso de uso principal del
contexto Experiments. Llama `RefreshDataset` (Fase 1) una sola vez y reusa su resultado para
todos los trials (Decision #10), abre la jerarquia de runs busqueda -> trial (-> horizonte,
Fase 3, `per_horizon`) en MLflow (`TrackingPort`, §3.5) y, para cada trial, resuelve el
adaptador de modelo (`ModelRegistryPort`, §3.3), lo entrena/evalua y loguea
metricas/tiempos/procedencia/artefactos.

Fase 2 (naive, `multi_output`, sin `search:`) y Fase 3 (`bilstm`, `per_horizon`, `search:`
grid/random/tpe) comparten esta misma clase:

* **Family** (`ModelSpec.family`, resuelta desde el adaptador registrado): los modelos `naive`
  no usan `BuildFeatureMatrix` (Decision 040 -- solo el propio target rezagado, un unico
  feature); cualquier otra familia (`torch`, Fase 3; `sklearn`, Fase 9) sí, con las columnas
  reales de `features.groups`/`experimental_transforms` (§3.6). La referencia de persistencia
  (`skill_vs_persistence`, §3.7) **siempre** se calcula aparte, sobre una `Sequences` de un
  solo feature (`target.actual_column`, sin escalar) construida con el mismo `lookback_days`
  del trial -- nunca reusando el `Sequences` multi-feature/escalado del modelo evaluado (daria
  una "persistencia" sin sentido: otra columna, en otra escala).
* **`horizon_strategy`** (Decision #2, §3.3): `multi_output` entrena un unico modelo con
  `n_outputs=len(horizons)`; `per_horizon` entrena `len(horizons)` modelos con `n_outputs=1`
  cada uno, cada uno en su propio run MLflow anidado (`nested=True`) *dentro* del run del
  trial -- "run nieto" (§3.5). Ambas estrategias quedan comparables: el trial agrega las
  metricas de los 8 horizontes (`per_horizon`: concatenando los `HorizonMetrics` de cada nieto;
  `multi_output`: ya vienen juntas) y sus tiempos (`per_horizon`: suma de los 8; `multi_output`:
  el unico valor) bajo las mismas claves `time/*` (§3.12).
* **`search:`** (§4.1, Fase 3): sin el bloque, `config.trials()` (Fase 2, un unico trial, sin
  cambios). Con el bloque, `infrastructure.experiments.search_strategies.build_sampler` genera
  overrides (`grid`/`random`/`tpe`) que se aplican sobre `loaded.raw_dict` (`apply_overrides`) y
  se reparsean a una `ExperimentConfig` de trial completa -- cada trial es un run hijo de
  MLflow con su config real (no la del YAML base), y `tpe` recibe el objetivo (`search.objective`,
  p. ej. `val/kge/mean`) de vuelta via `sampler.report(...)` para el siguiente `ask()`.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import polars as pl
import yaml

from rio_search.application.datasets.build_feature_matrix import BuildFeatureMatrix
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
from rio_search.domain.experiments.metric_set import HorizonMetrics, MetricSet
from rio_search.domain.experiments.run_status import RunStatus
from rio_search.domain.experiments.search import Search
from rio_search.domain.experiments.search_spec import SearchSpec
from rio_search.domain.experiments.trial import Trial
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.datasets.sequence_builder import SequenceBuilder, Sequences
from rio_search.infrastructure.datasets.target_builder import TargetBuilder, Targets
from rio_search.infrastructure.experiments.experiment_config_loader import LoadedExperimentConfig
from rio_search.infrastructure.experiments.search_strategies import apply_overrides, build_sampler
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
UC_MODEL_PREFIX = "weather.ml.rio_search_"


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
    # Fase 3: modelos que no son `naive` (Decision 040) necesitan `BuildFeatureMatrix` (§3.6)
    # con columnas reales. `None` sigue siendo valido para busquedas 100% naive (Fase 2, ningun
    # test/config existente lo necesita) -- `_prepare_trial_data` falla explicito si hace falta
    # y no esta.
    build_feature_matrix: BuildFeatureMatrix | None = None


@dataclass(frozen=True, slots=True)
class _TrialData:
    """Secuencias/targets ya preparados para un trial -- del modelo evaluado y, por separado,
    de la referencia de persistencia (ver docstring del modulo: nunca se reusa la misma
    `Sequences` multi-feature/escalada para la referencia)."""

    train_seq: Sequences
    train_targets: Targets
    val_seq: Sequences
    val_targets: Targets
    test_seq: Sequences
    test_targets: Targets
    reference_val_seq: Sequences
    reference_val_targets: Targets
    reference_test_seq: Sequences
    reference_test_targets: Targets
    n_features: int
    feature_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _HorizonOutcome:
    """Resultado de entrenar+evaluar un unico horizonte dentro de `per_horizon` (un "run
    nieto", §3.5)."""

    horizon: int
    val_metrics: HorizonMetrics
    test_metrics: HorizonMetrics
    val_pred: Predictions
    test_pred: Predictions
    fit_epochs: int
    fit_best_epoch: int
    fit_train_losses: tuple[float, ...]
    fit_val_losses: tuple[float, ...]
    fit_epoch_seconds: tuple[float, ...]
    fit_train_to_best_epoch_s: float
    fit_train_samples_per_s: float
    time_metrics: dict[str, float]
    run_id: str | None


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
                if config.search is not None:
                    search_tags["search_strategy"] = config.search.strategy
                    search_tags["search_objective"] = config.search.objective
                deps.tracking.set_tags(search_tags)
                deps.tracking.log_params(flatten_params(loaded.raw_dict))
                deps.tracking.log_meta_dataset(
                    name=f"training_dataset_v0@delta{dataset_version.delta_version}",
                    digest=dataset_version.sha256[:8],
                    source_path=VOLUME_PARQUET,
                    context="search",
                )

                if config.search is None:
                    # Fase 2, sin cambios: `config.trials()` da un unico trial, la config/YAML
                    # tal como esta en el archivo.
                    for trial_index, trial_config in enumerate(config.trials()):
                        trial, trial_total_s = self._run_trial(
                            trial_config=trial_config,
                            trial_index=trial_index,
                            trial_raw_dict=loaded.raw_dict,
                            trial_raw_yaml=loaded.raw_yaml,
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
                else:
                    # Fase 3 (§4.1, §5): un `TrialSampler` (grid/random/tpe) genera overrides
                    # (`suggest()`), se aplican sobre `loaded.raw_dict` y se reparsean a una
                    # `ExperimentConfig` de trial completa; `tpe` recibe de vuelta el objetivo
                    # real (`sampler.report(...)`) para que el *siguiente* `suggest()` ya use
                    # lo aprendido -- por eso este bucle no puede ser un simple `for` sobre una
                    # lista pre-generada como el caso sin `search:`.
                    sampler = build_sampler(config.search, seed=config.training.seed)
                    trial_index = 0
                    while True:
                        overrides = sampler.suggest()
                        if overrides is None:
                            break
                        trial_raw_dict = apply_overrides(loaded.raw_dict, overrides)
                        trial_config = ExperimentConfig.from_dict(trial_raw_dict)
                        trial_raw_yaml = yaml.safe_dump(trial_raw_dict, sort_keys=False, allow_unicode=True)
                        trial, trial_total_s = self._run_trial(
                            trial_config=trial_config,
                            trial_index=trial_index,
                            trial_raw_dict=trial_raw_dict,
                            trial_raw_yaml=trial_raw_yaml,
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
                        sampler.report(_extract_objective(trial, config.search))
                        trial_index += 1

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
        trial_raw_dict: dict[str, Any],
        trial_raw_yaml: str,
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

        adapter_cls = deps.model_registry.get(model.name)
        if model.horizon_strategy not in adapter_cls.supports:
            raise ValueError(f"{model.name!r} no soporta horizon_strategy={model.horizon_strategy.value!r}")
        model_spec = model.with_family(adapter_cls.family)
        model_spec = replace(model_spec, params={**model_spec.params, "horizons": list(horizons)})

        trial_stopwatch = deps.stopwatch_factory()
        started_at = datetime.now(timezone.utc)
        trial_run_name = (
            f"{model.name}__{target.value}__{model.horizon_strategy.value}__"
            f"{trial_config.split.policy}__{started_at.strftime('%Y%m%d-%H%M')}"
        )

        # El run del trial envuelve a `trial_total_s` (no al reves, a diferencia de la Fase 2):
        # `per_horizon` necesita abrir runs nietos (`nested=True`) *dentro* del run del trial,
        # que a su vez solo existe una vez que este `with` arranco -- MLflow anida sobre el run
        # activo. Por la misma razon, `trial_stopwatch.as_metrics()` (que incluye
        # `time/trial_total_s`) se loguea *despues* de que el `with trial_stopwatch.track(...)`
        # de mas abajo cierra, pero *antes* de que el run del trial cierre.
        with deps.tracking.start_run(
            trial_config.tracking.experiment, trial_run_name, nested=True
        ) as trial_run:
            deps.tracking.set_tags(base_tags)
            deps.tracking.log_params(flatten_params(trial_raw_dict))
            deps.tracking.set_tags({"search_trial_index": str(trial_index)})

            with trial_stopwatch.track("trial_total_s"):
                with trial_stopwatch.track("preprocess_s"):
                    split_dfs = self._build_split.execute(df, trial_config.split, horizons)
                    data = self._prepare_trial_data(trial_config, model_spec, split_dfs, target, horizons)

                reference_adapter = deps.model_registry.get(REFERENCE_MODEL_NAME)()
                reference_spec = ModelSpec(
                    name=REFERENCE_MODEL_NAME,
                    horizon_strategy=HorizonStrategy.MULTI_OUTPUT,
                    params={"horizons": list(horizons)},
                )
                reference_adapter.build(reference_spec, n_features=1, n_outputs=len(horizons), device=device)
                reference_val_pred = reference_adapter.predict(data.reference_val_seq)
                reference_test_pred = reference_adapter.predict(data.reference_test_seq)

                with tempfile.TemporaryDirectory() as tmp:
                    tmp_dir = Path(tmp)
                    write_json_artifact(tmp_dir, "experiment.yaml.json", trial_raw_dict)
                    (tmp_dir / "experiment.yaml").write_text(trial_raw_yaml, encoding="utf-8")
                    deps.tracking.log_artifact_dir(tmp_dir, artifact_path="config")

                with tempfile.TemporaryDirectory() as tmp:
                    tmp_dir = Path(tmp)
                    write_json_artifact(tmp_dir, "split.json", _split_payload(split_dfs))
                    deps.tracking.log_artifact_dir(tmp_dir, artifact_path="split")

                with tempfile.TemporaryDirectory() as tmp:
                    tmp_dir = Path(tmp)
                    transform_keys = [t.key for t in trial_config.features.experimental_transforms]
                    write_json_artifact(
                        tmp_dir,
                        "spec.json",
                        {
                            "feature_columns": list(data.feature_columns),
                            "experimental_transforms": transform_keys,
                        },
                    )
                    deps.tracking.log_artifact_dir(tmp_dir, artifact_path="features")

                if model.horizon_strategy is HorizonStrategy.MULTI_OUTPUT:
                    val_metrics, test_metrics = self._run_multi_output(
                        deps=deps,
                        adapter_cls=adapter_cls,
                        model_spec=model_spec,
                        data=data,
                        trial_config=trial_config,
                        device=device,
                        history_dates=history_dates,
                        history_values=history_values,
                        horizons=horizons,
                        reference_val_pred=reference_val_pred,
                        reference_test_pred=reference_test_pred,
                        trial_stopwatch=trial_stopwatch,
                        trial_run_id=trial_run.run_id,
                        register_model=trial_config.tracking.register_model,
                    )
                else:
                    val_metrics, test_metrics = self._run_per_horizon(
                        deps=deps,
                        adapter_cls=adapter_cls,
                        model_spec=model_spec,
                        data=data,
                        trial_config=trial_config,
                        device=device,
                        history_dates=history_dates,
                        history_values=history_values,
                        horizons=horizons,
                        reference_val_pred=reference_val_pred,
                        reference_test_pred=reference_test_pred,
                        base_tags=base_tags,
                        trial_stopwatch=trial_stopwatch,
                    )

            # `trial_total_s` ya cerro (salimos del `with trial_stopwatch.track("trial_total_s")`
            # de arriba): recien aca se puede leer su valor final. `_run_multi_output`/
            # `_run_per_horizon` ya logueraon el resto de `trial_stopwatch.as_metrics()` desde
            # adentro del bloque (ese `trial_total_s` en particular todavia no estaba cerrado).
            deps.tracking.log_metrics({"time/trial_total_s": trial_stopwatch.elapsed("trial_total_s") or 0.0})
            deps.tracking.log_metrics(val_metrics.as_mlflow_metrics())
            deps.tracking.log_metrics(test_metrics.as_mlflow_metrics())

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_code_artifacts(tmp_dir, provenance, PACKAGE_DIR)
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="code")

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

    # ------------------------------------------------------------------
    # multi_output
    # ------------------------------------------------------------------
    def _run_multi_output(
        self,
        deps: RunSearchDependencies,
        adapter_cls: type,
        model_spec: ModelSpec,
        data: _TrialData,
        trial_config: ExperimentConfig,
        device: Device,
        history_dates: tuple,
        history_values: np.ndarray,
        horizons: tuple[int, ...],
        reference_val_pred: Predictions,
        reference_test_pred: Predictions,
        trial_stopwatch: Stopwatch,
        trial_run_id: str | None,
        register_model: bool,
    ) -> tuple[MetricSet, MetricSet]:
        adapter = adapter_cls()
        adapter.build(model_spec, n_features=data.n_features, n_outputs=len(horizons), device=device)
        if hasattr(adapter, "set_history"):
            adapter.set_history(history_dates, history_values)

        with trial_stopwatch.track("train_total_s"):
            fit_result = adapter.fit(
                data.train_seq,
                data.val_seq,
                trial_config.training,
                train_y=data.train_targets.y,
                val_y=data.val_targets.y,
            )

        _log_epoch_curves(deps.tracking, fit_result)
        if fit_result.epochs > 0:
            deps.tracking.log_metrics(
                {
                    "time/train_to_best_epoch_s": fit_result.train_to_best_epoch_s,
                    "time/train_samples_per_s": fit_result.train_samples_per_s,
                    "train/best_epoch": float(fit_result.best_epoch),
                    "train/epochs": float(fit_result.epochs),
                }
            )

        with trial_stopwatch.track("eval_val_s"):
            val_pred = adapter.predict(data.val_seq)
            val_metrics = self._evaluate.execute(
                "val", horizons, data.val_targets.y, val_pred.y_pred, reference_val_pred.y_pred
            )

        with trial_stopwatch.track("predict_test_s"):
            test_pred = adapter.predict(data.test_seq)

        with trial_stopwatch.track("eval_test_s"):
            test_metrics = self._evaluate.execute(
                "test", horizons, data.test_targets.y, test_pred.y_pred, reference_test_pred.y_pred
            )

        n_test = len(data.test_seq.anchor_dates)
        predict_test_s = trial_stopwatch.elapsed("predict_test_s") or 0.0
        predict_per_sample_ms = (predict_test_s / n_test * 1000.0) if n_test else 0.0
        deps.tracking.log_metrics({"time/predict_per_sample_ms": predict_per_sample_ms})

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            _predictions_dataframe(val_pred, data.val_targets).write_parquet(tmp_dir / "val.parquet")
            _predictions_dataframe(test_pred, data.test_targets).write_parquet(tmp_dir / "test.parquet")
            deps.tracking.log_artifact_dir(tmp_dir, artifact_path="predictions")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            write_json_artifact(tmp_dir, "timings.json", timings_payload(trial_stopwatch))
            deps.tracking.log_artifact_dir(tmp_dir, artifact_path="timings")

        with trial_stopwatch.track("model_log_s"), tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            adapter.save(tmp_dir / "model_state.json")
            deps.tracking.log_artifact_dir(tmp_dir, artifact_path="model")
        deps.tracking.log_metrics({"time/model_log_s": trial_stopwatch.elapsed("model_log_s") or 0.0})

        if register_model and trial_run_id is not None:
            with trial_stopwatch.track("register_model_s"):
                uc_name = f"{UC_MODEL_PREFIX}{model_spec.name}"
                version = deps.tracking.register_model(
                    run_id=trial_run_id, artifact_path="model", name=uc_name
                )
            register_model_s = trial_stopwatch.elapsed("register_model_s") or 0.0
            deps.tracking.log_metrics({"time/register_model_s": register_model_s})
            deps.tracking.set_tags({"registered_model_name": uc_name, "registered_model_version": version})

        # Ultimo: incluye train_total_s/eval_*/model_log_s/register_model_s ya trackeados arriba.
        deps.tracking.log_metrics(trial_stopwatch.as_metrics())
        return val_metrics, test_metrics

    # ------------------------------------------------------------------
    # per_horizon (§3.3: "en la aplicacion", un run nieto de MLflow por horizonte)
    # ------------------------------------------------------------------
    def _run_per_horizon(
        self,
        deps: RunSearchDependencies,
        adapter_cls: type,
        model_spec: ModelSpec,
        data: _TrialData,
        trial_config: ExperimentConfig,
        device: Device,
        history_dates: tuple,
        history_values: np.ndarray,
        horizons: tuple[int, ...],
        reference_val_pred: Predictions,
        reference_test_pred: Predictions,
        base_tags: dict[str, str],
        trial_stopwatch: Stopwatch,
    ) -> tuple[MetricSet, MetricSet]:
        val_horizon_metrics: list[HorizonMetrics] = []
        test_horizon_metrics: list[HorizonMetrics] = []
        manifest: dict[str, Any] = {}
        summed_time: dict[str, float] = {}

        for j, h in enumerate(horizons):
            outcome = self._run_single_horizon(
                deps=deps,
                adapter_cls=adapter_cls,
                model_spec=model_spec,
                data=data,
                trial_config=trial_config,
                device=device,
                history_dates=history_dates,
                history_values=history_values,
                horizon=h,
                horizon_index=j,
                reference_val_pred=reference_val_pred,
                reference_test_pred=reference_test_pred,
                base_tags=base_tags,
            )
            val_horizon_metrics.append(outcome.val_metrics)
            test_horizon_metrics.append(outcome.test_metrics)
            manifest[f"h{h:02d}"] = outcome.run_id
            for key, value in outcome.time_metrics.items():
                summed_time[key] = summed_time.get(key, 0.0) + value

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            write_json_artifact(tmp_dir, "per_horizon_runs.json", manifest)
            deps.tracking.log_artifact_dir(tmp_dir, artifact_path="model")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            write_json_artifact(tmp_dir, "timings.json", timings_payload(trial_stopwatch))
            deps.tracking.log_artifact_dir(tmp_dir, artifact_path="timings")

        # Suma de los 8 horizontes bajo las mismas claves `time/*` que multi_output (§3.12):
        # comparable como "costo total de este trial", aunque sean 8 modelos en vez de uno.
        deps.tracking.log_metrics(summed_time)
        deps.tracking.log_metrics(trial_stopwatch.as_metrics())

        val_metrics = MetricSet(split="val", horizons=tuple(val_horizon_metrics))
        test_metrics = MetricSet(split="test", horizons=tuple(test_horizon_metrics))
        return val_metrics, test_metrics

    def _run_single_horizon(
        self,
        deps: RunSearchDependencies,
        adapter_cls: type,
        model_spec: ModelSpec,
        data: _TrialData,
        trial_config: ExperimentConfig,
        device: Device,
        history_dates: tuple,
        history_values: np.ndarray,
        horizon: int,
        horizon_index: int,
        reference_val_pred: Predictions,
        reference_test_pred: Predictions,
        base_tags: dict[str, str],
    ) -> _HorizonOutcome:
        horizon_spec = replace(model_spec, params={**model_spec.params, "horizons": [horizon]})
        adapter = adapter_cls()
        adapter.build(horizon_spec, n_features=data.n_features, n_outputs=1, device=device)
        if hasattr(adapter, "set_history"):
            adapter.set_history(history_dates, history_values)

        horizon_stopwatch = deps.stopwatch_factory()
        train_y = data.train_targets.for_horizon(horizon)
        val_y = data.val_targets.for_horizon(horizon)
        test_y = data.test_targets.for_horizon(horizon)
        ref_val_y = reference_val_pred.y_pred[:, [horizon_index]]
        ref_test_y = reference_test_pred.y_pred[:, [horizon_index]]

        with horizon_stopwatch.track("train_total_s"):
            fit_result = adapter.fit(
                data.train_seq, data.val_seq, trial_config.training, train_y=train_y, val_y=val_y
            )
        with horizon_stopwatch.track("eval_val_s"):
            val_pred = adapter.predict(data.val_seq)
            val_metric_set = self._evaluate.execute("val", (horizon,), val_y, val_pred.y_pred, ref_val_y)
        with horizon_stopwatch.track("predict_test_s"):
            test_pred = adapter.predict(data.test_seq)
        with horizon_stopwatch.track("eval_test_s"):
            test_metric_set = self._evaluate.execute("test", (horizon,), test_y, test_pred.y_pred, ref_test_y)

        n_test = len(data.test_seq.anchor_dates)
        predict_test_s = horizon_stopwatch.elapsed("predict_test_s") or 0.0
        predict_per_sample_ms = (predict_test_s / n_test * 1000.0) if n_test else 0.0

        started_at = datetime.now(timezone.utc)
        horizon_run_name = f"h{horizon:02d}__{started_at.strftime('%Y%m%d-%H%M')}"
        with deps.tracking.start_run(
            trial_config.tracking.experiment, horizon_run_name, nested=True
        ) as horizon_run:
            deps.tracking.set_tags({**base_tags, "horizon": str(horizon)})
            deps.tracking.log_metrics(val_metric_set.as_mlflow_metrics())
            deps.tracking.log_metrics(test_metric_set.as_mlflow_metrics())
            deps.tracking.log_metrics({"time/predict_per_sample_ms": predict_per_sample_ms})
            _log_epoch_curves(deps.tracking, fit_result)
            if fit_result.epochs > 0:
                deps.tracking.log_metrics(
                    {
                        "time/train_to_best_epoch_s": fit_result.train_to_best_epoch_s,
                        "time/train_samples_per_s": fit_result.train_samples_per_s,
                        "train/best_epoch": float(fit_result.best_epoch),
                        "train/epochs": float(fit_result.epochs),
                    }
                )

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                _predictions_dataframe(val_pred, _single_horizon_targets(val_y, horizon)).write_parquet(
                    tmp_dir / "val.parquet"
                )
                _predictions_dataframe(test_pred, _single_horizon_targets(test_y, horizon)).write_parquet(
                    tmp_dir / "test.parquet"
                )
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="predictions")

            with horizon_stopwatch.track("model_log_s"), tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                adapter.save(tmp_dir / "model_state.json")
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="model")
            deps.tracking.log_metrics({"time/model_log_s": horizon_stopwatch.elapsed("model_log_s") or 0.0})

            if trial_config.tracking.register_model:
                with horizon_stopwatch.track("register_model_s"):
                    uc_name = f"{UC_MODEL_PREFIX}{model_spec.name}_h{horizon:02d}"
                    version = deps.tracking.register_model(
                        run_id=horizon_run.run_id, artifact_path="model", name=uc_name
                    )
                deps.tracking.log_metrics(
                    {"time/register_model_s": horizon_stopwatch.elapsed("register_model_s") or 0.0}
                )
                deps.tracking.set_tags(
                    {"registered_model_name": uc_name, "registered_model_version": version}
                )

            deps.tracking.log_metrics(horizon_stopwatch.as_metrics())

        return _HorizonOutcome(
            horizon=horizon,
            val_metrics=val_metric_set.horizons[0],
            test_metrics=test_metric_set.horizons[0],
            val_pred=val_pred,
            test_pred=test_pred,
            fit_epochs=fit_result.epochs,
            fit_best_epoch=fit_result.best_epoch,
            fit_train_losses=fit_result.train_losses,
            fit_val_losses=fit_result.val_losses,
            fit_epoch_seconds=fit_result.epoch_seconds,
            fit_train_to_best_epoch_s=fit_result.train_to_best_epoch_s,
            fit_train_samples_per_s=fit_result.train_samples_per_s,
            time_metrics=horizon_stopwatch.as_metrics(),
            run_id=horizon_run.run_id,
        )

    # ------------------------------------------------------------------
    # preparacion de datos (naive vs. BuildFeatureMatrix, §3.6)
    # ------------------------------------------------------------------
    def _prepare_trial_data(
        self,
        trial_config: ExperimentConfig,
        model_spec: ModelSpec,
        split_dfs: SplitDataFrames,
        target: TargetVariable,
        horizons: tuple[int, ...],
    ) -> _TrialData:
        lookback = trial_config.sequence.lookback_days

        if model_spec.family is ModelFamily.NAIVE:
            # Decision 040: los baselines naive no pasan por BuildFeatureMatrix -- solo el
            # propio target rezagado. La referencia de persistencia reusa exactamente los
            # mismos objetos (no hace falta reconstruirlos: son identicos bit a bit de todos
            # modos, ver docstring del modulo).
            train_seq, train_targets = _build_sequences_and_targets(
                split_dfs.train, target, horizons, lookback
            )
            val_seq, val_targets = _build_sequences_and_targets(split_dfs.val, target, horizons, lookback)
            test_seq, test_targets = _build_sequences_and_targets(split_dfs.test, target, horizons, lookback)
            return _TrialData(
                train_seq=train_seq,
                train_targets=train_targets,
                val_seq=val_seq,
                val_targets=val_targets,
                test_seq=test_seq,
                test_targets=test_targets,
                reference_val_seq=val_seq,
                reference_val_targets=val_targets,
                reference_test_seq=test_seq,
                reference_test_targets=test_targets,
                n_features=1,
                feature_columns=(target.actual_column,),
            )

        if self._deps.build_feature_matrix is None:
            raise RuntimeError(
                f"El modelo {model_spec.name!r} (family={model_spec.family}) requiere "
                "BuildFeatureMatrix (§3.6, Fase 3) pero RunSearchDependencies.build_feature_matrix "
                "es None -- ver interfaces/container.py::build_run_search."
            )

        feature_matrices = self._deps.build_feature_matrix.execute(
            split_dfs,
            list(trial_config.features.groups),
            list(trial_config.features.experimental_transforms),
            trial_config.features.imputation_max_ffill_days,
            trial_config.features.scaling,
            list(trial_config.features.exclude),
        )
        feature_columns = list(feature_matrices.feature_columns)
        spec = SequenceSpec(lookback_days=lookback)

        target_builder = TargetBuilder(target, horizons)
        train_seq = SequenceBuilder(spec).build(feature_matrices.train, feature_columns)
        train_targets = target_builder.build(feature_matrices.train, anchor_dates=train_seq.anchor_dates)
        val_seq = SequenceBuilder(spec).build(feature_matrices.val, feature_columns)
        val_targets = target_builder.build(feature_matrices.val, anchor_dates=val_seq.anchor_dates)
        test_seq = SequenceBuilder(spec).build(feature_matrices.test, feature_columns)
        test_targets = target_builder.build(feature_matrices.test, anchor_dates=test_seq.anchor_dates)

        # Referencia de persistencia: mismo `lookback` (para que los `anchor_dates` calcen 1:1
        # con los del modelo evaluado, ver docstring del modulo), pero sobre el dataframe crudo
        # del split (sin imputar/escalar) y un unico feature (`target.actual_column`).
        reference_val_seq, reference_val_targets = _build_sequences_and_targets(
            split_dfs.val, target, horizons, lookback
        )
        reference_test_seq, reference_test_targets = _build_sequences_and_targets(
            split_dfs.test, target, horizons, lookback
        )

        return _TrialData(
            train_seq=train_seq,
            train_targets=train_targets,
            val_seq=val_seq,
            val_targets=val_targets,
            test_seq=test_seq,
            test_targets=test_targets,
            reference_val_seq=reference_val_seq,
            reference_val_targets=reference_val_targets,
            reference_test_seq=reference_test_seq,
            reference_test_targets=reference_test_targets,
            n_features=len(feature_columns),
            feature_columns=tuple(feature_columns),
        )


def _extract_objective(trial: Trial, search: SearchSpec) -> float:
    """Valor de `search.objective` (p. ej. `"val/kge/mean"`, §4.1) para el `Trial` recien
    corrido -- lo que `TpeSampler.report()` necesita para el siguiente `ask()`. `NaN` si el
    split pedido no tiene metricas finitas (§2.1: huecos de target en TEST); `TpeSampler` ya
    sabe convertir eso en "lo peor posible" en vez de romper el `Study`."""
    metric_set = trial.val_metrics if search.objective_split == "val" else trial.test_metrics
    if metric_set is None:
        return float("nan")
    return metric_set.mean(search.objective_metric)


def _log_epoch_curves(tracking: TrackingPort, fit_result: Any) -> None:
    """Curvas de loss + `time/train_epoch_s` por epoch (§3.12), logueadas con `step=epoch` una
    vez que `fit()` termino (no en vivo epoch a epoch: el adaptador no depende de `TrackingPort`,
    §3.3 -- separacion de responsabilidades). No-op para adaptadores sin entrenamiento
    iterativo (`FitResult.epochs == 0`, naive/Fase 2)."""
    for epoch, (train_loss, val_loss, epoch_s) in enumerate(
        zip(fit_result.train_losses, fit_result.val_losses, fit_result.epoch_seconds, strict=True), start=1
    ):
        tracking.log_metrics(
            {"train/loss": train_loss, "val/loss": val_loss, "time/train_epoch_s": epoch_s}, step=epoch
        )


def _single_horizon_targets(y: np.ndarray, horizon: int) -> Targets:
    return Targets(y=y, horizons=(horizon,))


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
