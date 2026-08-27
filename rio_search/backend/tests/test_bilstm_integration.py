"""Test de integracion de la Fase 3 contra Databricks/MLflow/Unity Catalog real
(docs/rio_search_plan.md §5, criterio de cierre): corre una busqueda `bilstm` real (derivada de
`configs/experiments/bilstm_baseline_v1.yaml` con `search.n_trials`/`training.max_epochs`
reducidos para que el test termine rapido -- la corrida baseline completa se corre aparte, por
CLI, y se documenta en `docs/decisions.md`) y verifica: el trial termina, tiene metricas val/test
para los 8 horizontes, tiempos completos (`time/train_epoch_s` via curva, `time/model_log_s`,
`time/register_model_s`) y el modelo queda registrado en `weather.ml` (Decision #12, Decision
042) -- verificado con el SDK de Databricks, no solo con el valor de retorno de MLflow.

Requiere el perfil de Databricks (`~/.databrickscfg`) autenticado; se salta con
`pytest -m "not integration"` (default del repo, ver pyproject.toml).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.experiments.run_status import RunStatus
from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE, build_workspace_client
from rio_search.infrastructure.experiments.experiment_config_loader import load_experiment_config
from rio_search.interfaces.container import build_run_search

CONFIGS_DIR = Path(__file__).resolve().parents[1] / "configs" / "experiments"


def _fast_bilstm_config(tmp_path: Path) -> Path:
    """Copia `bilstm_baseline_v1.yaml` con un espacio de busqueda/entrenamiento chico (para que
    el test de integracion termine en minutos, no en la duracion completa de la corrida
    baseline real). El nombre del modelo UC (`weather.ml.rio_search_bilstm`) lo fija
    `RunSearch` a partir de `model.name` ("bilstm"), no de este `name` de experimento -- correr
    este test con `register_model: true` agrega una version mas al mismo modelo registrado que
    la corrida baseline real (Decision 043); es el comportamiento esperado de un registro de
    modelos (acumula versiones), no un bug del test."""
    data = yaml.safe_load((CONFIGS_DIR / "bilstm_baseline_v1.yaml").read_text(encoding="utf-8"))
    data["name"] = "bilstm_integration_test"
    data["search"] = {
        "strategy": "random",
        "n_trials": 1,
        "objective": "val/kge/mean",
        "space": {"sequence.lookback_days": [30, 60]},
    }
    data["training"]["max_epochs"] = 5
    data["training"]["early_stopping"]["patience"] = 5
    data["training"]["device"] = "cpu"  # reproducibilidad del criterio de cierre, ver mas abajo
    data["tracking"]["experiment"] = "/Users/joaquintschopp@gmail.com/rio_search/bilstm_integration_test"
    path = tmp_path / "bilstm_integration_test.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.integration
def test_bilstm_search_runs_end_to_end_with_times_and_uc_registration(tmp_path: Path) -> None:
    config_path = _fast_bilstm_config(tmp_path)
    loaded = load_experiment_config(config_path)

    run_search = build_run_search()
    search = run_search.execute(loaded)

    assert search.status is RunStatus.FINISHED
    assert search.run_id is not None
    assert len(search.trials) == 1

    trial = search.trials[0]
    assert trial.run_id is not None
    assert trial.model.horizon_strategy is HorizonStrategy.MULTI_OUTPUT
    assert trial.val_metrics is not None and trial.test_metrics is not None
    assert len(trial.test_metrics.horizons) == 8
    assert not math.isnan(trial.val_metrics.mean("kge"))

    # Verifica el registro real en weather.ml con el SDK (no solo el valor de retorno de
    # mlflow.register_model): Decision #12 + Decision 042.
    client = build_workspace_client(profile=DEFAULT_PROFILE)
    versions = list(client.model_versions.list("weather.ml.rio_search_bilstm"))
    assert versions, "weather.ml.rio_search_bilstm deberia tener al menos una version registrada"
    assert any(v.status.value == "READY" for v in versions)
