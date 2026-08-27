"""Carga un YAML completo de `configs/experiments/*.yaml` a `ExperimentConfig` (Fase 2,
docs/rio_search_plan.md §4.1, §5). Distinto de `infrastructure.datasets.experiment_yaml`
(Fase 1, subconjunto minimo para `rio-search datasets describe`, no se toca). El parseo del YAML
en si vive aca (`infrastructure`, el dominio no toca el filesystem); `ExperimentConfig.from_dict`
(dominio, puro) hace el resto -- mismo patron que `feature_catalog_loader.py` (Fase 1).

Tambien calcula `config_sha256` sobre el **texto crudo** del YAML (no sobre el dict parseado):
es el tag `rio_search.config_sha256` (§3.5) -- referencia exacta al archivo tal como esta en el
repo, no a una serializacion que podria variar por reordenamiento de claves.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from rio_search.domain.experiments.experiment_config import ExperimentConfig


@dataclass(frozen=True, slots=True)
class LoadedExperimentConfig:
    config: ExperimentConfig
    raw_yaml: str
    raw_dict: dict[str, Any]
    config_sha256: str
    path: Path


def load_experiment_config(path: Path) -> LoadedExperimentConfig:
    if not path.exists():
        raise FileNotFoundError(f"No existe la config de experimento: {path}")
    raw_yaml = path.read_text(encoding="utf-8")
    raw_dict = yaml.safe_load(raw_yaml) or {}
    config = ExperimentConfig.from_dict(raw_dict)
    config_sha256 = hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()
    return LoadedExperimentConfig(
        config=config, raw_yaml=raw_yaml, raw_dict=raw_dict, config_sha256=config_sha256, path=path
    )
