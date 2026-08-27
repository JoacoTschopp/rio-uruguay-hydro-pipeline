"""CLI `rio-search` (§4.2, docs/rio_search_plan.md). Fase 0 cableo los comandos base
(`databricks init-schema`, `datasets refresh`, `api serve`, `mlflow smoke`); la Fase 1 conecta
`datasets describe` a `DescribeDataset` real (cobertura por columna/año/split, §5). El resto
del contrato de §4.2 (`search run`, `champions set`, `predict run`, `research …`,
`thesis export`) llega con sus fases."""

from __future__ import annotations

import sys
from pathlib import Path

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

search_app = typer.Typer(help="Corridas de busqueda (Fase 2, §4.2, §5).")
app.add_typer(search_app, name="search")

champions_app = typer.Typer(help="Campeon vigente por target (Fase 6, Decision #12, §4.2).")
app.add_typer(champions_app, name="champions")

predict_app = typer.Typer(help="Inferencia diaria del campeon (Fase 6, §3.8, §4.2).")
app.add_typer(predict_app, name="predict")


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
    experiment: Path = typer.Option(
        None,
        "--experiment",
        help=(
            "YAML de configs/experiments/ del que se toman target/horizontes/split/grupos "
            "de features (default: bilstm_baseline_v1.yaml, §4.1). Sin este archivo cae al "
            "resumen simple de la Fase 0 (version, filas, rango, columnas)."
        ),
    ),
    mode: str = typer.Option(
        "offline", help="ensure_latest | volume_as_is | offline (§3.6); default offline: usa el cache."
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks."),
    warehouse_id: str = typer.Option(DEFAULT_WAREHOUSE_ID, help="Warehouse SQL serverless."),
) -> None:
    """Cobertura por columna/año/split (Fase 1, §5) para la config de experimento pedida;
    sin `--experiment` (o si no existe ningun YAML en configs/experiments/) imprime el
    resumen simple del snapshot que ya daba la Fase 0."""
    from rio_search.infrastructure.datasets.experiment_yaml import load_dataset_describe_config
    from rio_search.interfaces.container import (
        DEFAULT_EXPERIMENTS_DIR,
        build_feature_catalog,
        build_gold_parquet_repository,
    )

    experiment_path = experiment or (DEFAULT_EXPERIMENTS_DIR / "bilstm_baseline_v1.yaml")
    repository = build_gold_parquet_repository(profile=profile, warehouse_id=warehouse_id)
    dataset_version, df = repository.load(mode=mode)  # type: ignore[arg-type]

    if not experiment_path.exists():
        typer.echo(f"(sin config de experimento en {experiment_path}; resumen simple)")
        typer.echo(f"delta_version: {dataset_version.delta_version}")
        typer.echo(f"rows: {dataset_version.rows}")
        typer.echo(f"fecha: {dataset_version.fecha_min} -> {dataset_version.fecha_max}")
        typer.echo(f"columns ({len(dataset_version.columns)}): {', '.join(dataset_version.columns)}")
        return

    from rio_search.application.datasets.describe_dataset import DescribeDataset

    config = load_dataset_describe_config(experiment_path)
    catalog = build_feature_catalog()
    target_columns = list(config.target.target_columns(config.horizons))
    feature_columns = list(catalog.columns_for(config.feature_groups))
    columns = tuple(dict.fromkeys(feature_columns + target_columns))

    coverage = DescribeDataset().execute(
        dataset_version=dataset_version,
        df=df,
        split_policy=config.split_policy,
        horizons=config.horizons,
        columns=columns,
    )

    typer.echo(f"experimento: {config.name} ({experiment_path})")
    typer.echo(f"dataset: delta_version={dataset_version.delta_version} rows={dataset_version.rows}")
    typer.echo(f"target: {config.target.value} horizontes: {list(config.horizons)}")
    typer.echo(f"grupos de features: {list(config.feature_groups)} ({len(feature_columns)} columnas)")
    typer.echo(f"split: {config.split_policy.policy} anchor={coverage.split.anchor}")
    typer.echo("")

    for split_coverage in coverage.splits:
        typer.echo(
            f"[{split_coverage.name}] {split_coverage.date_range} "
            f"({split_coverage.date_range.days} dias, {split_coverage.rows} filas)"
        )
        for column_coverage in split_coverage.columns:
            typer.echo(
                f"    {column_coverage.column:<55} "
                f"{column_coverage.non_null_pct:6.2f}% "
                f"({column_coverage.non_null_rows}/{column_coverage.rows})"
            )
        typer.echo("")


@search_app.command("run")
def search_run(
    config: Path = typer.Argument(..., help="YAML de configs/experiments/ (§4.1)."),
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks / MLflow."),
    warehouse_id: str = typer.Option(DEFAULT_WAREHOUSE_ID, help="Warehouse SQL serverless."),
) -> None:
    """Corre una busqueda completa (Fase 2, §3.2, §5): `RefreshDataset` + un trial por modelo
    naive (`persistence`/`climatology`/`seasonal_naive`), logueado en MLflow con la jerarquia
    busqueda -> trial."""
    from rio_search.infrastructure.experiments.experiment_config_loader import load_experiment_config
    from rio_search.interfaces.container import build_run_search

    loaded = load_experiment_config(config)
    run_search = build_run_search(profile=profile, warehouse_id=warehouse_id)
    search = run_search.execute(loaded)

    typer.echo(
        f"search_run_id={search.run_id} experiment={search.experiment_path} trials={len(search.trials)}"
    )
    for trial in search.trials:
        skill_h01 = None
        if trial.test_metrics is not None:
            try:
                skill_h01 = trial.test_metrics.horizon(1).get("skill_vs_persistence")
            except KeyError:
                skill_h01 = None
        typer.echo(
            f"  trial={trial.name} run_id={trial.run_id} status={trial.status.value} "
            f"test/skill_vs_persistence/h01={skill_h01}"
        )


@champions_app.command("set")
def champions_set(
    run_id: str = typer.Option(..., "--run", help="run_id de MLflow (Databricks) del trial a promover."),
    target: str = typer.Option("caudal", help="caudal | nivel."),
    metric_name: str = typer.Option(
        "val/kge/mean", "--metric", help="Metrica de seleccion sobre VAL (§3.7: nunca TEST)."
    ),
    note: str = typer.Option(
        None,
        "--note",
        help="Nota libre (p. ej. 'campeon provisorio, pendiente de revision del usuario', §8).",
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks / MLflow."),
) -> None:
    """`PromoteChampion` (Fase 6, Decision #12, §3.5, §4.2): fija el alias
    `champion_<target>` en Unity Catalog y la copia local en SQLite."""
    from rio_search.domain.shared.target_variable import TargetVariable
    from rio_search.interfaces.container import build_promote_champion

    promote = build_promote_champion(profile=profile)
    champion = promote.execute(
        run_id=run_id, target=TargetVariable(target), metric_name=metric_name, note=note
    )
    typer.echo(
        f"campeon target={champion.target.value} run_id={champion.run_id} model={champion.model_name} "
        f"{champion.metric_name}={champion.metric_value:.4f}"
    )
    if champion.registered_model_name:
        typer.echo(
            f"  alias champion_{champion.target.value} -> {champion.registered_model_name} "
            f"v{champion.registered_model_version}"
        )
    if champion.note:
        typer.echo(f"  nota: {champion.note}")


@predict_app.command("run")
def predict_run(
    target: str = typer.Option("caudal", help="caudal | nivel."),
    as_of: str = typer.Option(
        None, "--as-of", help="YYYY-MM-DD; default: resuelto por AsOfPolicy (§3.8 paso 3)."
    ),
    device: str = typer.Option("auto", help="auto | cuda | mps | cpu (Decision #6, tambien en inferencia)."),
    publish: bool = typer.Option(
        False, "--publish", help="Publica el parquet en el Volume (§3.8 paso 5)."
    ),
    profile: str = typer.Option(DEFAULT_PROFILE, help="Perfil de la CLI de Databricks / MLflow."),
    warehouse_id: str = typer.Option(DEFAULT_WAREHOUSE_ID, help="Warehouse SQL serverless."),
) -> None:
    """`IssueDailyForecast` (Fase 6, §3.8): protocolo completo de inferencia diaria -- mismo
    comando que corre el Task Scheduler a las 06:30 Montevideo (`scheduler/register_tasks.ps1`).

    Toma el mismo `ProcessLock` de archivo que `SubprocessJobRunner`/`rio-search search run`
    (Decision 044, docs/decisions.md): la tarea diaria y una busqueda lanzada a mano (o desde la
    API) nunca le pegan a Databricks/MLflow al mismo tiempo con el mismo perfil de CLI."""
    from datetime import date as _date

    from rio_search.domain.shared.target_variable import TargetVariable
    from rio_search.infrastructure.jobs.process_lock import ProcessLock
    from rio_search.interfaces.container import DEFAULT_JOB_LOCK_PATH, build_issue_daily_forecast

    lock = ProcessLock(DEFAULT_JOB_LOCK_PATH)
    lock.acquire_blocking(label="predict_run", poll_seconds=2.0, timeout_seconds=None)
    try:
        issue = build_issue_daily_forecast(profile=profile, warehouse_id=warehouse_id)
        as_of_override = _date.fromisoformat(as_of) if as_of else None
        forecast = issue.execute(
            target=TargetVariable(target),
            as_of_override=as_of_override,
            device_preferred=device,
            publish=publish,
        )
    finally:
        lock.release()

    typer.echo(
        f"forecast_run_id={forecast.forecast_run_id} as_of={forecast.as_of} "
        f"data_lag_days={forecast.data_lag_days} device={forecast.device_type} "
        f"dataset_delta_version={forecast.dataset_delta_version} champion_run_id={forecast.champion_run_id}"
    )
    for point in sorted(forecast.points, key=lambda p: p.horizon):
        typer.echo(f"  t+{point.horizon:02d} ({point.target_date}): {point.value:.2f}")
    if forecast.published_path:
        typer.echo(f"  publicado en {forecast.published_path}")


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
