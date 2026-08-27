"""`MlflowDatabricksTrackingReader` (Fase 4, docs/rio_search_plan.md §3.9, §5): implementa
`application.ports.tracking_read.TrackingReadPort` sobre `mlflow.tracking.MlflowClient`
(mlflow-skinny, Decision #9 -- **no** la funcion de modulo `mlflow.search_runs()`, que devuelve
un `pandas.DataFrame` y arrastraria pandas; `MlflowClient.search_runs()` devuelve una
`PagedList[Run]`, sin pandas).

Precedente directo: `infrastructure.tracking.mlflow_databricks.MlflowDatabricksTracking`
(Fase 2) ya probo el mismo `tracking_uri=f"databricks://{profile}"` contra Databricks real. Este
modulo es su contraparte de solo lectura: nunca llama `start_run`/`log_*`.
"""

from __future__ import annotations

from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from rio_search.application.ports.tracking_read import MetricPoint, RunRecord
from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE


def _to_record(run) -> RunRecord:  # noqa: ANN001 - mlflow.entities.Run, no tipado publico estable
    info = run.info
    data = run.data
    return RunRecord(
        run_id=info.run_id,
        experiment_id=info.experiment_id,
        status=str(info.status),
        start_time_ms=info.start_time,
        end_time_ms=info.end_time,
        artifact_uri=info.artifact_uri or "",
        tags=dict(data.tags or {}),
        params=dict(data.params or {}),
        metrics={k: float(v) for k, v in (data.metrics or {}).items()},
    )


class MlflowDatabricksTrackingReader:
    """Implementa `application.ports.tracking_read.TrackingReadPort`."""

    def __init__(self, profile: str = DEFAULT_PROFILE) -> None:
        self._client = MlflowClient(tracking_uri=f"databricks://{profile}")

    def list_runs(self, experiment_names, max_results: int = 500) -> list[RunRecord]:
        records: list[RunRecord] = []
        for name in experiment_names:
            experiment = self._client.get_experiment_by_name(name)
            if experiment is None:
                continue  # experimento todavia no existe (p. ej. daily_forecast antes de Fase 6)
            page = self._client.search_runs(
                [experiment.experiment_id],
                max_results=max_results,
                order_by=["attributes.start_time DESC"],
            )
            records.extend(_to_record(run) for run in page)
        return records

    def get_run(self, run_id: str) -> RunRecord | None:
        try:
            run = self._client.get_run(run_id)
        except MlflowException:
            return None
        return _to_record(run)

    def list_children(
        self, parent_run_id: str, experiment_id: str, max_results: int = 200
    ) -> list[RunRecord]:
        # Backticks: la sintaxis de `filter_string` de MLflow exige escapar claves de tag con
        # puntos (`mlflow.parentRunId`) igual que en SQL con nombres reservados.
        filter_string = f"tags.`mlflow.parentRunId` = '{parent_run_id}'"
        try:
            page = self._client.search_runs(
                [experiment_id], filter_string=filter_string, max_results=max_results
            )
        except MlflowException:
            return []
        return [_to_record(run) for run in page]

    def get_metric_history(self, run_id: str, metric_key: str) -> list[MetricPoint]:
        try:
            history = self._client.get_metric_history(run_id, metric_key)
        except MlflowException:
            return []
        return [MetricPoint(step=m.step, timestamp_ms=m.timestamp, value=float(m.value)) for m in history]
