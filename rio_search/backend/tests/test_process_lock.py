"""Tests offline de `infrastructure.jobs.process_lock.ProcessLock` (Fase 4,
docs/rio_search_plan.md §5: "comparte el `lock.py` de `ana_historic_backfill`"): mismo patron
que el original (`notebooks_local/ana_historic_backfill/lock.py`, verificado por inspeccion, no
importado -- §0 del encargo) pero portado a `rio_search/backend`. Usa el propio PID del proceso
de test (siempre "vivo" para `tasklist`) y un PID inventado (999999, asumido muerto) para el
caso "stale"."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from rio_search.infrastructure.jobs.process_lock import ProcessLock


def test_acquire_when_free_succeeds(tmp_path: Path) -> None:
    lock = ProcessLock(tmp_path / "job.lock")
    assert lock.acquire("test") is True
    assert lock.is_locked() is not None
    lock.release()


def test_acquire_when_held_by_self_pid_fails(tmp_path: Path) -> None:
    lock_file = tmp_path / "job.lock"
    lock = ProcessLock(lock_file)
    assert lock.acquire("first") is True

    other = ProcessLock(lock_file)
    assert other.acquire("second") is False  # el PID del test sigue "vivo" -> lock real


def test_release_frees_the_lock(tmp_path: Path) -> None:
    lock = ProcessLock(tmp_path / "job.lock")
    lock.acquire("test")
    lock.release()
    assert lock.is_locked() is None
    assert lock.acquire("test-again") is True


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path: Path) -> None:
    lock_file = tmp_path / "job.lock"
    lock_file.write_text('{"pid": 999999, "label": "dead", "started_at": 0}', encoding="utf-8")

    lock = ProcessLock(lock_file)
    assert lock.is_locked() is None  # PID 999999 no deberia existir -> se libera solo
    assert lock.acquire("fresh") is True


def test_acquire_blocking_returns_false_on_timeout_when_held(tmp_path: Path) -> None:
    lock_file = tmp_path / "job.lock"
    holder = ProcessLock(lock_file)
    holder.acquire("holder")

    waiter = ProcessLock(lock_file)
    started = time.monotonic()
    result = waiter.acquire_blocking("waiter", poll_seconds=0.05, timeout_seconds=0.2)
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed >= 0.15


def test_acquire_blocking_succeeds_once_released_concurrently(tmp_path: Path) -> None:
    lock_file = tmp_path / "job.lock"
    holder = ProcessLock(lock_file)
    holder.acquire("holder")

    def release_soon() -> None:
        time.sleep(0.1)
        holder.release()

    threading.Thread(target=release_soon, daemon=True).start()

    waiter = ProcessLock(lock_file)
    assert waiter.acquire_blocking("waiter", poll_seconds=0.03, timeout_seconds=2.0) is True


def test_read_returns_stored_label(tmp_path: Path) -> None:
    lock = ProcessLock(tmp_path / "job.lock")
    lock.acquire("my-label")
    info = lock.read()
    assert info is not None
    assert info["label"] == "my-label"
    assert info["pid"] == os.getpid()
