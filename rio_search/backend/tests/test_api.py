"""Tests offline de la API FastAPI (Fase 4, docs/rio_search_plan.md §3.9, §5: "tests con
`TestClient` y un `TrackingPort` falso"): `ApiDependencies` enteramente falso (reader, job
runner, snapshot sync) -- ningun test de este archivo toca Databricks/MLflow real. El caso
end-to-end real contra Databricks/MLflow (criterio de cierre de la Fase 4) se corre aparte, a
mano, no como parte de `pytest`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rio_search.application.experiments.compare_runs import CompareRuns
from rio_search.application.experiments.get_run_detail import GetRunDetail
from rio_search.application.experiments.list_runs import ListRuns
from rio_search.application.experiments.list_searches import ListSearches
from rio_search.application.ports.job_runner import JobRecord, JobStatus
from rio_search.application.ports.tracking_read import MetricPoint, RunRecord
from rio_search.domain.datasets.dataset_version import DatasetVersion
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.datasets.feature_group import FeatureGroup
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


def _hierarchy() -> list[RunRecord]:
    search = _run("search-1", None, 300)
    trial_a = _run("trial-a", "search-1", 200, params={"model.name": "bilstm"})
    trial_b = _run("trial-b", "search-1", 100, params={"model.name": "persistence"})
    horizon = _run("h01", "trial-a", 250)
    return [search, trial_a, trial_b, horizon]


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
    )
    return TestClient(create_app(deps=deps))


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_runs_returns_all_records(client: TestClient) -> None:
    response = client.get("/api/runs")
    assert response.status_code == 200
    run_ids = {r["run_id"] for r in response.json()["runs"]}
    assert run_ids == {"search-1", "trial-a", "trial-b", "h01"}


def test_list_searches_groups_trials(client: TestClient) -> None:
    response = client.get("/api/searches")
    assert response.status_code == 200
    searches = response.json()["searches"]
    assert len(searches) == 1
    assert searches[0]["search"]["run_id"] == "search-1"
    assert sorted(t["run_id"] for t in searches[0]["trials"]) == ["trial-a", "trial-b"]


def test_get_run_detail(client: TestClient) -> None:
    response = client.get("/api/runs/search-1")
    assert response.status_code == 200
    body = response.json()
    assert body["run"]["run_id"] == "search-1"
    assert sorted(c["run_id"] for c in body["children"]) == ["trial-a", "trial-b"]


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
