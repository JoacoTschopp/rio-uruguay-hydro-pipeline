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

`register_model` (Fase 3, Decision #12, Decision 042 -- docs/decisions.md): registro en Unity
Catalog via `mlflow.set_registry_uri("databricks-uc")` + `mlflow.register_model(model_uri, name)`.
Dos hallazgos reales contra Databricks (Decision 042):

1. UC **exige** un `MLmodel` con `signature` (inputs+outputs) para registrar cualquier version,
   incluso sin usar el modelo para *serving* -- `register_model` (punto 1 de esta Decision)
   escribe un `MLmodel` minimo (`flavors={}`, sin pyfunc) con una `signature` de tensores
   (`TensorSpec`, `mlflow.types.schema`, sin pandas) y lo sube al mismo `artifact_path` ya
   logueado.
2. El propio cliente de UC (`UcModelRegistryRestStore._load_model`, corre **local**, antes de
   llamar a la API) hace `Model.load(...)` para validar ese `MLmodel` -- y `Model.from_dict()`
   importa **incondicionalmente** `mlflow.models.signature`, que a su vez importa `pandas` en
   el top-level (mismo patron que `mlflow.pytorch`, Decision 039, pero mas profundo: pasa
   *siempre* que se registra un modelo, no solo si se usa el flavor de alto nivel). Sin pandas
   instalado (Decision #9) esa validacion local truena con `ModuleNotFoundError` antes de llegar
   siquiera a la red. Se aisla con un `sys.modules["pandas"]` temporal (`unittest.mock.MagicMock`,
   nunca pandas real) durante la ventana exacta de `mlflow.register_model(...)`, restaurado en
   `finally` -- exactamente lo que permite la propia Decision #9 ("si una dependencia lo
   necesita, aislarla, nunca importarlo desde rio_search"): la resolucion de `pd.Series`/etc. es
   solo un chequeo de anotaciones de tipo en el codigo de `mlflow.types.utils`, nunca se invoca
   pandas real en el camino de `ModelSignature.from_dict()`/`Schema.from_json()` que este metodo
   ejercita. Verificado con `test_no_pandas_in_env`/`test_pandas_import_actually_fails` en verde
   despues de una corrida real que registro un modelo (el stub no deja rastro en `sys.modules`).
"""

from __future__ import annotations

import posixpath
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

import mlflow
import numpy as np
from mlflow.data.meta_dataset import MetaDataset
from mlflow.data.uc_volume_dataset_source import UCVolumeDatasetSource
from mlflow.models.model import Model
from mlflow.types.schema import Schema, TensorSpec

from rio_search.application.ports.tracking import RunHandle
from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE, build_workspace_client

TAG_PREFIX = "rio_search."


class _TensorSignatureStub:
    """Duck-type de `mlflow.models.signature.ModelSignature.to_dict()` (Decision 042): la
    clase real no se puede importar (su modulo hace `import pandas` en el top-level); esta
    replica exactamente el mismo formato de salida (`{"inputs": <json>, "outputs": <json>,
    "params": None}`, ver `mlflow/models/signature.py::ModelSignature.to_dict`) usando solo
    `mlflow.types.schema.Schema`/`TensorSpec` (confirmado sin dependencia de pandas)."""

    def __init__(self) -> None:
        # `Model.to_dict()` lee estos dos atributos privados de `self.signature` ademas de
        # `to_dict()` -- ver `mlflow/models/model.py::Model.to_dict`.
        self._is_signature_from_type_hint = False
        self._is_type_hint_from_example = False

    def to_dict(self) -> dict[str, Any]:
        inputs = Schema([TensorSpec(np.dtype(np.float32), (-1, -1, -1), name="X")])
        outputs = Schema([TensorSpec(np.dtype(np.float64), (-1, -1), name="y_pred")])
        return {"inputs": inputs.to_json(), "outputs": outputs.to_json(), "params": None}


@contextmanager
def _pandas_import_stub() -> Iterator[None]:
    """Ventana minima donde `sys.modules["pandas"]` existe como `MagicMock` (Decision 042):
    solo mientras dura `mlflow.register_model(...)`, nunca mas. No es pandas real ni lo
    instala como dependencia (`pyproject.toml` sigue sin `pandas`, Decision #9); revierte el
    estado exacto de antes (no toca `sys.modules` si pandas ya estaba presente, lo cual nunca
    pasa en este entorno -- defensivo)."""
    already_present = "pandas" in sys.modules
    if not already_present:
        sys.modules["pandas"] = mock.MagicMock(name="rio_search_pandas_stub_for_uc_registration")
    try:
        yield
    finally:
        if not already_present:
            sys.modules.pop("pandas", None)


class MlflowDatabricksTracking:
    """Implementa `application.ports.tracking.TrackingPort`."""

    def __init__(self, profile: str = DEFAULT_PROFILE) -> None:
        self._profile = profile
        self._tracking_uri = f"databricks://{profile}"
        mlflow.set_tracking_uri(self._tracking_uri)
        mlflow.set_registry_uri("databricks-uc")

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

    def register_model(self, run_id: str, artifact_path: str, name: str) -> str:
        # UC exige un `MLmodel` con signature en el mismo `artifact_path` ya subido (Decision
        # 042, punto 1): se agrega ahora, no en `ModelAdapterPort.save()` -- el adaptador no
        # sabe (ni deberia saber) si esta corrida va a registrar en UC.
        with tempfile.TemporaryDirectory() as tmp:
            mlmodel_path = Path(tmp) / "MLmodel"
            model = Model(
                artifact_path=artifact_path, run_id=run_id, flavors={}, signature=_TensorSignatureStub()
            )
            model.save(str(mlmodel_path))
            mlflow.log_artifact(str(mlmodel_path), artifact_path=artifact_path)

        model_uri = f"runs:/{run_id}/{artifact_path}"
        with _pandas_import_stub():
            result = mlflow.register_model(model_uri=model_uri, name=name)
        return str(result.version)
