"""`MlflowDatabricksTracking` (Fase 2, docs/rio_search_plan.md §3.5): implementa
`application.ports.tracking.TrackingPort` sobre `mlflow-skinny` + `databricks-sdk`
(Decision #1). Precedente directo: `infrastructure.tracking.smoke` (Fase 0) verifico contra
Databricks real que este mismo patron (tags/params/metricas/artefactos/`MetaDataset`) funciona
sin pandas; este modulo lo generaliza a la jerarquia de runs busqueda -> trial (-> horizonte,
Fase 3) via `nested=True` en vez de un unico run plano.

Nota (Decision 039): esta clase no loguea modelos con `mlflow.pytorch.log_model` -- ningun
metodo de este puerto lo hace. Los adaptadores de modelo (Fase 2: naive; Fase 3: `bilstm`)
serializan su propio estado (`ModelAdapterPort.save`) y `RunSearch` sube ese directorio con
`log_artifact_dir`, igual que cualquier otro artefacto.
"""

from __future__ import annotations

import posixpath
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import mlflow
from mlflow.data.meta_dataset import MetaDataset
from mlflow.data.uc_volume_dataset_source import UCVolumeDatasetSource

from rio_search.application.ports.tracking import RunHandle
from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE, build_workspace_client

TAG_PREFIX = "rio_search."


class MlflowDatabricksTracking:
    """Implementa `application.ports.tracking.TrackingPort`."""

    def __init__(self, profile: str = DEFAULT_PROFILE) -> None:
        self._profile = profile
        self._tracking_uri = f"databricks://{profile}"
        mlflow.set_tracking_uri(self._tracking_uri)

    @contextmanager
    def start_run(self, experiment_path: str, run_name: str, nested: bool = False) -> Iterator[RunHandle]:
        if not nested:
            # `mlflow.set_experiment` no crea el directorio padre del workspace (a diferencia
            # de una carpeta comun, Fase 0): se crea una vez, sin efecto si ya existe.
            workspace_parent = posixpath.dirname(experiment_path)
            build_workspace_client(profile=self._profile).workspace.mkdirs(workspace_parent)
            mlflow.set_experiment(experiment_path)
        run = mlflow.start_run(run_name=run_name, nested=nested)
        try:
            yield RunHandle(run_id=run.info.run_id, experiment_id=run.info.experiment_id)
        finally:
            mlflow.end_run()

    def set_tags(self, tags: dict[str, str]) -> None:
        mlflow.set_tags({f"{TAG_PREFIX}{k}": v for k, v in tags.items()})

    def log_params(self, params: dict[str, Any]) -> None:
        if params:
            mlflow.log_params(params)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        if metrics:
            mlflow.log_metrics(metrics, step=step)

    def log_artifact_dir(self, local_dir: Path, artifact_path: str) -> None:
        mlflow.log_artifacts(str(local_dir), artifact_path=artifact_path)

    def log_meta_dataset(self, name: str, digest: str, source_path: str, context: str) -> None:
        meta_dataset = MetaDataset(source=UCVolumeDatasetSource(path=source_path), name=name, digest=digest)
        mlflow.log_input(meta_dataset, context=context)
