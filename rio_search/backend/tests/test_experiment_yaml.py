"""Tests del lector minimo de config de experimento (Fase 1, docs/rio_search_plan.md §4.1,
§5): parsea `configs/experiments/bilstm_baseline_v1.yaml` (el YAML real del criterio de
cierre) y valida el manejo de `train_window.start` vs `train_window.years`."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.datasets.experiment_yaml import load_dataset_describe_config

BACKEND_DIR = Path(__file__).resolve().parents[1]
BILSTM_BASELINE_PATH = BACKEND_DIR / "configs" / "experiments" / "bilstm_baseline_v1.yaml"


def test_bilstm_baseline_v1_yaml_exists() -> None:
    assert BILSTM_BASELINE_PATH.exists(), "criterio de cierre de la Fase 1 (§5) requiere este YAML"


def test_load_real_bilstm_baseline_config() -> None:
    config = load_dataset_describe_config(BILSTM_BASELINE_PATH)
    assert config.name == "bilstm_baseline_v1"
    assert config.target == TargetVariable.CAUDAL
    assert config.horizons == (1, 2, 3, 4, 5, 6, 7, 14)
    assert config.split_policy.policy == "rolling_365"
    assert config.split_policy.embargo_days == 14
    assert config.split_policy.train_window.start == date(2008, 1, 1)
    assert config.feature_groups == (
        "caudal_estado",
        "caudal_agregado_alta_frontera",
        "cptec_grid",
    )


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_dataset_describe_config(tmp_path / "no_existe.yaml")


def test_train_window_years_variant(tmp_path: Path) -> None:
    path = tmp_path / "experiment.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "x",
                "dataset": {"target": "nivel", "horizons": [1, 7]},
                "split": {"policy": "calendar_year", "embargo_days": 7, "train_window": {"years": 5}},
                "features": {"groups": ["cptec_grid"]},
            }
        ),
        encoding="utf-8",
    )
    config = load_dataset_describe_config(path)
    assert config.target == TargetVariable.NIVEL
    assert config.split_policy.policy == "calendar_year"
    assert config.split_policy.train_window.years == 5
    assert config.feature_groups == ("cptec_grid",)


def test_train_window_without_start_or_years_raises(tmp_path: Path) -> None:
    path = tmp_path / "experiment.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "x",
                "dataset": {"target": "caudal", "horizons": [1]},
                "split": {"policy": "rolling_365", "train_window": {}},
                "features": {"groups": []},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="train_window"):
        load_dataset_describe_config(path)
