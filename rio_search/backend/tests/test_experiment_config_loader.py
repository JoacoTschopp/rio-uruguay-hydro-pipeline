"""Tests de `infrastructure.experiments.experiment_config_loader` (Fase 2,
docs/rio_search_plan.md §4.1, §5): carga los 3 YAML de baseline reales del repo."""

from __future__ import annotations

from pathlib import Path

import pytest

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.experiments.experiment_config_loader import load_experiment_config

CONFIGS_DIR = Path(__file__).resolve().parents[1] / "configs" / "experiments"


@pytest.mark.parametrize(
    "filename,model_name",
    [
        ("persistence_baseline_v1.yaml", "persistence"),
        ("climatology_baseline_v1.yaml", "climatology"),
        ("seasonal_naive_baseline_v1.yaml", "seasonal_naive"),
    ],
)
def test_loads_real_naive_baseline_configs(filename: str, model_name: str) -> None:
    loaded = load_experiment_config(CONFIGS_DIR / filename)
    config = loaded.config

    assert config.model.name == model_name
    assert config.model.horizon_strategy is HorizonStrategy.MULTI_OUTPUT
    assert config.dataset.target is TargetVariable.CAUDAL
    assert config.dataset.horizons == (1, 2, 3, 4, 5, 6, 7, 14)
    assert config.split.policy == "rolling_365"
    assert config.sequence.lookback_days == 1
    assert config.tracking.experiment == "/Users/joaquintschopp@gmail.com/rio_search/baselines"
    assert config.provenance.require_clean_git is False
    assert config.features.groups == ()  # baselines naive: sin bloque `features:` (§3.3)
    assert config.trials() == (config,)
    assert len(loaded.config_sha256) == 64
    assert loaded.raw_dict["model"]["name"] == model_name


def test_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_experiment_config(tmp_path / "no_existe.yaml")


def test_config_sha256_changes_when_file_content_changes(tmp_path: Path) -> None:
    base = (CONFIGS_DIR / "persistence_baseline_v1.yaml").read_text(encoding="utf-8")
    path_a = tmp_path / "a.yaml"
    path_b = tmp_path / "b.yaml"
    path_a.write_text(base, encoding="utf-8")
    path_b.write_text(base.replace("persistence_baseline_v1", "persistence_baseline_v2"), encoding="utf-8")

    loaded_a = load_experiment_config(path_a)
    loaded_b = load_experiment_config(path_b)
    assert loaded_a.config_sha256 != loaded_b.config_sha256
