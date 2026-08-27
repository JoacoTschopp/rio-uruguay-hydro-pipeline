"""FastAPI de Rio_Search (§3.9, docs/rio_search_plan.md). Fase 0 solo exponia `/api/health`; la
Fase 4 agrega los endpoints de lectura de MLflow (Búsquedas, Run, Comparar, §3.9) y el lanzador
de búsquedas (Lanzar: `POST /api/jobs`, `GET /api/jobs/{id}/log` SSE, §5). Predicciones/Research
quedan para las Fases 6/7 (`PromoteChampion`/`IssueDailyForecast`/`Document` todavia no existen).

`create_app(deps=...)` acepta un `ApiDependencies` inyectado (tests, §5: "TestClient y un
TrackingPort falso") o construye el real via `interfaces.container.build_api_dependencies()`
cuando no recibe ninguno -- necesario porque `uvicorn.run(..., factory=True)` (§4.2, `rio-search
api serve`) llama a la factory sin argumentos.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from rio_search.application.ports.job_runner import JobRecord
from rio_search.application.ports.snapshot_sync import RefreshMode
from rio_search.application.ports.tracking_read import RunRecord
from rio_search.interfaces.api.dependencies import ApiDependencies
from rio_search.interfaces.api.schemas import (
    DatasetOut,
    DatasetVersionOut,
    FeatureCatalogOut,
    FeatureGroupOut,
    JobListOut,
    JobOut,
    JobSubmitIn,
    MetricSeriesOut,
    RunComparisonOut,
    RunDetailOut,
    RunListOut,
    RunOut,
    SearchListOut,
    SearchOut,
)

APP_VERSION = "0.2.0"


def create_app(deps: ApiDependencies | None = None) -> FastAPI:
    if deps is None:
        from rio_search.interfaces.container import build_api_dependencies

        deps = build_api_dependencies()

    app = FastAPI(
        title="rio_search",
        version=APP_VERSION,
        description=(
            "Banco de pruebas de la metodologia que mejor proyecta el caudal del Rio Uruguay "
            "(docs/rio_search_plan.md). Fase 4: lectura de MLflow (Databricks) cacheada en "
            "SQLite + lanzador local de busquedas."
        ),
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "rio_search-backend", "version": APP_VERSION}

    # ------------------------------------------------------------------
    # Búsquedas (§3.9): GET /api/searches, GET /api/runs
    # ------------------------------------------------------------------
    @app.get("/api/searches", response_model=SearchListOut)
    def list_searches(
        families: str | None = Query(
            None, description="Familias separadas por coma (baselines,bilstm,...); default: todas."
        ),
        max_results: int = Query(500, ge=1, le=2000),
    ) -> SearchListOut:
        families_tuple = tuple(f.strip() for f in families.split(",")) if families else None
        results = deps.list_searches.execute(families=families_tuple, max_results=max_results)
        return SearchListOut(
            searches=[
                SearchOut(
                    search=RunOut.model_validate(r.search),
                    trials=[RunOut.model_validate(t) for t in r.trials],
                )
                for r in results
            ]
        )

    @app.get("/api/runs", response_model=RunListOut)
    def list_runs(
        families: str | None = Query(
            None, description="Familias separadas por coma (baselines,bilstm,...); default: todas."
        ),
        max_results: int = Query(500, ge=1, le=2000),
    ) -> RunListOut:
        families_tuple = tuple(f.strip() for f in families.split(",")) if families else None
        records: list[RunRecord] = deps.list_runs.execute(families=families_tuple, max_results=max_results)
        return RunListOut(runs=[RunOut.model_validate(r) for r in records])

    # ------------------------------------------------------------------
    # Run (§3.9): GET /api/runs/{id}, GET /api/runs/{id}/series/{name}
    # ------------------------------------------------------------------
    @app.get("/api/runs/compare", response_model=RunComparisonOut)
    def compare_runs(
        ids: str = Query(..., description="run_id separados por coma, p. ej. ?ids=abc,def"),
    ) -> RunComparisonOut:
        run_ids = [i.strip() for i in ids.split(",") if i.strip()]
        if not run_ids:
            raise HTTPException(status_code=400, detail="ids vacio")
        comparison = deps.compare_runs.execute(run_ids)
        return RunComparisonOut(
            runs=[RunOut.model_validate(r) for r in comparison.runs],
            missing_run_ids=list(comparison.missing_run_ids),
            param_diff=comparison.param_diff,
        )

    @app.get("/api/runs/{run_id}", response_model=RunDetailOut)
    def get_run(run_id: str) -> RunDetailOut:
        detail = deps.get_run_detail.execute(run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"run {run_id!r} no encontrado")
        return RunDetailOut(
            run=RunOut.model_validate(detail.run),
            children=[RunOut.model_validate(c) for c in detail.children],
        )

    @app.get("/api/runs/{run_id}/series/{metric_name:path}", response_model=MetricSeriesOut)
    def get_run_series(run_id: str, metric_name: str) -> MetricSeriesOut:
        # `{metric_name:path}` (no el `str` default de Starlette): las claves de metrica de
        # Rio_Search llevan `/` (`test/rmse/h01`, `time/train_total_s`, §3.5/§3.12) -- el
        # cliente HTTP las manda %-encodeadas pero el decoder de ASGI ya las convierte a `/`
        # crudo antes del ruteo, asi que el segmento por defecto (que corta en `/`) nunca haria
        # match.
        points = deps.reader.get_metric_history(run_id, metric_name)
        return MetricSeriesOut(run_id=run_id, metric=metric_name, points=list(points))

    # ------------------------------------------------------------------
    # Lanzar (§3.9): POST /api/jobs, GET /api/jobs, GET /api/jobs/{id}, GET /api/jobs/{id}/log (SSE)
    # ------------------------------------------------------------------
    @app.post("/api/jobs", response_model=JobOut, status_code=201)
    def submit_job(body: JobSubmitIn) -> JobOut:
        config_path = (deps.experiments_dir / body.config).resolve()
        experiments_dir = deps.experiments_dir.resolve()
        if experiments_dir not in config_path.parents or not config_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"config {body.config!r} no existe en {deps.experiments_dir}",
            )
        record: JobRecord = deps.job_runner.submit(config_path=config_path, label=body.label or body.config)
        return JobOut.model_validate(record)

    @app.get("/api/jobs", response_model=JobListOut)
    def list_jobs() -> JobListOut:
        return JobListOut(jobs=[JobOut.model_validate(j) for j in deps.job_runner.list()])

    @app.get("/api/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str) -> JobOut:
        record = deps.job_runner.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"job {job_id!r} no encontrado")
        return JobOut.model_validate(record)

    @app.get("/api/jobs/{job_id}/log")
    def stream_job_log(job_id: str) -> StreamingResponse:
        if deps.job_runner.get(job_id) is None:
            raise HTTPException(status_code=404, detail=f"job {job_id!r} no encontrado")

        async def event_source():
            loop = asyncio.get_running_loop()
            iterator = deps.job_runner.stream_log(job_id)
            while True:
                try:
                    line = await loop.run_in_executor(None, _next_or_sentinel, iterator)
                except StopIteration:
                    break
                if line is _SENTINEL:
                    break
                yield f"data: {line}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(event_source(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # Datasets (§3.9): GET /api/datasets, GET /api/features
    # ------------------------------------------------------------------
    @app.get("/api/datasets", response_model=DatasetOut)
    def get_dataset(
        mode: RefreshMode = Query(
            "offline", description="offline (default, no toca Databricks) | volume_as_is | ensure_latest"
        ),
    ) -> DatasetOut:
        dataset_version, path = deps.snapshot_sync.refresh(mode=mode)
        return DatasetOut(
            dataset_version=DatasetVersionOut.model_validate(dataset_version), cache_path=str(path), mode=mode
        )

    @app.get("/api/features", response_model=FeatureCatalogOut)
    def get_features() -> FeatureCatalogOut:
        groups = [FeatureGroupOut.model_validate(g) for g in deps.feature_catalog.groups]
        return FeatureCatalogOut(groups=groups)

    # ------------------------------------------------------------------
    # Frontend estatico (Fase 5, §3.9: "Build estatico servido por FastAPI en `/`"): montado
    # *despues* de todas las rutas `/api/*` de arriba, a proposito -- Starlette resuelve rutas en
    # el orden en que se registraron y devuelve el primer match, asi que un catch-all acá abajo
    # nunca puede robarle una request a `/api/health` ni al resto. Solo se activa si
    # `rio_search/frontend/dist` existe (post `npm run build`); si no existe (tests de la API,
    # backend sin frontend compilado todavia) la API sigue funcionando igual, sin servir "/" --
    # asi los 262 tests de `pytest` (que construyen `create_app(deps=fake)` sin buildear nada)
    # siguen en verde sin tocarlos.
    frontend_dist = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    if frontend_dist.is_dir():
        index_file = frontend_dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_frontend(full_path: str) -> FileResponse:
            candidate = (frontend_dist / full_path).resolve()
            if full_path and candidate.is_file() and frontend_dist in candidate.parents:
                return FileResponse(candidate)
            # Fallback de SPA (React Router con `BrowserRouter`): cualquier ruta de la UI que no
            # sea un archivo real del build (`/runs/<id>`, `/compare`, ...) sirve `index.html` y
            # React Router resuelve la ruta en el cliente.
            return FileResponse(index_file)

    return app


_SENTINEL = object()


def _next_or_sentinel(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return _SENTINEL


# Nota: a diferencia de la Fase 0, este modulo **no** construye `app = create_app()` a nivel de
# modulo -- `create_app()` sin `deps` arma el `ApiDependencies` real (Databricks/MLflow, Fase 4)
# y eso no debe pasar solo por *importar* el modulo (rompe los tests de la API, que importan
# `create_app` para pasarle un `ApiDependencies` falso). `rio-search api serve` (interfaces/cli)
# usa `uvicorn.run(..., factory=True)`, que llama a `create_app()` el mismo -- no necesita este
# `app` de nivel de modulo.
