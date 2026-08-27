"""CLI `rio-search` (§4.2, docs/rio_search_plan.md). Fase 0 solo cablea los comandos que
esa fase necesita (`databricks init-schema`, `datasets refresh`, `api serve`, y `mlflow smoke`
como utilidad para verificar conectividad); el resto del contrato de §4.2 (`datasets describe`
con filtros, `search run`, `champions set`, `predict run`, `research …`, `thesis export`)
llega con sus fases."""

from __future__ import annotations

import sys

import typer

from rio_search.application.ports.snapshot_sync import RefreshMode
from rio_search.infrastructure.databricks.sdk_client import (
    DEFAULT_PROFILE,
    DEFAULT_WAREHOUSE_ID,
    DatabricksStatementExecutor,
    build_workspace_client,
    create_schema_if_not_exists,
)

# mlflow imprime iconos unicode (p. ej. al terminar un run) que la consola de Windows en
# cp1252 no puede codificar y tira UnicodeEncodeError; forzar utf-8 en stdout/stderr evita
# que un simple mensaje informativo tumbe el comando.
for _stream in (sys.stdout, sys.stderr):
    if getattr(_stream, "encoding", "").lower() != "utf-8":
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

app = typer.Typer(
    help="rio-search: banco de pruebas para la metodologia que mejor proyecta el caudal del Rio Uruguay."
)

databricks_app = typer.Typer(help="Operaciones directas sobre Databricks (Statement API, schema UC).")
app.add_typer(databricks_app, name="databricks")

mlflow_app = typer.Typer(help="Conectividad MLflow (tracking en Databricks, Decision #1).")
app.add_typer(mlflow_app, name="mlflow")

api_app = typer.Typer(help="Backend FastAPI.")
app.add_typer(api_app, name="api")

datasets_app = typer.Typer(help="Snapshot del dataset Gold (Decision #10, §3.6).")
app.add_typer(datasets_app, name="datasets")


@databricks_app.command("init-schema")
def init_schema(
    schema: str = typer.Option("weather.ml", help="Schema Unity Catalog (Decision #12)."),
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks (~/.databrickscfg)."),
    warehouse_id: str = typer.Option(DEFAULT_WAREHOUSE_ID, help="Warehouse SQL serverless."),
) -> None:
    """`CREATE SCHEMA IF NOT EXISTS <schema>` (idempotente, Decision #12, Fase 0)."""
    client = build_workspace_client(profile=profile)
    statements = DatabricksStatementExecutor(client, warehouse_id=warehouse_id)
    create_schema_if_not_exists(statements, schema=schema)
    typer.echo(f"Schema '{schema}' listo (CREATE SCHEMA IF NOT EXISTS).")


@mlflow_app.command("smoke")
def mlflow_smoke(
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks / MLflow."),
) -> None:
    """Run `smoke` en `/Users/<profile>/rio_search/smoke`: tags, tiempos, procedencia,
    MetaDataset y modelo de juguete (Fase 0, verifica mlflow-skinny sin pandas)."""
    from rio_search.infrastructure.tracking.smoke import run_smoke

    result = run_smoke(profile=profile, log=typer.echo)
    typer.echo(f"run_id={result.run_id} experiment={result.experiment_path}")


@datasets_app.command("refresh")
def datasets_refresh(
    mode: RefreshMode = typer.Option("ensure_latest", help="ensure_latest | volume_as_is | offline (§3.6)."),
    force: bool = typer.Option(False, help="Forzar re-descarga del parquet aunque la version no cambie."),
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks."),
    warehouse_id: str = typer.Option(DEFAULT_WAREHOUSE_ID, help="Warehouse SQL serverless."),
) -> None:
    """Protocolo de frescura completo (Decision #10, §3.6): version Delta de Gold -> manifest
    -> dispara `Export_Gold_Snapshot` si esta atras -> descarga y verifica `sha256`."""
    from rio_search.interfaces.container import build_gold_snapshot_sync

    sync = build_gold_snapshot_sync(profile=profile, warehouse_id=warehouse_id)
    dataset_version, path = sync.refresh(mode=mode, force=force)
    typer.echo(
        f"delta_version={dataset_version.delta_version} columns={len(dataset_version.columns)} "
        f"rows={dataset_version.rows} sha256={dataset_version.sha256[:12]}... path={path}"
    )


@datasets_app.command("describe")
def datasets_describe(
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks."),
    warehouse_id: str = typer.Option(DEFAULT_WAREHOUSE_ID, help="Warehouse SQL serverless."),
) -> None:
    """Resumen del snapshot en cache (version, filas, rango de fechas, columnas). La
    cobertura por columna/anio/split (Fase 1) todavia no esta implementada."""
    from rio_search.interfaces.container import build_gold_snapshot_sync

    sync = build_gold_snapshot_sync(profile=profile, warehouse_id=warehouse_id)
    dataset_version, path = sync.refresh(mode="offline")
    typer.echo(f"delta_version: {dataset_version.delta_version}")
    typer.echo(f"rows: {dataset_version.rows}")
    typer.echo(f"fecha: {dataset_version.fecha_min} -> {dataset_version.fecha_max}")
    typer.echo(f"columns ({len(dataset_version.columns)}): {', '.join(dataset_version.columns)}")
    typer.echo(f"parquet: {path}")


@api_app.command("serve")
def api_serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Levanta el backend FastAPI (`GET /api/health` en Fase 0)."""
    import uvicorn

    uvicorn.run("rio_search.interfaces.api.main:create_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    app()
