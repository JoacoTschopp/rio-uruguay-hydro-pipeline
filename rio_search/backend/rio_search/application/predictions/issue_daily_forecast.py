"""`IssueDailyForecast` (Fase 6, docs/rio_search_plan.md §3.8): protocolo completo de inferencia
diaria.

1. `RefreshDataset` con el mismo protocolo de frescura de §3.6 (Decision #10).
2. Resuelve device (Decision #6) y carga el campeon **exactamente** como se guardo (Decision 039:
   `torch.save(state_dict)` + JSON, nunca `mlflow.pytorch.log_model`) -- `run_id` -> `model/`,
   `features/spec.json`, `config/experiment.yaml`.
3. `AsOfPolicy`: resuelve `as_of` (ultimo dia con inputs completos tras ffill acotado) y
   `data_lag_days`.
4. Predice t+1..t+7, t+14 respecto de `as_of`; guarda el `Forecast` (SQLite + parquet) y loguea
   un run corto en `daily_forecast` con sus tiempos.
5. Publicacion opcional al Volume (`--publish`).

Hallazgo real de esta fase (ver Decision 04x en `docs/decisions.md`): §3.5 del plan lista
`preprocess/pipeline.pkl` entre los artefactos de un trial, pero `RunSearch` (Fase 2/3, ya cerrada
y testeada, 264 tests) nunca lo logueo -- solo `imputer_stats`/`scaler_stats` en memoria, nunca
serializados. Sin ese artefacto, "cargar exactamente los artefactos del run, nada se recalcula
distinto" (§3.8 paso 2) es literalmente imposible. Esta clase lo resuelve **reconstruyendo** el
pipeline de forma determinista, sin tocar `RunSearch`: el propio run guarda `split/split.json`
con el rango exacto de fechas de TRAIN que uso (`2000-01-01..2024-07-12` para el campeon
provisorio, verificado real) -- Gold es una serie observada historica que no se reescribe, asi
que recortar el dataset **actual** a ese mismo rango de fechas y volver a ajustar
`ImputerStats`/`ScalerStats` (`application.datasets.build_feature_matrix.BuildFeatureMatrix`,
mismo codigo que uso el entrenamiento real) reproduce los mismos estadisticos bit a bit, sin
inventar una politica de preprocesamiento nueva. El riesgo documentado: si Gold alguna vez
corrige datos historicos (no solo agrega dias nuevos), esta reconstruccion dejaria de ser
identica al pipeline original -- no observado en este repo hasta ahora.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml

from rio_search.application.datasets.build_feature_matrix import BuildFeatureMatrix
from rio_search.application.datasets.refresh_dataset import RefreshDataset
from rio_search.application.ports.artifact_repository import ArtifactRepositoryPort
from rio_search.application.ports.champion_store import ChampionStorePort
from rio_search.application.ports.device_resolver import DeviceResolver, PreferredDevice
from rio_search.application.ports.forecast_repository import ForecastRepositoryPort
from rio_search.application.ports.git_provenance import GitProvenancePort
from rio_search.application.ports.model_registry import ModelRegistryPort
from rio_search.application.ports.stopwatch import Stopwatch
from rio_search.application.ports.tracking import TrackingPort
from rio_search.application.ports.tracking_read import TrackingReadPort
from rio_search.application.ports.volume_publisher import VolumePublisherPort
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.datasets.sequence_spec import SequenceSpec
from rio_search.domain.experiments.experiment_config import ExperimentConfig
from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.predictions.as_of_policy import AsOfPolicy
from rio_search.domain.predictions.forecast import Forecast, ForecastPoint
from rio_search.domain.shared.device import Device
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.datasets.sequence_builder import SequenceBuilder, Sequences
from rio_search.infrastructure.models.types import Predictions
from rio_search.infrastructure.tracking.artifacts import write_json_artifact

DAILY_FORECAST_EXPERIMENT_SUFFIX = "daily_forecast"


@dataclass(frozen=True, slots=True)
class _SplitDataFramesLike:
    """Duck-type minimo de `application.datasets.build_split.SplitDataFrames`: solo los tres
    atributos que lee `BuildFeatureMatrix.execute` (nunca `.split`). No se reusa esa clase real
    porque exige un `Split` valido (train < val < test <= anchor, §3.6) que no tiene sentido acá
    -- no hay VAL/TEST en inferencia, solo TRAIN (para ajustar el pipeline, ver docstring del
    modulo) y la ventana de inferencia (que reusa el slot `test`)."""

    train: pl.DataFrame
    val: pl.DataFrame
    test: pl.DataFrame


@dataclass(frozen=True, slots=True)
class IssueDailyForecastDependencies:
    refresh_dataset: RefreshDataset
    device_resolver: DeviceResolver
    git_provenance: GitProvenancePort
    champion_store: ChampionStorePort
    tracking_reader: TrackingReadPort
    artifact_repository: ArtifactRepositoryPort
    tracking: TrackingPort
    model_registry: ModelRegistryPort
    feature_catalog: FeatureCatalog
    forecast_repository: ForecastRepositoryPort
    stopwatch: Stopwatch  # compartido con `refresh_dataset` (mismo patron que RunSearchDependencies)
    experiment_base_path: str  # "/Users/<profile>/rio_search"
    artifacts_cache_dir: Path
    volume_publisher: VolumePublisherPort | None = None


class IssueDailyForecast:
    def __init__(self, deps: IssueDailyForecastDependencies) -> None:
        self._deps = deps

    def execute(
        self,
        target: TargetVariable = TargetVariable.CAUDAL,
        as_of_override: date | None = None,
        device_preferred: PreferredDevice = "auto",
        publish: bool = False,
    ) -> Forecast:
        deps = self._deps
        stopwatch = deps.stopwatch
        today = datetime.now(timezone.utc).date()

        champion = deps.champion_store.get(target)
        if champion is None:
            raise RuntimeError(
                f"No hay campeon promovido para target={target.value!r}. Corré primero "
                "`rio-search champions set --run <run_id> --target "
                f"{target.value}` (PromoteChampion, §4.2)."
            )

        now_hms = datetime.now(timezone.utc).strftime("%H%M%S")
        run_name = f"forecast__{target.value}__{today.isoformat()}__{now_hms}"
        experiment_path = f"{deps.experiment_base_path}/{DAILY_FORECAST_EXPERIMENT_SUFFIX}"

        with deps.tracking.start_run(experiment_path, run_name, nested=False) as run:
            with stopwatch.track("total_s"):
                refresh_result = deps.refresh_dataset.execute(mode="ensure_latest")
                dataset_version = refresh_result.dataset_version
                df = refresh_result.dataframe

                device = deps.device_resolver.resolve(preferred=device_preferred)
                provenance = deps.git_provenance.capture()

                with stopwatch.track("model_load_s"):
                    champion_run = deps.tracking_reader.get_run(champion.run_id)
                    if champion_run is None:
                        raise RuntimeError(f"champion.run_id={champion.run_id!r} ya no existe en MLflow")
                    exp_config, split_train_start, split_train_end = self._load_champion_config(
                        champion.run_id
                    )
                    adapter, feature_columns_trained = self._load_champion_model(
                        champion_run_id=champion.run_id,
                        horizon_strategy=exp_config.model.horizon_strategy,
                        device=device,
                    )

                with stopwatch.track("preprocess_s"):
                    as_of, data_lag_days, sequences = self._build_inference_window(
                        df=df,
                        exp_config=exp_config,
                        train_start=split_train_start,
                        train_end=split_train_end,
                        feature_columns_trained=feature_columns_trained,
                        as_of_override=as_of_override,
                        today=today,
                    )

                with stopwatch.track("predict_s"):
                    predictions = adapter.predict(sequences)

            points = tuple(
                ForecastPoint(
                    horizon=h,
                    target_date=as_of + timedelta(days=h),
                    value=float(predictions.y_pred[0, j]),
                )
                for j, h in enumerate(predictions.horizons)
            )

            forecast = Forecast(
                target=target,
                as_of=as_of,
                issued_at=datetime.now(timezone.utc).isoformat(),
                dataset_delta_version=dataset_version.delta_version,
                dataset_sha256=dataset_version.sha256,
                champion_run_id=champion.run_id,
                champion_model_name=champion.model_name,
                device_type=device.type,
                data_lag_days=data_lag_days,
                points=points,
                forecast_run_id=run.run_id,
            )

            if publish and deps.volume_publisher is not None:
                with tempfile.TemporaryDirectory() as tmp:
                    staging_path = Path(tmp) / "forecast.parquet"
                    _write_points_parquet(forecast, staging_path)
                    remote_name = (
                        f"{target.value}_{as_of.isoformat()}_{forecast.issued_at.replace(':', '')}.parquet"
                    )
                    published_path = deps.volume_publisher.publish(staging_path, remote_name)
                forecast = replace(forecast, published_path=published_path)

            deps.forecast_repository.save(forecast)

            tags = {
                **device.as_tags(),
                **provenance.as_tags(),
                **champion.as_tags(),
                **forecast.as_tags(),
            }
            deps.tracking.set_tags(tags)
            deps.tracking.log_metrics(stopwatch.as_metrics())
            deps.tracking.log_metrics({f"forecast/h{p.horizon:02d}": p.value for p in points})
            deps.tracking.log_meta_dataset(
                name=f"training_dataset_v0@delta{dataset_version.delta_version}",
                digest=dataset_version.sha256[:8],
                source_path="/Volumes/weather/raw/gold_export_volume/training_dataset_v0.parquet",
                context="daily_forecast",
            )
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                write_json_artifact(tmp_dir, "forecast.json", _forecast_payload(forecast))
                deps.tracking.log_artifact_dir(tmp_dir, artifact_path="forecast")

        return forecast

    # ------------------------------------------------------------------
    # carga del campeon
    # ------------------------------------------------------------------
    def _run_artifacts_dir(self, run_id: str) -> Path:
        d = self._deps.artifacts_cache_dir / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load_champion_config(self, run_id: str) -> tuple[ExperimentConfig, date, date]:
        deps = self._deps
        dst = self._run_artifacts_dir(run_id)
        config_dir = deps.artifact_repository.download(run_id, "config", dst)
        split_dir = deps.artifact_repository.download(run_id, "split", dst)

        config_text = (Path(config_dir) / "experiment.yaml").read_text(encoding="utf-8")
        raw = yaml.safe_load(config_text)
        exp_config = ExperimentConfig.from_dict(raw)

        split_payload = json.loads((Path(split_dir) / "split.json").read_text(encoding="utf-8"))
        train_start = date.fromisoformat(split_payload["train"]["start"])
        train_end = date.fromisoformat(split_payload["train"]["end"])
        return exp_config, train_start, train_end

    def _load_champion_model(
        self, champion_run_id: str, horizon_strategy: HorizonStrategy, device: Device
    ) -> tuple[Any, tuple[str, ...]]:
        deps = self._deps
        dst = self._run_artifacts_dir(champion_run_id)
        features_dir = deps.artifact_repository.download(champion_run_id, "features", dst)
        spec = json.loads((Path(features_dir) / "spec.json").read_text(encoding="utf-8"))
        feature_columns = tuple(spec["feature_columns"])

        model_dir = deps.artifact_repository.download(champion_run_id, "model", dst)
        manifest_path = Path(model_dir) / "per_horizon_runs.json"

        if horizon_strategy is HorizonStrategy.PER_HORIZON or manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            adapter = self._load_per_horizon_adapter(manifest, device)
        else:
            adapter = self._load_single_adapter(champion_run_id, model_dir, device)

        return adapter, feature_columns

    def _load_single_adapter(self, run_id: str, model_dir: Path, device: Device) -> Any:
        """`path` = `model_dir / "model_state.json"` es el nombre que `run_search.py` **siempre**
        pasa a `adapter.save(path)` (`_run_multi_output`/`_run_single_horizon`), no una
        convencion de este modulo: `BaseTorchAdapter.save/load` ignoran el nombre del archivo y
        usan `path.parent` (escriben `model_state_dict.pth` + `architecture.json` ahi), mientras
        que los adaptadores naive (`PersistenceAdapter`, etc.) escriben/leen literalmente ese
        archivo -- pasar el mismo nombre que uso el entrenamiento reproduce el contrato real de
        cada adaptador sin que este modulo necesite conocerlo. El nombre del modelo (para elegir
        `adapter_cls` en el `ModelRegistry`) sale del tag `rio_search.model` del run (Fase 2/3,
        `_base_tags`), **no** de `architecture.json`: ese archivo solo existe para adaptadores
        torch (Decision 039), un campeon naive (baseline, no un caso real pero soportado) nunca
        lo escribe."""
        deps = self._deps
        run = deps.tracking_reader.get_run(run_id)
        if run is None:
            raise RuntimeError(f"run {run_id!r} (modelo del campeon) ya no existe en MLflow")
        model_name = run.rio_search_tag("model")
        if model_name is None:
            raise RuntimeError(f"run {run_id!r} no tiene el tag rio_search.model")
        adapter_cls = deps.model_registry.get(model_name)
        return adapter_cls.load(model_dir / "model_state.json", device)

    def _load_per_horizon_adapter(self, manifest: dict[str, str], device: Device) -> "_PerHorizonEnsemble":
        deps = self._deps
        adapters: dict[int, Any] = {}
        for key, run_id in manifest.items():
            horizon = int(key.lstrip("h"))
            dst = self._run_artifacts_dir(run_id)
            model_dir = deps.artifact_repository.download(run_id, "model", dst)
            adapters[horizon] = self._load_single_adapter(run_id, Path(model_dir), device)
        return _PerHorizonEnsemble(adapters)

    # ------------------------------------------------------------------
    # reconstruccion del pipeline + ventana de inferencia (ver docstring del modulo)
    # ------------------------------------------------------------------
    def _build_inference_window(
        self,
        df: pl.DataFrame,
        exp_config: ExperimentConfig,
        train_start: date,
        train_end: date,
        feature_columns_trained: tuple[str, ...],
        as_of_override: date | None,
        today: date,
    ) -> tuple[date, int, Sequences]:
        deps = self._deps
        exclude = exp_config.features.exclude
        base_columns = [
            c for c in deps.feature_catalog.columns_for(exp_config.features.groups) if c not in exclude
        ]

        max_ffill_days = exp_config.features.imputation_max_ffill_days
        as_of_policy = AsOfPolicy(max_ffill_days=max_ffill_days)
        as_of = as_of_override or _resolve_as_of(df, base_columns, max_ffill_days)
        data_lag_days = as_of_policy.data_lag_days(as_of, today)

        train_df = df.filter(pl.col("fecha").is_between(train_start, train_end, closed="both")).sort("fecha")
        inference_df = df.filter(pl.col("fecha") <= as_of).sort("fecha")
        if inference_df.height < exp_config.sequence.lookback_days:
            raise RuntimeError(
                f"Solo hay {inference_df.height} dias de datos hasta as_of={as_of}, menos que "
                f"sequence.lookback_days={exp_config.sequence.lookback_days} del campeon."
            )

        split_dfs = _SplitDataFramesLike(train=train_df, val=inference_df, test=inference_df)
        feature_matrices = BuildFeatureMatrix(deps.feature_catalog).execute(
            split_dfs,  # type: ignore[arg-type]
            list(exp_config.features.groups),
            list(exp_config.features.experimental_transforms),
            exp_config.features.imputation_max_ffill_days,
            exp_config.features.scaling,
            list(exp_config.features.exclude),
        )

        if feature_matrices.feature_columns != feature_columns_trained:
            raise RuntimeError(
                "La reconstruccion de features no coincide con features/spec.json del campeon "
                f"(entrenado con {len(feature_columns_trained)} columnas, reconstruido con "
                f"{len(feature_matrices.feature_columns)}) -- ¿cambio el catalogo de features "
                "(configs/feature_groups.yaml) desde que se entreno el campeon?"
            )

        window_df = feature_matrices.test.sort("fecha").tail(exp_config.sequence.lookback_days)
        sequences = SequenceBuilder(SequenceSpec(lookback_days=exp_config.sequence.lookback_days)).build(
            window_df, feature_columns=list(feature_matrices.feature_columns)
        )
        if sequences.anchor_dates != (as_of,):
            raise RuntimeError(
                f"La ventana de inferencia no ancla en as_of={as_of} (anclo en "
                f"{sequences.anchor_dates}); revisar continuidad del calendario del dataset."
            )
        return as_of, data_lag_days, sequences


class _PerHorizonEnsemble:
    """Adaptador compuesto para un campeon `per_horizon` (§3.3): un `ModelAdapterPort` real por
    horizonte, cada uno con `n_outputs=1`. `predict()` los corre a todos y concatena en el mismo
    orden de horizontes que declaran sus claves (`hNN`), igual convencion que
    `application.experiments.run_search._run_per_horizon`."""

    def __init__(self, adapters_by_horizon: dict[int, Any]) -> None:
        self._adapters = dict(sorted(adapters_by_horizon.items()))

    def predict(self, X: Sequences) -> Predictions:
        horizons = tuple(self._adapters.keys())
        columns = []
        for h in horizons:
            pred = self._adapters[h].predict(X)
            columns.append(pred.y_pred[:, 0])
        y_pred = np.stack(columns, axis=1)
        return Predictions(y_pred=y_pred, anchor_dates=X.anchor_dates, horizons=horizons)


def _resolve_as_of(
    df: pl.DataFrame, base_columns: list[str], max_ffill_days: int, date_column: str = "fecha"
) -> date:
    """Ultimo dia con todos los `base_columns` no nulos tras `ffill` acotado (ver
    `domain.predictions.as_of_policy.AsOfPolicy`): misma expresion que
    `infrastructure.preprocess.imputers.apply_imputer` usa para TRAIN/VAL/TEST, pero **sin** el
    relleno por mediana (ver docstring del modulo: no se fabrica un dato del dia mas reciente)."""
    if not base_columns:
        raise ValueError("base_columns vacio: no se puede resolver as_of sin columnas de entrada")
    ordered = df.sort(date_column)
    filled = ordered.with_columns([pl.col(c).forward_fill(limit=max_ffill_days) for c in base_columns])
    complete = filled.filter(pl.all_horizontal([pl.col(c).is_not_null() for c in base_columns]))
    if complete.height == 0:
        raise RuntimeError(
            "Ningun dia del dataset tiene todos los inputs requeridos completos (tras ffill "
            f"acotado a {max_ffill_days} dias); revisar cobertura de {base_columns}."
        )
    value = complete.select(pl.col(date_column).max()).item()
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _forecast_payload(forecast: Forecast) -> dict[str, Any]:
    return {
        "target": forecast.target.value,
        "as_of": forecast.as_of.isoformat(),
        "issued_at": forecast.issued_at,
        "dataset_delta_version": forecast.dataset_delta_version,
        "dataset_sha256": forecast.dataset_sha256,
        "champion_run_id": forecast.champion_run_id,
        "champion_model_name": forecast.champion_model_name,
        "device_type": forecast.device_type,
        "data_lag_days": forecast.data_lag_days,
        "forecast_run_id": forecast.forecast_run_id,
        "published_path": forecast.published_path,
        "points": [
            {"horizon": p.horizon, "target_date": p.target_date.isoformat(), "value": p.value}
            for p in forecast.points
        ],
    }


def _write_points_parquet(forecast: Forecast, path: Path) -> None:
    """Parquet minimo de staging para `--publish` (§3.8 paso 5): una fila por `ForecastPoint`,
    independiente del formato interno de `ForecastRepositoryPort` (que puede evolucionar sin
    afectar lo que se sube al Volume)."""
    pl.DataFrame(
        {
            "target": [forecast.target.value] * len(forecast.points),
            "as_of": [forecast.as_of] * len(forecast.points),
            "issued_at": [forecast.issued_at] * len(forecast.points),
            "champion_run_id": [forecast.champion_run_id] * len(forecast.points),
            "horizonte": [p.horizon for p in forecast.points],
            "fecha_objetivo": [p.target_date for p in forecast.points],
            "valor": [p.value for p in forecast.points],
        }
    ).write_parquet(path)
