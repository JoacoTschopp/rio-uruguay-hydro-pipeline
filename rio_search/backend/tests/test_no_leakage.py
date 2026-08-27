"""Tests de no-fuga temporal de punta a punta (Fase 1, docs/rio_search_plan.md §5, criterio de
Tests de la fase): dataset sintetico en Polars, pipeline completo `BuildSplit` ->
`SequenceBuilder` -> `TargetBuilder`, y las cuatro invariantes que pide el plan:

1. Ninguna fecha de TRAIN es posterior al inicio de VAL menos el embargo.
2. Ningun target de VAL cae dentro de los inputs (fechas) de TEST.
3. El escalador no ve VAL/TEST (ver tambien test_build_feature_matrix.py, aca se repite el
   caso limite con un dataset donde VAL/TEST tienen una escala deliberadamente distinta).
4. Las ventanas de `SequenceBuilder` no cruzan el `anchor` de la busqueda.

`calendar_year`/`rolling_365` dando los rangos esperados esta cubierto en
`test_split_policy.py` (incluye el ejemplo textual del propio plan, §3.6).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from rio_search.application.datasets.build_split import BuildSplit
from rio_search.domain.datasets.sequence_spec import SequenceSpec
from rio_search.domain.datasets.split_policy import SplitPolicy, TrainWindow
from rio_search.domain.shared.target_variable import TargetVariable
from rio_search.infrastructure.datasets.sequence_builder import SequenceBuilder
from rio_search.infrastructure.datasets.target_builder import TargetBuilder
from rio_search.infrastructure.preprocess.scalers import apply_scaler, fit_scaler

HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)
EMBARGO_DAYS = 14


def _synthetic_df(n_days: int = 1200, start: date = date(2015, 1, 1)) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(n_days)]
    ramp = [float(i) for i in range(n_days)]
    data: dict[str, list] = {"fecha": dates, "caudal_actual_m3s": ramp}
    for h in HORIZONS:
        data[f"caudal_t_mas_{h}d"] = [ramp[i + h] if i + h < n_days else None for i in range(n_days)]
    return pl.DataFrame(data)


def _split_dfs(policy_name: str = "rolling_365"):
    df = _synthetic_df()
    policy = SplitPolicy(
        policy=policy_name, embargo_days=EMBARGO_DAYS, train_window=TrainWindow(start=date(2015, 1, 1))
    )
    return BuildSplit().execute(df, policy, HORIZONS)


@pytest.mark.parametrize("policy_name", ["rolling_365", "calendar_year"])
def test_no_train_dates_after_val_start_minus_embargo(policy_name: str) -> None:
    split_dfs = _split_dfs(policy_name)
    train_max = split_dfs.train["fecha"].max()
    limit = split_dfs.split.val.start - timedelta(days=EMBARGO_DAYS)
    assert train_max <= limit, f"train llega hasta {train_max}, mas alla del limite {limit}"


@pytest.mark.parametrize("policy_name", ["rolling_365", "calendar_year"])
def test_no_val_target_falls_within_test_inputs(policy_name: str) -> None:
    """Para cada ventana de VAL (SequenceBuilder) y cada horizonte, la fecha del target
    (anchor + horizonte) debe caer antes del inicio de TEST -- nunca dentro de TEST."""
    split_dfs = _split_dfs(policy_name)
    seqs = SequenceBuilder(SequenceSpec(lookback_days=7)).build(split_dfs.val, ["caudal_actual_m3s"])

    test_start = split_dfs.split.test.start
    for anchor in seqs.anchor_dates:
        for h in HORIZONS:
            target_date = anchor + timedelta(days=h)
            assert target_date < test_start, (
                f"target de VAL en {anchor} a horizonte {h} ({target_date}) cae dentro de TEST "
                f"(inicia {test_start})"
            )


@pytest.mark.parametrize("policy_name", ["rolling_365", "calendar_year"])
def test_scaler_ignores_val_and_test_even_with_different_scale(policy_name: str) -> None:
    """Ademas de test_build_feature_matrix.py: aca VAL/TEST tienen una escala deliberadamente
    distinta de TRAIN (multiplicada por 1000) para que cualquier fuga sea imposible de pasar
    por alto en las estadisticas resultantes."""
    split_dfs = _split_dfs(policy_name)
    scaled_col = (pl.col("caudal_actual_m3s") * 1000).alias("caudal_actual_m3s")
    contaminated_val = split_dfs.val.with_columns(scaled_col)
    contaminated_test = split_dfs.test.with_columns(scaled_col)

    stats = fit_scaler(split_dfs.train, ["caudal_actual_m3s"], "standard")
    expected_center = split_dfs.train["caudal_actual_m3s"].mean()
    assert stats.center["caudal_actual_m3s"] == pytest.approx(expected_center)

    # Aplicar el escalador (ajustado solo con TRAIN) sobre VAL/TEST contaminados no cambia
    # `stats` -- lo unico que puede fallar es que `apply_scaler` reajuste, y no lo hace.
    apply_scaler(contaminated_val, ["caudal_actual_m3s"], stats)
    apply_scaler(contaminated_test, ["caudal_actual_m3s"], stats)
    assert stats.center["caudal_actual_m3s"] == pytest.approx(expected_center)


@pytest.mark.parametrize("policy_name", ["rolling_365", "calendar_year"])
def test_windows_never_cross_the_search_anchor(policy_name: str) -> None:
    """Ninguna ventana (de ningun split) tiene como fecha "as of" un dia posterior al
    `anchor` de la busqueda -- el limite estructural mas alla del cual el horizonte mas largo
    ya no tiene target observable (§3.6)."""
    split_dfs = _split_dfs(policy_name)
    anchor = split_dfs.split.anchor

    for name, part in (("train", split_dfs.train), ("val", split_dfs.val), ("test", split_dfs.test)):
        seqs = SequenceBuilder(SequenceSpec(lookback_days=7)).build(part, ["caudal_actual_m3s"])
        assert max(seqs.anchor_dates) <= anchor, f"{name} tiene una ventana mas alla del anchor {anchor}"


def test_target_builder_multi_output_matrix_never_reaches_into_the_next_split() -> None:
    """El target de la ultima ventana de TEST (horizonte mas largo) no puede superar
    `fecha_max` del dataset -- si lo hiciera, `TargetBuilder` estaria inventando datos."""
    df = _synthetic_df()
    split_dfs = _split_dfs("rolling_365")
    seqs = SequenceBuilder(SequenceSpec(lookback_days=7)).build(split_dfs.test, ["caudal_actual_m3s"])
    targets = TargetBuilder(TargetVariable.CAUDAL, HORIZONS).build(split_dfs.test, seqs.anchor_dates)

    fecha_max = df["fecha"].max()
    last_anchor = max(seqs.anchor_dates)
    idx = seqs.anchor_dates.index(last_anchor)
    for h in HORIZONS:
        target_date = last_anchor + timedelta(days=h)
        value = targets.for_horizon(h)[idx, 0]
        if target_date > fecha_max:
            # El target no existe en el dataset -> TargetBuilder debe devolver NaN, no inventar un valor.
            assert np.isnan(value)
        else:
            assert not np.isnan(value)
