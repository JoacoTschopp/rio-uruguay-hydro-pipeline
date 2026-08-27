"""Lector minimo de config de experimento para `rio-search datasets describe` (Fase 1,
docs/rio_search_plan.md §4.1, §5): extrae solo lo que `DescribeDataset` necesita (target,
horizontes, split, grupos de features). **No** es el `ExperimentConfig` completo del contexto
`experiments` (§3.2) -- ese VO llega con la Fase 2 y probablemente reemplace este lector por
uno que parsea el YAML entero de una sola vez (search/model/training incluidos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from rio_search.domain.datasets.split_policy import SplitPolicy, TrainWindow
from rio_search.domain.shared.target_variable import TargetVariable


@dataclass(frozen=True, slots=True)
class DatasetDescribeConfig:
    name: str
    target: TargetVariable
    horizons: tuple[int, ...]
    split_policy: SplitPolicy
    feature_groups: tuple[str, ...]


def load_dataset_describe_config(path: Path) -> DatasetDescribeConfig:
    if not path.exists():
        raise FileNotFoundError(f"No existe la config de experimento: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    dataset = data["dataset"]
    split = data["split"]
    features = data.get("features", {})

    train_window_raw = split.get("train_window", {})
    if "start" in train_window_raw:
        train_window = TrainWindow(start=_parse_date(train_window_raw["start"]))
    elif "years" in train_window_raw:
        train_window = TrainWindow(years=int(train_window_raw["years"]))
    else:
        raise ValueError(f"{path}: split.train_window requiere 'start' o 'years' (§3.6, §4.1)")

    policy = SplitPolicy(
        policy=split["policy"],
        embargo_days=int(split.get("embargo_days", 14)),
        train_window=train_window,
    )

    return DatasetDescribeConfig(
        name=str(data["name"]),
        target=TargetVariable(dataset["target"]),
        horizons=tuple(int(h) for h in dataset["horizons"]),
        split_policy=policy,
        feature_groups=tuple(features.get("groups", [])),
    )


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
