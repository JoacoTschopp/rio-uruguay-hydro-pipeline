"""Run `smoke`: verifica que `mlflow-skinny` alcanza sin pandas (Decision #9, Fase 0 del
plan) para tags, tiempos (§3.12), procedencia (§3.13), `MetaDataset` (§3.5) y un modelo de
PyTorch de juguete.

Hallazgo real de esta fase (a documentar en `decisions.md`, no en el plan): `mlflow.pytorch`
(el flavor de alto nivel, `mlflow.pytorch.log_model`) hace `import pandas as pd` en el
top-level de `mlflow/pytorch/__init__.py` (mlflow 3.15.2 / mlflow-skinny) — importar ese
submodulo sin pandas instalado falla con `ModuleNotFoundError`. Por eso el modelo de juguete
NO se loguea con `mlflow.pytorch.log_model`: se guarda el `state_dict` con `torch.save` y se
sube como artefacto plano (`model/model_state_dict.pth` + `model/README.md`). La Fase 3
(BiLSTM real) debe adoptar el mismo patron para el `ModelAdapterPort.save`/`load` (§3.3) en
vez de la API de alto nivel de `mlflow.pytorch`, salvo que una version futura de mlflow lo
corrija.
"""

from __future__ import annotations

import io
import json
import posixpath
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mlflow
import torch
from mlflow.data.meta_dataset import MetaDataset
from mlflow.data.uc_volume_dataset_source import UCVolumeDatasetSource

from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE, build_workspace_client
from rio_search.infrastructure.device.torch_device_resolver import TorchDeviceResolver
from rio_search.infrastructure.provenance.git_provenance import GitProvenance
from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch

EXPERIMENT_PATH_TEMPLATE = "/Users/{profile}/rio_search/smoke"
VOLUME_PARQUET = "/Volumes/weather/raw/gold_export_volume/training_dataset_v0.parquet"
TAG_PREFIX = "rio_search."
# .../backend/rio_search/infrastructure/tracking/smoke.py -> .../backend/rio_search (raiz del paquete)
PACKAGE_DIR = Path(__file__).resolve().parents[2]


class _ToyModel(torch.nn.Module):
    """Modelo minimo, solo para ejercitar el camino de logueo; no es el BiLSTM (Fase 3)."""

    def __init__(self, in_features: int = 4, out_features: int = 1) -> None:
        super().__init__()
        self.linear = torch.nn.Linear(in_features, out_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x)


@dataclass
class SmokeResult:
    run_id: str
    experiment_id: str
    experiment_path: str
    tracking_uri: str


def _prefixed(tags: dict[str, str]) -> dict[str, str]:
    return {f"{TAG_PREFIX}{k}": v for k, v in tags.items()}


def _zip_package(package_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in package_dir.rglob("*.py"):
            zf.write(path, arcname=str(path.relative_to(package_dir.parent)))
    return buffer.getvalue()


def run_smoke(profile: str = DEFAULT_PROFILE, log: Any = print) -> SmokeResult:
    tracking_uri = f"databricks://{profile}"
    mlflow.set_tracking_uri(tracking_uri)
    experiment_path = EXPERIMENT_PATH_TEMPLATE.format(profile=profile)

    # `mlflow.set_experiment` no crea el directorio padre del workspace (a diferencia de
    # una carpeta comun): si `/Users/<profile>/rio_search/` todavia no existe, la creacion
    # del experimento falla con NOT_FOUND. Se crea una vez, sin efecto si ya existe.
    # posixpath, no pathlib: los paths de workspace de Databricks son siempre `/`, incluso
    # en Windows (pathlib.Path los normalizaria con `\`).
    workspace_parent = posixpath.dirname(experiment_path)
    build_workspace_client(profile=profile).workspace.mkdirs(workspace_parent)

    mlflow.set_experiment(experiment_path)

    stopwatch = PerfCounterStopwatch(cuda_sync=False)
    device = TorchDeviceResolver().resolve(preferred="auto")
    provenance = GitProvenance().capture()

    started_at = datetime.now(timezone.utc)
    run_name = f"smoke__{started_at.strftime('%Y%m%d-%H%M')}"

    run = mlflow.start_run(run_name=run_name)
    try:
        log(f"Run smoke iniciado: {run.info.run_id} en {experiment_path}")
        run_id = run.info.run_id
        experiment_id = run.info.experiment_id

        with stopwatch.track("total_s"):
            tags = _prefixed(
                {
                    **device.as_tags(),
                    **provenance.as_tags(),
                    "started_at": started_at.isoformat(),
                }
            )
            mlflow.set_tags(tags)

            mlflow.log_param("rio_search.smoke.example_param", "fase_0")
            mlflow.log_metric("smoke/example_metric", 1.0)

            # --- MetaDataset (§3.5): nombre/digest/origen del dataset sin materializarlo ---
            with stopwatch.track("meta_dataset_s"):
                meta_dataset = MetaDataset(
                    source=UCVolumeDatasetSource(path=VOLUME_PARQUET),
                    name="training_dataset_v0",
                    digest="smoke",
                )
                mlflow.log_input(meta_dataset, context="smoke")

            # --- Procedencia (§3.13): patch no commiteado + snapshot del paquete ---
            with stopwatch.track("code_artifact_s"), tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                (tmp_dir / "uncommitted.patch").write_text(provenance.uncommitted_patch, encoding="utf-8")
                package_zip = tmp_dir / "package.zip"
                package_zip.write_bytes(_zip_package(PACKAGE_DIR))
                mlflow.log_artifacts(str(tmp_dir), artifact_path="code")

            # --- Modelo de juguete: sin mlflow.pytorch.log_model (ver docstring del modulo) ---
            with stopwatch.track("model_log_s"), tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                model = _ToyModel()
                torch.save(model.state_dict(), tmp_dir / "model_state_dict.pth")
                (tmp_dir / "README.md").write_text(
                    "Modelo de juguete del run smoke (Fase 0). Guardado con "
                    "torch.save(state_dict()), no con mlflow.pytorch.log_model: ese flavor "
                    "importa pandas en el top-level de mlflow.pytorch (mlflow-skinny 3.15.2) y "
                    "rompe sin pandas instalado (Decision #9). Ver docstring de "
                    "infrastructure/tracking/smoke.py.\n",
                    encoding="utf-8",
                )
                (tmp_dir / "architecture.json").write_text(
                    json.dumps(
                        {"in_features": model.linear.in_features, "out_features": model.linear.out_features}
                    ),
                    encoding="utf-8",
                )
                mlflow.log_artifacts(str(tmp_dir), artifact_path="model")

        # total_s recien queda cerrado aca (el `with` de arriba ya termino); se loguea antes
        # de terminar el run para que quede en el mismo run, junto con el resto de time/*.
        mlflow.log_metrics(stopwatch.as_metrics())
        mlflow.set_tags(_prefixed({"ended_at": datetime.now(timezone.utc).isoformat()}))
    finally:
        mlflow.end_run()

    time_metrics = stopwatch.as_metrics()
    log(f"Run smoke completo: run_id={run_id} tiempos={time_metrics}")
    return SmokeResult(
        run_id=run_id, experiment_id=experiment_id, experiment_path=experiment_path, tracking_uri=tracking_uri
    )


if __name__ == "__main__":
    run_smoke()
