"""`MlflowModelAlias` (Fase 6, Decision #12, docs/rio_search_plan.md §3.5): implementa
`application.ports.model_alias.ModelAliasPort` sobre `MlflowClient.set_registered_model_alias`
sobre Unity Catalog (`registry_uri=databricks-uc`, mismo registro que
`infrastructure.tracking.mlflow_databricks.MlflowDatabricksTracking.register_model`, Fase 3)."""

from __future__ import annotations

from mlflow.tracking import MlflowClient

from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE


class MlflowModelAlias:
    """Implementa `application.ports.model_alias.ModelAliasPort`."""

    def __init__(self, profile: str = DEFAULT_PROFILE) -> None:
        self._client = MlflowClient(tracking_uri=f"databricks://{profile}", registry_uri="databricks-uc")

    def set_alias(self, name: str, alias: str, version: str) -> None:
        self._client.set_registered_model_alias(name=name, alias=alias, version=version)
