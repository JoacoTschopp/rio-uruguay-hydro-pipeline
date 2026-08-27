"""Tests offline de la API FastAPI (Fase 4, docs/rio_search_plan.md §3.9, §5: "tests con
`TestClient` y un `TrackingPort` falso"): `ApiDependencies` enteramente falso (reader, job
runner, snapshot sync) -- ningun test de este archivo toca Databricks/MLflow real. El caso
end-to-end real contra Databricks/MLflow (criterio de cierre de la Fase 4) se corre aparte, a
mano, no como parte de `pytest`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from rio_search.application.experiments.compare_runs import CompareRuns
from rio_search.application.experiments.get_run_detail import GetRunDetail
from rio_search.application.experiments.list_runs import ListRuns
from rio_search.application.experiments.list_searches import ListSearches
from rio_search.application.ports.job_runner import JobRecord, JobStatus
from rio_search.application.ports.tracking_read import MetricPoint, RunRecord
from rio_search.application.predictions.backtest_recent import BacktestRecent
from rio_search.application.predictions.promote_champion import PromoteChampion
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.datasets.feature_group import FeatureGroup
from rio_search.domain.predictions.champion import Champion
from rio_search.domain.predictions.forecast import Forecast, ForecastPoint
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.interfaces.api.dependencies import ApiDependencies
from rio_search.interfaces.api.main import create_app

BASE_PATH = "/Users/test@example.com/rio_search"


def _run(run_id: str, parent: str | None, start_ms: int, **kwargs) -> RunRecord:
    tags = {"mlflow.runName": run_id}
    if parent is not None:
        tags["mlflow.parentRunId"] = parent
    tags.update(kwargs.pop("tags", {}))
    return RunRecord(
        run_id=run_id,
        experiment_id="exp-1",
        status=kwargs.pop("status", "FINISHED"),
        start_time_ms=start_ms,
        end_time_ms=start_ms + 100,
        artifact_uri=f"dbfs:/{run_id}",
        tags=tags,
        params=kwargs.pop("params", {}),
        metrics=kwargs.pop("metrics", {"time/train_total_s": 12.5, "test/rmse/h01": 3.2}),
    )


class FakeReader:
    def __init__(self, runs: list[RunRecord]) -> None:
        self._runs = {r.run_id: r for r in runs}

    def list_runs(self, experiment_names, max_results: int = 500) -> list[RunRecord]:
        return list(self._runs.values())

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_children(
        self, parent_run_id: str, experiment_id: str, max_results: int = 200
    ) -> list[RunRecord]:
        return [r for r in self._runs.values() if r.parent_run_id == parent_run_id]

    def get_metric_history(self, run_id: str, metric_key: str) -> list[MetricPoint]:
        return [
            MetricPoint(step=0, timestamp_ms=1000, value=1.0),
            MetricPoint(step=1, timestamp_ms=2000, value=0.5),
        ]


class FakeJobRunner:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self.submitted: list[tuple[Path, str]] = []

    def submit(self, config_path: Path, label: str) -> JobRecord:
        job_id = f"job-{len(self._jobs) + 1}"
        record = JobRecord(
            job_id=job_id,
            label=label,
            config_path=str(config_path),
            status=JobStatus.FINISHED,
            created_at="2026-01-01T00:00:00+00:00",
            started_at="2026-01-01T00:00:01+00:00",
            ended_at="2026-01-01T00:00:02+00:00",
            exit_code=0,
            pid=4242,
            extra={"search_run_id": "run-xyz"},
        )
        self._jobs[job_id] = record
        self.submitted.append((config_path, label))
        return record

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        return list(self._jobs.values())

    def stream_log(self, job_id: str):
        yield "descargando dataset..."
        yield "search_run_id=run-xyz experiment=/x trials=1"


class FakeSnapshotSync:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def refresh(self, mode: str = "ensure_latest", force: bool = False):
        self.calls.append(mode)
        version = DatasetVersion(
            delta_version=268,
            sha256="a" * 64,
            rows=9732,
            fecha_min="2000-01-01",
            fecha_max="2026-08-23",
            columns=("fecha", "caudal_actual_m3s"),
            punto_prediccion="ana_74100000",
            exported_at="2026-08-26T07:40:27+00:00",
        )
        return version, Path("/fake/cache/training_dataset_v0.parquet")


class FakeChampionStore:
    def __init__(self) -> None:
        self._by_target: dict[str, Champion] = {}
        self._history: dict[str, list[Champion]] = {}

    def set(self, champion: Champion) -> None:
        self._by_target[champion.target.value] = champion
        self._history.setdefault(champion.target.value, []).insert(0, champion)

    def get(self, target: TargetVariable) -> Champion | None:
        return self._by_target.get(target.value)

    def history(self, target: TargetVariable, max_results: int = 50) -> list[Champion]:
        return self._history.get(target.value, [])[:max_results]


class FakeForecastRepository:
    def __init__(self) -> None:
        self._by_target: dict[str, list[Forecast]] = {}

    def save(self, forecast: Forecast) -> None:
        self._by_target.setdefault(forecast.target.value, []).insert(0, forecast)

    def latest(self, target: TargetVariable) -> Forecast | None:
        items = self._by_target.get(target.value, [])
        return items[0] if items else None

    def list_recent(self, target: TargetVariable, max_results: int = 30) -> list[Forecast]:
        return self._by_target.get(target.value, [])[:max_results]


class FakeDatasetRepository:
    def load(self, mode: str = "ensure_latest", force: bool = False):
        version = DatasetVersion(
            delta_version=268,
            sha256="a" * 64,
            rows=3,
            fecha_min="2026-08-01",
            fecha_max="2026-08-03",
            columns=("fecha", "caudal_actual_m3s"),
        )
        df = pl.DataFrame(
            {
                "fecha": [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)],
                "caudal_actual_m3s": [1000.0, 1010.0, None],
            }
        )
        return version, df


def _champion_candidate_run() -> RunRecord:
    """Trial `bilstm` real de la Fase 3 (tags/metricas minimas que `PromoteChampion` necesita):
    `rio_search.model`, `rio_search.target`, `registered_model_name`/`_version`,
    `val/kge/mean`."""
    return _run(
        "bilstm-v9",
        "search-1",
        400,
        tags={
            "rio_search.model": "bilstm",
            "rio_search.target": "caudal",
            "rio_search.registered_model_name": "weather.ml.rio_search_bilstm",
            "rio_search.registered_model_version": "9",
        },
        metrics={"val/kge/mean": 0.207},
    )


def _hierarchy() -> list[RunRecord]:
    search = _run("search-1", None, 300)
    trial_a = _run("trial-a", "search-1", 200, params={"model.name": "bilstm"})
    trial_b = _run("trial-b", "search-1", 100, params={"model.name": "persistence"})
    horizon = _run("h01", "trial-a", 250)
    return [search, trial_a, trial_b, horizon, _champion_candidate_run()]


@pytest.fixture()
def experiments_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "configs" / "experiments"
    directory.mkdir(parents=True)
    (directory / "persistence_baseline_v1.yaml").write_text(
        "name: persistence_baseline_v1\n", encoding="utf-8"
    )
    return directory


@pytest.fixture()
def client(experiments_dir: Path) -> TestClient:
    reader = FakeReader(_hierarchy())
    list_runs = ListRuns(reader=reader, base_path=BASE_PATH)
    feature_catalog = FeatureCatalog(
        groups=(FeatureGroup(name="caudal_estado", columns=("caudal_actual_m3s",), default_on=True),)
    )
    champion_store = FakeChampionStore()
    forecast_repository = FakeForecastRepository()
    deps = ApiDependencies(
        reader=reader,
        list_runs=list_runs,
        list_searches=ListSearches(list_runs=list_runs),
        get_run_detail=GetRunDetail(reader=reader),
        compare_runs=CompareRuns(reader=reader),
        job_runner=FakeJobRunner(),
        experiments_dir=experiments_dir,
        snapshot_sync=FakeSnapshotSync(),
        feature_catalog=feature_catalog,
        promote_champion=PromoteChampion(reader=reader, store=champion_store, model_alias=None),
        champion_store=champion_store,
        forecast_repository=forecast_repository,
        backtest_recent=BacktestRecent(
            forecast_repository=forecast_repository, dataset_repository=FakeDatasetRepository()
        ),
    )
    test_client = TestClient(create_app(deps=deps))
    # Atributos extra (no parte de `TestClient`) para que los tests de Fase 6 puedan sembrar el
    # repo falso directamente -- las rutas HTTP no exponen "crear un pronostico", eso lo hace
    # `IssueDailyForecast` (CLI/Task Scheduler), no la API (ver docstring de
    # `interfaces.container.build_api_dependencies`).
    test_client.forecast_repository = forecast_repository  # type: ignore[attr-defined]
    test_client.champion_store = champion_store  # type: ignore[attr-defined]
    return test_client


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_runs_returns_all_records(client: TestClient) -> None:
    response = client.get("/api/runs")
    assert response.status_code == 200
    run_ids = {r["run_id"] for r in response.json()["runs"]}
    assert run_ids == {"search-1", "trial-a", "trial-b", "h01", "bilstm-v9"}


def test_list_searches_groups_trials(client: TestClient) -> None:
    response = client.get("/api/searches")
    assert response.status_code == 200
    searches = response.json()["searches"]
    assert len(searches) == 1
    assert searches[0]["search"]["run_id"] == "search-1"
    assert sorted(t["run_id"] for t in searches[0]["trials"]) == ["bilstm-v9", "trial-a", "trial-b"]


def test_get_run_detail(client: TestClient) -> None:
    response = client.get("/api/runs/search-1")
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["run_id"] == "search-1"
    assert sorted(c["run_id"] for c in body["children"]) == ["bilstm-v9", "trial-a", "trial-b"]


def test_get_run_detail_404_for_unknown_run(client: TestClient) -> None:
    response = client.get("/api/runs/does-not-exist")
    assert response.status_code == 404


def test_get_run_series(client: TestClient) -> None:
    response = client.get("/api/runs/trial-a/series/train%2Floss")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "trial-a"
    assert len(body["points"]) == 2


def test_compare_runs(client: TestClient) -> None:
    response = client.get("/api/runs/compare", params={"ids": "trial-a,trial-b,nope"})
    assert response.status_code == 200
    body = response.json()
    assert body["missing_run_ids"] == ["nope"]
    assert body["param_diff"]["model.name"] == {"trial-a": "bilstm", "trial-b": "persistence"}


def test_compare_runs_requires_ids(client: TestClient) -> None:
    response = client.get("/api/runs/compare", params={"ids": ""})
    assert response.status_code == 400


def test_submit_job_returns_finished_fake_job(client: TestClient) -> None:
    response = client.post("/api/jobs", json={"config": "persistence_baseline_v1.yaml"})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "finished"
    assert body["extra"]["search_run_id"] == "run-xyz"


def test_submit_job_rejects_unknown_config(client: TestClient) -> None:
    response = client.post("/api/jobs", json={"config": "does_not_exist.yaml"})
    assert response.status_code == 400


def test_submit_job_rejects_path_traversal(client: TestClient) -> None:
    response = client.post("/api/jobs", json={"config": "../../evil.yaml"})
    assert response.status_code == 400


def test_list_jobs_and_get_job(client: TestClient) -> None:
    submit_response = client.post("/api/jobs", json={"config": "persistence_baseline_v1.yaml"})
    job_id = submit_response.json()["job_id"]

    list_response = client.get("/api/jobs")
    assert any(j["job_id"] == job_id for j in list_response.json()["jobs"])

    get_response = client.get(f"/api/jobs/{job_id}")
    assert get_response.status_code == 200
    assert get_response.json()["job_id"] == job_id


def test_get_unknown_job_404(client: TestClient) -> None:
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


def test_job_log_stream_returns_sse_lines(client: TestClient) -> None:
    submit_response = client.post("/api/jobs", json={"config": "persistence_baseline_v1.yaml"})
    job_id = submit_response.json()["job_id"]

    response = client.get(f"/api/jobs/{job_id}/log")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "search_run_id=run-xyz" in response.text


def test_job_log_stream_404_for_unknown_job(client: TestClient) -> None:
    response = client.get("/api/jobs/does-not-exist/log")
    assert response.status_code == 404


def test_get_dataset_defaults_to_offline_mode(client: TestClient) -> None:
    response = client.get("/api/datasets")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "offline"
    assert body["dataset_version"]["delta_version"] == 268
    assert body["dataset_version"]["rows"] == 9732


def test_get_features_returns_catalog(client: TestClient) -> None:
    response = client.get("/api/features")
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert groups[0]["name"] == "caudal_estado"
    assert groups[0]["columns"] == ["caudal_actual_m3s"]


def test_api_routes_never_fall_through_to_the_frontend_static_mount(client: TestClient) -> None:
    """Fase 5 (docs/rio_search_plan.md §3.9): `create_app` monta el build estatico del frontend
    en `/` *despues* de registrar todas las rutas `/api/*` -- Starlette resuelve por orden de
    registro, asi que un catch-all de SPA nunca deberia poder robarle una request a `/api/*`. Un
    404 de verdad (no el `index.html` del SPA) es la prueba de que el orden se respeto."""
    response = client.get("/api/runs/does-not-exist-at-all")
    assert response.status_code == 404
    assert response.json()["detail"] == "run 'does-not-exist-at-all' no encontrado"


def test_frontend_static_mount_matches_whether_dist_was_built(client: TestClient) -> None:
    """No hay flag para forzar el montaje: `create_app` decide solo mirando si
    `rio_search/frontend/dist` existe (para que los 262 tests de `pytest`, que nunca compilan el
    frontend, sigan pasando igual). Este test refleja esa misma condicion en vez de asumir un
    estado fijo, asi pasa tanto en una maquina con el build hecho (Fase 5, verificado real) como
    en CI sin `npm run build` corrido."""
    from pathlib import Path

    # tests/test_api.py -> parents[1] = rio_search/backend -> parents[2] = rio_search (top),
    # hermano de rio_search/frontend -- misma cuenta de `.parents[4]` que usa `interfaces/api/
    # main.py` desde su propia ubicacion, un nivel mas profundo.
    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    response = client.get("/")
    if frontend_dist.is_dir():
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    else:
        assert response.status_code == 404


# ------------------------------------------------------------------
# Fase 6 -- Predicciones (§3.9): POST/GET /api/champions, GET /api/forecasts/*.
# ------------------------------------------------------------------


def test_promote_champion_sets_it_from_a_real_run(client: TestClient) -> None:
    response = client.post("/api/champions", json={"run_id": "bilstm-v9", "target": "caudal"})
    assert response.status_code == 201
    body = response.json()
    assert body["run_id"] == "bilstm-v9"
    assert body["model_name"] == "bilstm"
    assert body["metric_value"] == pytest.approx(0.207)
    assert body["registered_model_version"] == "9"

    get_response = client.get("/api/champions", params={"target": "caudal"})
    assert get_response.status_code == 200
    assert get_response.json()["run_id"] == "bilstm-v9"


def test_promote_champion_rejects_run_without_metric(client: TestClient) -> None:
    response = client.post(
        "/api/champions", json={"run_id": "trial-b", "target": "caudal", "metric_name": "val/kge/mean"}
    )
    assert response.status_code == 400


def test_get_champion_404_when_none_promoted(client: TestClient) -> None:
    response = client.get("/api/champions", params={"target": "nivel"})
    assert response.status_code == 404


def _sample_forecast(as_of: date, issued_at: str) -> Forecast:
    return Forecast(
        target=TargetVariable.CAUDAL,
        as_of=as_of,
        issued_at=issued_at,
        dataset_delta_version=268,
        dataset_sha256="a" * 64,
        champion_run_id="bilstm-v9",
        champion_model_name="bilstm",
        device_type="cpu",
        data_lag_days=1,
        points=(
            ForecastPoint(horizon=1, target_date=date(2026, 8, 2), value=1005.0),
            ForecastPoint(horizon=2, target_date=date(2026, 8, 3), value=1010.0),
        ),
        forecast_run_id="forecast-run-1",
    )


def test_forecasts_latest_and_history_and_backtest(client: TestClient) -> None:
    empty = client.get("/api/forecasts/latest", params={"target": "caudal"})
    assert empty.status_code == 404

    older = _sample_forecast(date(2026, 8, 1), "2026-08-01T06:30:00+00:00")
    newer = _sample_forecast(date(2026, 8, 2), "2026-08-02T06:30:00+00:00")
    client.forecast_repository.save(older)  # type: ignore[attr-defined]
    client.forecast_repository.save(newer)  # type: ignore[attr-defined]

    latest = client.get("/api/forecasts/latest", params={"target": "caudal"})
    assert latest.status_code == 200
    assert latest.json()["as_of"] == "2026-08-02"
    assert latest.json()["points"][0]["horizon"] == 1

    history = client.get("/api/forecasts/history", params={"target": "caudal"})
    assert history.status_code == 200
    assert [f["as_of"] for f in history.json()["forecasts"]] == ["2026-08-02", "2026-08-01"]

    # `_sample_forecast` predice horizonte 1 -> fecha_objetivo=2026-08-02 (observado real en
    # `FakeDatasetRepository` = 1010.0) y horizonte 2 -> fecha_objetivo=2026-08-03 (nulo en el
    # dataset falso, todavia "pendiente" en el backtest).
    backtest = client.get("/api/forecasts/backtest", params={"target": "caudal"})
    assert backtest.status_code == 200
    body = backtest.json()
    assert body["target"] == "caudal"
    assert len(body["points"]) == 4  # 2 forecasts x 2 horizontes cada uno
    resolved = [p for p in body["points"] if p["observed"] is not None]
    pending = [p for p in body["points"] if p["observed"] is None]
    assert len(resolved) == 2 and len(pending) == 2
    assert all(p["horizon"] == 1 and p["observed"] == pytest.approx(1010.0) for p in resolved)
