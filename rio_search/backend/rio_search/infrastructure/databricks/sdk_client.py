"""Adaptadores reales sobre `databricks-sdk`: Statement API (warehouse serverless), descarga
de archivos del Volume y `jobs submit` de un run ad hoc (docs/rio_search_plan.md §2.3, §3.6).

Sin secretos en git: usa el perfil ya autenticado del CLI de Databricks (`~/.databrickscfg`),
igual que `notebooks_local/*/sync_to_databricks.py`.
"""

from __future__ import annotations

import io
import time
from datetime import timedelta
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs as sdk_jobs
from databricks.sdk.service import sql as sdk_sql

DEFAULT_PROFILE = "joaquintschopp@gmail.com"
DEFAULT_WAREHOUSE_ID = "d8aaafcf1fdb6645"  # warehouse serverless (docs/rio_search_plan.md §2.2)

_PENDING_STATES = (sdk_sql.StatementState.PENDING, sdk_sql.StatementState.RUNNING)


def build_workspace_client(profile: str = DEFAULT_PROFILE) -> WorkspaceClient:
    """Cliente autenticado con el perfil del CLI ya validado; no requiere tokens en el repo."""
    return WorkspaceClient(profile=profile)


class DatabricksStatementExecutor:
    """Ejecuta SQL contra el warehouse serverless via la Statement Execution API y devuelve
    filas como `list[dict]` (nombre de columna -> valor, siempre `str` o `None`)."""

    def __init__(
        self,
        client: WorkspaceClient,
        warehouse_id: str = DEFAULT_WAREHOUSE_ID,
        poll_interval_s: float = 1.0,
        timeout_s: float = 120.0,
    ) -> None:
        self._client = client
        self._warehouse_id = warehouse_id
        self._poll_interval_s = poll_interval_s
        self._timeout_s = timeout_s

    def execute(self, statement: str) -> list[dict[str, Any]]:
        response = self._client.statement_execution.execute_statement(
            statement=statement, warehouse_id=self._warehouse_id, wait_timeout="30s"
        )
        response = self._await_completion(response)
        if response.status is None or response.status.state != sdk_sql.StatementState.SUCCEEDED:
            state = response.status.state if response.status else None
            error = response.status.error if response.status else None
            raise RuntimeError(f"Statement fallo ({state}): {error}\n---\n{statement}")
        if response.result is None or response.manifest is None or response.manifest.schema is None:
            return []
        columns = [c.name for c in (response.manifest.schema.columns or [])]
        rows = response.result.data_array or []
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def _await_completion(self, response: sdk_sql.StatementResponse) -> sdk_sql.StatementResponse:
        deadline = time.monotonic() + self._timeout_s
        while response.status is not None and response.status.state in _PENDING_STATES:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Statement {response.statement_id} no termino en {self._timeout_s}s")
            time.sleep(self._poll_interval_s)
            response = self._client.statement_execution.get_statement(response.statement_id)
        return response


class DatabricksGoldCatalog:
    """Implementa `application.ports.gold_catalog.GoldCatalogPort`."""

    def __init__(self, statements: DatabricksStatementExecutor) -> None:
        self._statements = statements

    def current_delta_version(self, table: str) -> int:
        rows = self._statements.execute(f"DESCRIBE HISTORY {table} LIMIT 1")
        if not rows:
            raise RuntimeError(f"DESCRIBE HISTORY {table} no devolvio filas")
        return int(rows[0]["version"])


class DatabricksVolumeFiles:
    """Descarga/sube archivos de un Unity Catalog Volume via la Files API (`/Volumes/...`)."""

    def __init__(self, client: WorkspaceClient) -> None:
        self._client = client

    def download(self, path: str) -> bytes:
        response = self._client.files.download(path)
        return response.contents.read()

    def upload(self, path: str, contents: bytes, overwrite: bool = True) -> None:
        """Sube `contents` a `path` (`/Volumes/...`, Fase 6 -- `--publish` de
        `rio-search predict run`, docs/rio_search_plan.md §3.8 paso 5)."""
        self._client.files.upload(path, io.BytesIO(contents), overwrite=overwrite)


class DatabricksJobSubmitter:
    """Dispara un run ad hoc (`jobs submit`, no un job registrado) y espera a que termine."""

    def __init__(self, client: WorkspaceClient, timeout_s: float = 1800.0) -> None:
        self._client = client
        self._timeout_s = timeout_s

    def submit_notebook(self, notebook_path: str, run_name: str) -> None:
        waiter = self._client.jobs.submit(
            run_name=run_name,
            tasks=[
                sdk_jobs.SubmitTask(
                    task_key="run",
                    notebook_task=sdk_jobs.NotebookTask(
                        notebook_path=notebook_path, source=sdk_jobs.Source.WORKSPACE
                    ),
                )
            ],
        )
        run = waiter.result(timeout=timedelta(seconds=self._timeout_s))
        result_state = run.state.result_state if run.state else None
        if result_state != sdk_jobs.RunResultState.SUCCESS:
            life_cycle = run.state.life_cycle_state if run.state else None
            message = run.state.state_message if run.state else None
            raise RuntimeError(
                f"Run ad hoc de {notebook_path} termino en life_cycle={life_cycle} "
                f"result={result_state}: {message}"
            )


def create_schema_if_not_exists(statements: DatabricksStatementExecutor, schema: str = "weather.ml") -> None:
    """`CREATE SCHEMA IF NOT EXISTS weather.ml` (Decision #12): idempotente, se puede
    correr repetidas veces sin efecto una vez que el schema existe."""
    statements.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
