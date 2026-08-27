"""`ExperimentConfig`: value object completo de un YAML de `configs/experiments/*.yaml` (Fase 2,
docs/rio_search_plan.md §4.1). Distinto de
`infrastructure.datasets.experiment_yaml.DatasetDescribeConfig` (Fase 1): ese lector es un
subconjunto minimo para `rio-search datasets describe` y no se toca; este VO es el contrato
completo que consume `RunSearch` (dataset + provenance + split + features + sequence + model +
training + tracking). Sin dependencias del proyecto (regla de `domain`): el parseo de YAML en
si (lectura de archivo, `yaml.safe_load`) vive en
`infrastructure.experiments.experiment_config_loader`, que le pasa un `dict` ya parseado a
`ExperimentConfig.from_dict` (mismo patron que `FeatureCatalog.from_dict`, Fase 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rio_search.domain.datasets.feature_transform import ExperimentalTransformSpec
from rio_search.domain.datasets.split_policy import SplitPolicy
from rio_search.domain.experiments.training_spec import TrainingSpec
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.target_variable import TargetVariable


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    source: str
    refresh: str  # application.ports.snapshot_sync.RefreshMode
    version: str  # "latest" o "delta-<N>" (§4.1: reproduccion exacta)
    target: TargetVariable
    horizons: tuple[int, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetConfig":
        return cls(
            source=str(data.get("source", "gold_training_dataset_v0")),
            refresh=str(data.get("refresh", "ensure_latest")),
            version=str(data.get("version", "latest")),
            target=TargetVariable(data["target"]),
            horizons=tuple(int(h) for h in data["horizons"]),
        )


@dataclass(frozen=True, slots=True)
class ProvenanceConfig:
    require_clean_git: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProvenanceConfig":
        data = data or {}
        return cls(require_clean_git=bool(data.get("require_clean_git", False)))


@dataclass(frozen=True, slots=True)
class FeaturesConfig:
    """Bloque `features:` (§4.1). Los baselines naive (Fase 2) no lo usan (§3.3: "no usan
    features, solo el propio target rezagado"): sus YAML omiten esta seccion y quedan con los
    defaults vacios."""

    groups: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    experimental_transforms: tuple[ExperimentalTransformSpec, ...] = ()
    imputation_max_ffill_days: int = 3
    scaling: str = "none"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FeaturesConfig":
        data = data or {}
        imputation = data.get("imputation") or {}
        return cls(
            groups=tuple(data.get("groups", []) or []),
            exclude=tuple(data.get("exclude", []) or []),
            experimental_transforms=tuple(
                ExperimentalTransformSpec.from_dict(t)
                for t in (data.get("experimental_transforms", []) or [])
            ),
            imputation_max_ffill_days=int(imputation.get("max_ffill_days", 3)),
            scaling=str(data.get("scaling", "none")),
        )


@dataclass(frozen=True, slots=True)
class SequenceConfig:
    lookback_days: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SequenceConfig":
        return cls(lookback_days=int(data["lookback_days"]))


@dataclass(frozen=True, slots=True)
class TrackingConfig:
    experiment: str
    tags: dict[str, str] = field(default_factory=dict)
    register_model: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackingConfig":
        return cls(
            experiment=str(data["experiment"]),
            tags={str(k): str(v) for k, v in (data.get("tags") or {}).items()},
            register_model=bool(data.get("register_model", False)),
        )


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    name: str
    description: str
    dataset: DatasetConfig
    provenance: ProvenanceConfig
    split: SplitPolicy
    features: FeaturesConfig
    sequence: SequenceConfig
    model: ModelSpec
    training: TrainingSpec
    tracking: TrackingConfig

    def trials(self) -> tuple["ExperimentConfig", ...]:
        """Sin bloque `search:` en el YAML (grid/random/tpe, §4.1) la busqueda tiene un unico
        trial: esta misma config (§0, vocabulario: "un experimento simple es una busqueda de
        un solo trial"). La expansion real de `search:` es Fase 3."""
        return (self,)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentConfig":
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            dataset=DatasetConfig.from_dict(data["dataset"]),
            provenance=ProvenanceConfig.from_dict(data.get("provenance")),
            split=SplitPolicy.from_dict(data["split"]),
            features=FeaturesConfig.from_dict(data.get("features")),
            sequence=SequenceConfig.from_dict(data["sequence"]),
            model=ModelSpec.from_dict(data["model"]),
            training=TrainingSpec.from_dict(data.get("training")),
            tracking=TrackingConfig.from_dict(data["tracking"]),
        )
