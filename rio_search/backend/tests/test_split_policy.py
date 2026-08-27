"""Tests de `SplitPolicy`/`Split` (Decision #4, docs/rio_search_plan.md §3.6, Fase 1): rangos
esperados de `rolling_365` y `calendar_year`, invariantes de no-fuga (no-overlap, embargo,
orden temporal train < val < test, test nunca despues del anchor)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from rio_search.domain.datasets.split_policy import Split, SplitPolicy, TrainWindow, compute_anchor
from rio_search.domain.shared.date_range import DateRange

HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)


def test_compute_anchor_is_fecha_max_minus_max_horizon() -> None:
    anchor = compute_anchor(date(2026, 8, 23), HORIZONS)
    assert anchor == date(2026, 8, 9)


def test_compute_anchor_requires_horizons() -> None:
    with pytest.raises(ValueError):
        compute_anchor(date(2026, 8, 23), ())


def test_rolling_365_matches_worked_example_from_plan() -> None:
    # Ejemplo textual de docs/rio_search_plan.md §3.6: "Con los datos de hoy, rolling_365 da
    # TEST ≈ 2025-08-10 → 2026-08-09, VAL ≈ 2024-07-27 → 2025-07-26."
    policy = SplitPolicy(
        policy="rolling_365", embargo_days=14, train_window=TrainWindow(start=date(2008, 1, 1))
    )
    split = policy.build(fecha_max=date(2026, 8, 23), horizons=HORIZONS)

    assert split.anchor == date(2026, 8, 9)
    assert split.test == DateRange(date(2025, 8, 10), date(2026, 8, 9))
    assert split.val == DateRange(date(2024, 7, 27), date(2025, 7, 26))
    assert split.train.start == date(2008, 1, 1)
    assert split.train.end == date(2024, 7, 12)


def test_calendar_year_ranges() -> None:
    policy = SplitPolicy(
        policy="calendar_year", embargo_days=14, train_window=TrainWindow(start=date(2000, 1, 1))
    )
    # anchor = 2026-08-09: el 2026 no esta completo (no llega a 31-dic) -> ultimo completo = 2025.
    split = policy.build(fecha_max=date(2026, 8, 23), horizons=HORIZONS)

    assert split.test == DateRange(date(2025, 1, 1), date(2025, 12, 31))
    assert split.val == DateRange(date(2024, 1, 1), date(2024, 12, 17))  # 31-dic-2024 - 14d
    assert split.train.start == date(2000, 1, 1)
    assert split.train.end == date(2023, 12, 17)  # 31-dic-2023 - 14d


def test_calendar_year_uses_current_year_when_anchor_reaches_dec_31() -> None:
    policy = SplitPolicy(
        policy="calendar_year", embargo_days=14, train_window=TrainWindow(start=date(2000, 1, 1))
    )
    # fecha_max = 2027-01-14 -> anchor = fecha_max - 14d = 2026-12-31: el 2026 SI esta completo.
    split = policy.build(fecha_max=date(2027, 1, 14), horizons=HORIZONS)
    assert split.test == DateRange(date(2026, 1, 1), date(2026, 12, 31))


def test_train_window_years_resolves_relative_to_val_start() -> None:
    policy = SplitPolicy(policy="rolling_365", embargo_days=14, train_window=TrainWindow(years=5))
    split = policy.build(fecha_max=date(2026, 8, 23), horizons=HORIZONS)
    assert split.train.start == date(2019, 7, 27)  # val_start (2024-07-27) - 5 años


def test_train_window_requires_exactly_one_of_start_or_years() -> None:
    with pytest.raises(ValueError):
        TrainWindow()
    with pytest.raises(ValueError):
        TrainWindow(start=date(2000, 1, 1), years=5)


def test_split_no_overlap_between_train_val_test() -> None:
    policy = SplitPolicy(policy="rolling_365", embargo_days=14, train_window=TrainWindow(years=10))
    split = policy.build(fecha_max=date(2026, 8, 23), horizons=HORIZONS)
    assert not split.train.overlaps(split.val)
    assert not split.val.overlaps(split.test)
    assert not split.train.overlaps(split.test)


def test_split_embargo_separates_val_targets_from_test_inputs() -> None:
    """Ningun target de VAL (val_end + horizonte) cae dentro de TEST (§6, riesgo de fuga)."""
    policy = SplitPolicy(policy="rolling_365", embargo_days=14, train_window=TrainWindow(years=10))
    split = policy.build(fecha_max=date(2026, 8, 23), horizons=HORIZONS)
    for h in HORIZONS:
        target_date = split.val.end + timedelta(days=h)
        assert target_date < split.test.start, (
            f"target de VAL a horizonte {h} ({target_date}) cae dentro de TEST ({split.test})"
        )


def test_split_train_end_respects_embargo_before_val_start() -> None:
    policy = SplitPolicy(policy="rolling_365", embargo_days=14, train_window=TrainWindow(years=10))
    split = policy.build(fecha_max=date(2026, 8, 23), horizons=HORIZONS)
    assert split.train.end + timedelta(days=14) < split.val.start


def test_split_rejects_test_after_anchor() -> None:
    with pytest.raises(ValueError, match="anchor"):
        Split(
            policy="rolling_365",
            anchor=date(2020, 1, 1),
            train=DateRange(date(2010, 1, 1), date(2018, 1, 1)),
            val=DateRange(date(2018, 2, 1), date(2019, 1, 1)),
            test=DateRange(date(2019, 2, 1), date(2020, 1, 2)),  # 1 dia despues del anchor
        )


def test_split_rejects_overlapping_ranges() -> None:
    with pytest.raises(ValueError):
        Split(
            policy="rolling_365",
            anchor=date(2020, 1, 1),
            train=DateRange(date(2010, 1, 1), date(2018, 6, 1)),
            val=DateRange(date(2018, 1, 1), date(2019, 1, 1)),  # solapa con train
            test=DateRange(date(2019, 2, 1), date(2020, 1, 1)),
        )


def test_split_policy_rejects_unknown_policy() -> None:
    with pytest.raises(ValueError):
        SplitPolicy(policy="quarterly", embargo_days=14, train_window=TrainWindow(years=1))  # type: ignore[arg-type]


def test_split_policy_rejects_negative_embargo() -> None:
    with pytest.raises(ValueError):
        SplitPolicy(policy="rolling_365", embargo_days=-1, train_window=TrainWindow(years=1))
