"""Tests de `PerfCounterStopwatch` (Decisiones #13/#14, docs/rio_search_plan.md §3.12)."""

from __future__ import annotations

import time

from rio_search.infrastructure.timing.stopwatch import PerfCounterStopwatch


def test_track_records_elapsed_seconds() -> None:
    sw = PerfCounterStopwatch(cuda_sync=False)
    with sw.track("dataset_download_s"):
        time.sleep(0.01)
    elapsed = sw.elapsed("dataset_download_s")
    assert elapsed is not None
    assert elapsed >= 0.01


def test_elapsed_is_none_when_never_tracked() -> None:
    sw = PerfCounterStopwatch(cuda_sync=False)
    assert sw.elapsed("never_tracked") is None


def test_history_accumulates_repeated_names() -> None:
    sw = PerfCounterStopwatch(cuda_sync=False)
    for _ in range(3):
        with sw.track("train_epoch_s"):
            pass
    assert len(sw.history("train_epoch_s")) == 3
    # elapsed() siempre expone la ultima medicion.
    assert sw.elapsed("train_epoch_s") == sw.history("train_epoch_s")[-1]


def test_as_metrics_uses_fixed_time_prefix() -> None:
    sw = PerfCounterStopwatch(cuda_sync=False)
    with sw.track("train_total_s"):
        pass
    with sw.track("eval_test_s"):
        pass
    metrics = sw.as_metrics()
    assert set(metrics.keys()) == {"time/train_total_s", "time/eval_test_s"}
    assert all(isinstance(v, float) for v in metrics.values())


def test_track_records_elapsed_even_on_exception() -> None:
    sw = PerfCounterStopwatch(cuda_sync=False)
    try:
        with sw.track("preprocess_s"):
            raise ValueError("boom")
    except ValueError:
        pass
    assert sw.elapsed("preprocess_s") is not None
