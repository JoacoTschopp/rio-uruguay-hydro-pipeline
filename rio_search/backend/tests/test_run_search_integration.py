"""Test de integracion de `RunSearch` contra Databricks/MLflow real (Fase 2,
docs/rio_search_plan.md §5, criterio de cierre): corre la busqueda `persistence` real y
verifica el criterio de cierre exacto -- skill de persistencia = 0 por construccion, en un
run real (no offline). Requiere el perfil de Databricks (`~/.databrickscfg`) autenticado;
se salta con `pytest -m "not integration"` (default del repo, ver pyproject.toml).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from rio_search.domain.experiments.run_status import RunStatus
from rio_search.infrastructure.experiments.experiment_config_loader import load_experiment_config
from rio_search.interfaces.container import build_run_search

CONFIGS_DIR = Path(__file__).resolve().parents[1] / "configs" / "experiments"


@pytest.mark.integration
def test_persistence_baseline_real_run_has_zero_skill_on_databricks() -> None:
    loaded = load_experiment_config(CONFIGS_DIR / "persistence_baseline_v1.yaml")
    run_search = build_run_search()

    search = run_search.execute(loaded)

    assert search.status is RunStatus.FINISHED
    assert search.run_id is not None
    assert len(search.trials) == 1

    trial = search.trials[0]
    assert trial.run_id is not None
    assert trial.test_metrics is not None and trial.val_metrics is not None

    for h in loaded.config.dataset.horizons:
        skill_test = trial.test_metrics.horizon(h).get("skill_vs_persistence")
        skill_val = trial.val_metrics.horizon(h).get("skill_vs_persistence")
        assert not math.isnan(skill_test)
        assert skill_test == 0.0
        assert skill_val == 0.0
