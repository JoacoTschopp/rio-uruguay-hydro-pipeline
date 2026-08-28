"""Tests offline de `infrastructure.jobs.subprocess_job_runner.SubprocessJobRunner` (Fase 4,
docs/rio_search_plan.md §5): `command_builder` inyectado apunta a `sys.executable -c "..."` (un
proceso Python trivial, nunca `rio-search search run`) -- verifica cola/estado/log/lock sin
tocar Databricks/MLflow ni lanzar una busqueda real."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from rio_search.application.ports.job_runner import JobStatus
from rio_search.infrastructure.jobs.process_lock import ProcessLock
from rio_search.infrastructure.jobs.subprocess_job_runner import SubprocessJobRunner


def _ok_command(config_path: Path) -> list[str]:
    line = f"search_run_id=fake-run-{config_path.stem} experiment=/x trials=1"
    return [sys.executable, "-c", f"print({line!r})"]


def _failing_command(config_path: Path) -> list[str]:
    return [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"]


def _slow_command(config_path: Path) -> list[str]:
    return [sys.executable, "-c", "import time; print('start'); time.sleep(0.3); print('end')"]


def _ok_predict_command(target: str) -> list[str]:
    line = (
        f"forecast_run_id=fake-forecast-{target} as_of=2026-08-23 data_lag_days=5 "
        "device=cpu dataset_delta_version=270 champion_run_id=fake-champion"
    )
    return [sys.executable, "-c", f"print({line!r})"]


def _wait_terminal(runner: SubprocessJobRunner, job_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = runner.get(job_id)
        if record is not None and record.status in (JobStatus.FINISHED, JobStatus.FAILED):
            return record
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} no termino a tiempo")


def _runner(tmp_path: Path, command_builder, predict_command_builder=None) -> SubprocessJobRunner:
    return SubprocessJobRunner(
        command_builder=command_builder,
        predict_command_builder=predict_command_builder,
        log_dir=tmp_path / "jobs",
        lock=ProcessLock(tmp_path / "job.lock"),
    )


def test_submit_starts_as_queued_then_reaches_finished(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    record = runner.submit(config_path=Path("cfg.yaml"), label="test")

    assert record.status == JobStatus.QUEUED
    final = _wait_terminal(runner, record.job_id)
    assert final.status == JobStatus.FINISHED
    assert final.exit_code == 0


def test_failing_subprocess_marks_job_failed(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _failing_command)
    record = runner.submit(config_path=Path("cfg.yaml"), label="test")

    final = _wait_terminal(runner, record.job_id)
    assert final.status == JobStatus.FAILED
    assert final.exit_code == 3


def test_log_file_captures_stdout(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    record = runner.submit(config_path=Path("cfg.yaml"), label="test")
    _wait_terminal(runner, record.job_id)

    log_path = tmp_path / "jobs" / f"{record.job_id}.log"
    assert "search_run_id=fake-run-cfg" in log_path.read_text(encoding="utf-8")


def test_finished_job_extracts_search_run_id_from_log(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    record = runner.submit(config_path=Path("cfg.yaml"), label="test")
    final = _wait_terminal(runner, record.job_id)

    assert final.extra.get("search_run_id") == "fake-run-cfg"


def test_get_unknown_job_returns_none(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    assert runner.get("nope") is None


def test_list_returns_newest_first(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    first = runner.submit(config_path=Path("a.yaml"), label="a")
    _wait_terminal(runner, first.job_id)
    second = runner.submit(config_path=Path("b.yaml"), label="b")
    _wait_terminal(runner, second.job_id)

    jobs = runner.list()
    assert [j.job_id for j in jobs][:2] == [second.job_id, first.job_id]


def test_jobs_run_one_at_a_time_never_concurrently(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _slow_command)
    first = runner.submit(config_path=Path("a.yaml"), label="a")
    second = runner.submit(config_path=Path("b.yaml"), label="b")

    # Justo despues de encolar ambos, como mucho uno esta RUNNING (nunca los dos): la cola en
    # memoria + el ProcessLock compartido (aviso operativo de la Fase 3) garantizan "un job a
    # la vez" incluso si el segundo ya esta en la cola.
    time.sleep(0.1)
    statuses = {
        first.job_id: runner.get(first.job_id).status,
        second.job_id: runner.get(second.job_id).status,
    }
    assert list(statuses.values()).count(JobStatus.RUNNING) <= 1

    _wait_terminal(runner, first.job_id)
    _wait_terminal(runner, second.job_id)
    assert runner.get(first.job_id).status == JobStatus.FINISHED
    assert runner.get(second.job_id).status == JobStatus.FINISHED


def test_stream_log_yields_lines_and_stops_when_finished(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    record = runner.submit(config_path=Path("cfg.yaml"), label="test")
    _wait_terminal(runner, record.job_id)

    lines = list(runner.stream_log(record.job_id))
    assert any("search_run_id=fake-run-cfg" in line for line in lines)


def test_stream_log_of_unknown_job_yields_nothing(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)
    assert list(runner.stream_log("nope")) == []


def test_submit_predict_runs_via_predict_command_builder_and_extracts_forecast_run_id(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path, _ok_command, predict_command_builder=_ok_predict_command)
    record = runner.submit_predict(target="caudal", label="Predecir hoy (caudal)")

    assert record.config_path == "predict:caudal"
    final = _wait_terminal(runner, record.job_id)
    assert final.status == JobStatus.FINISHED
    assert final.extra.get("forecast_run_id") == "fake-forecast-caudal"
    assert final.extra.get("as_of") == "2026-08-23"


def test_submit_predict_without_builder_raises_immediately(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _ok_command)  # sin predict_command_builder
    try:
        runner.submit_predict(target="caudal", label="Predecir hoy (caudal)")
        assert False, "se esperaba RuntimeError"
    except RuntimeError:
        pass


def test_predict_and_search_jobs_share_the_same_lock_never_concurrently(tmp_path: Path) -> None:
    predict_builder = lambda target: _slow_command(Path(target))  # noqa: E731
    runner = _runner(tmp_path, _slow_command, predict_command_builder=predict_builder)
    search_job = runner.submit(config_path=Path("a.yaml"), label="a")
    predict_job = runner.submit_predict(target="caudal", label="Predecir hoy (caudal)")

    time.sleep(0.1)
    statuses = {
        search_job.job_id: runner.get(search_job.job_id).status,
        predict_job.job_id: runner.get(predict_job.job_id).status,
    }
    assert list(statuses.values()).count(JobStatus.RUNNING) <= 1

    _wait_terminal(runner, search_job.job_id)
    _wait_terminal(runner, predict_job.job_id)
