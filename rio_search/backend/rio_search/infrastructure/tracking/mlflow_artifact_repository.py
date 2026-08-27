"""`MlflowArtifactRepository` (Fase 6, docs/rio_search_plan.md §3.8): implementa
`application.ports.artifact_repository.ArtifactRepositoryPort` sobre
`mlflow.tracking.MlflowClient.download_artifacts` (mlflow-skinny, Decision #9 -- verificado
real contra Databricks: baja archivos sueltos (`split/split.json`) y directorios completos
(`config/`, `features/`, `model/`) sin arrastrar pandas). Mismo `tracking_uri` que
`infrastructure.tracking.mlflow_read.MlflowDatabricksTrackingReader` (Fase 4)."""

from __future__ import annotations

from pathlib import Path

from mlflow.tracking import MlflowClient

from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE


class MlflowArtifactRepository:
    """Implementa `application.ports.artifact_repository.ArtifactRepositoryPort`."""

    def __init__(self, profile: str = DEFAULT_PROFILE) -> None:
        self._client = MlflowClient(tracking_uri=f"databricks://{profile}")

    def download(self, run_id: str, artifact_path: str, dst_dir: Path) -> Path:
        dst_dir.mkdir(parents=True, exist_ok=True)
        local_path = self._client.download_artifacts(run_id, artifact_path, str(dst_dir))
        return Path(local_path)
