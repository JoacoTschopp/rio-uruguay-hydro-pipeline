"""Tests offline (sin Databricks ni red) de `calibration.py`: aritmetica de horizontes,
agregacion por sub-cuenca y calculo/aplicacion del sesgo. Usa DataFrames sinteticos
construidos a mano, no datos reales -- la verificacion contra datos reales de Bronze vive
en `run_calibration_check.py` (Decision 035).

Uso:
    python -m pytest notebooks_local/forecast_calibration/test_calibration.py -v
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import calibration as m


# ---------------------------------------------------------------------------
# horizon_steps
# ---------------------------------------------------------------------------

def test_horizon_steps_h1_uses_zero_as_previous():
    assert m.horizon_steps(1) == (0, 24)


def test_horizon_steps_h7():
    assert m.horizon_steps(7) == (144, 168)


def test_horizon_steps_h14_skips_intermediate_days():
    # t+14 es el incremento entre el dia 13 y el dia 14, no el acumulado de toda la semana 2
    assert m.horizon_steps(14) == (312, 336)


def test_horizon_steps_rejects_undefined_horizon():
    with pytest.raises(ValueError, match="Decision 019"):
        m.horizon_steps(8)


# ---------------------------------------------------------------------------
# daily_horizon_precip
# ---------------------------------------------------------------------------

def _cumulative_point_df(run_date="2010-01-01", lat=-27.0, lon=-53.5, subcuenca_id=1,
                          subcuenca_nombre="alta_frontera", daily_mm=None):
    """Un solo punto de grilla, series cumulativa construida a partir de precipitaciones
    diarias conocidas (daily_mm: dict horizon->mm), para poder aserter el roundtrip exacto."""
    if daily_mm is None:
        daily_mm = {1: 5.0, 2: 0.0, 3: 12.5, 4: 0.0, 5: 0.0, 6: 3.0, 7: 1.5, 14: 8.0}
    rows = []
    cum = 0.0
    # dias 1..7 consecutivos
    for h in range(1, 8):
        cum += daily_mm[h]
        rows.append({"run_date": run_date, "latitude": lat, "longitude": lon,
                     "subcuenca_id": subcuenca_id, "subcuenca_nombre": subcuenca_nombre,
                     "step_hours": h * 24, "tp_mm": cum})
    # relleno arbitrario para los dias 8..13 (no se usan, pero estan en la fuente real)
    cum_13 = cum + 20.0  # lo que haya llovido entre el dia 7 y el dia 13, no importa el valor
    rows.append({"run_date": run_date, "latitude": lat, "longitude": lon,
                 "subcuenca_id": subcuenca_id, "subcuenca_nombre": subcuenca_nombre,
                 "step_hours": 312, "tp_mm": cum_13})
    rows.append({"run_date": run_date, "latitude": lat, "longitude": lon,
                 "subcuenca_id": subcuenca_id, "subcuenca_nombre": subcuenca_nombre,
                 "step_hours": 336, "tp_mm": cum_13 + daily_mm[14]})
    return pd.DataFrame(rows)


def test_daily_horizon_precip_recovers_known_daily_values():
    daily_mm = {1: 5.0, 2: 0.0, 3: 12.5, 4: 0.0, 5: 0.0, 6: 3.0, 7: 1.5, 14: 8.0}
    df = _cumulative_point_df(daily_mm=daily_mm)
    out = m.daily_horizon_precip(df)
    got = dict(zip(out["horizon_days"], out["precip_mm"]))
    for h, expected in daily_mm.items():
        assert got[h] == pytest.approx(expected), f"horizonte {h}"


def test_daily_horizon_precip_drops_points_outside_subcuenca():
    df = _cumulative_point_df(subcuenca_nombre=None)
    out = m.daily_horizon_precip(df)
    assert out.empty


def test_daily_horizon_precip_clips_negative_to_zero():
    # cumulativo no monotono (dato sucio): dia 2 "llueve negativo" -- debe clampear a 0, no propagar negativos
    df = _cumulative_point_df(daily_mm={1: 5.0, 2: -3.0, 3: 12.5, 4: 0.0, 5: 0.0, 6: 3.0, 7: 1.5, 14: 8.0})
    out = m.daily_horizon_precip(df)
    row = out[out["horizon_days"] == 2].iloc[0]
    assert row["precip_mm"] == 0.0


def test_daily_horizon_precip_point_missing_only_h14_step_keeps_other_horizons():
    # Simula el gotcha real de GEFS: la grilla 0,5 grados del tramo Days:10-16 es SUBCONJUNTO
    # de la 0,25 grados -- un punto de un miembro perturbado puede tener steps 24..168 (tramo
    # fino) pero no 312/336 (tramo grueso), mientras OTRO punto de la misma corrida si los
    # tiene. La columna step=336 existe en el pivot (por el segundo punto) pero con NaN para
    # el primero -- ese es el caso que rompia n_points antes del fix.
    df_full = _cumulative_point_df(lat=-27.0, lon=-53.5)
    df_partial = _cumulative_point_df(lat=-27.25, lon=-53.5)
    df_partial = df_partial[~df_partial["step_hours"].isin([312, 336])]
    df = pd.concat([df_full, df_partial], ignore_index=True)

    out = m.daily_horizon_precip(df)
    assert out["precip_mm"].isna().sum() == 0
    h14 = out[out["horizon_days"] == 14]
    assert len(h14) == 1  # solo el punto completo aporta al horizonte 14
    h1 = out[out["horizon_days"] == 1]
    assert len(h1) == 2  # ambos puntos aportan a los horizontes 1..7


def test_daily_horizon_precip_missing_step_excludes_only_that_horizon():
    df = _cumulative_point_df()
    df = df[df["step_hours"] != 96]  # falta el step del dia 4
    out = m.daily_horizon_precip(df)
    horizons_present = set(out["horizon_days"])
    # dia 4 (necesita step 96) y dia 5 (necesita step 96 como "previo") deberian faltar
    assert 4 not in horizons_present
    assert 5 not in horizons_present
    assert {1, 2, 3, 6, 7, 14}.issubset(horizons_present)


# ---------------------------------------------------------------------------
# aggregate_by_subcuenca
# ---------------------------------------------------------------------------

def test_aggregate_by_subcuenca_averages_points():
    daily = pd.DataFrame(
        {
            "run_date": ["2010-01-01"] * 4,
            "subcuenca_nombre": ["alta_frontera"] * 4,
            "horizon_days": [1, 1, 1, 1],
            "precip_mm": [10.0, 20.0, 0.0, 30.0],
        }
    )
    out = m.aggregate_by_subcuenca(daily)
    assert len(out) == 1
    assert out.iloc[0]["precip_mm"] == pytest.approx(15.0)
    assert out.iloc[0]["n_points"] == 4


def test_aggregate_by_subcuenca_keeps_subcuencas_and_horizons_separate():
    daily = pd.DataFrame(
        {
            "run_date": ["2010-01-01"] * 4,
            "subcuenca_nombre": ["alta_frontera", "alta_frontera", "intermedia_paso_libres", "intermedia_paso_libres"],
            "horizon_days": [1, 2, 1, 2],
            "precip_mm": [10.0, 5.0, 100.0, 50.0],
        }
    )
    out = m.aggregate_by_subcuenca(daily)
    assert len(out) == 4


# ---------------------------------------------------------------------------
# compute_bias_table / apply_bias
# ---------------------------------------------------------------------------

def _agg_df(run_dates, subcuenca, horizon, values):
    return pd.DataFrame(
        {
            "run_date": run_dates,
            "subcuenca_nombre": subcuenca,
            "horizon_days": horizon,
            "precip_mm": values,
            "n_points": 1,
        }
    )


def test_compute_bias_table_additive_matches_hand_computed_mean_diff():
    run_dates = ["2010-01-01", "2010-01-02", "2010-01-03"]
    gefs = _agg_df(run_dates, "alta_frontera", 1, [0.0, 5.0, 10.0])
    tigge = _agg_df(run_dates, "alta_frontera", 1, [2.0, 5.0, 20.0])
    bias = m.compute_bias_table(gefs, tigge, method="additive")
    assert len(bias) == 1
    row = bias.iloc[0]
    # diffs: 2, 0, 10 -> media 4.0
    assert row["bias_mm"] == pytest.approx(4.0)
    assert row["n_days"] == 3
    assert row["mean_gefs_mm"] == pytest.approx(5.0)
    assert row["mean_tigge_mm"] == pytest.approx(9.0)


def test_compute_bias_table_only_uses_overlapping_dates():
    gefs = _agg_df(["2010-01-01", "2010-01-02", "2010-01-03"], "alta_frontera", 1, [1.0, 1.0, 1.0])
    tigge = _agg_df(["2010-01-02", "2010-01-03", "2010-01-04"], "alta_frontera", 1, [5.0, 5.0, 5.0])
    bias = m.compute_bias_table(gefs, tigge, method="additive")
    # solo 01-02 y 01-03 se solapan -> n_days=2, no 3 ni 4
    assert bias.iloc[0]["n_days"] == 2
    assert bias.iloc[0]["bias_mm"] == pytest.approx(4.0)


def test_compute_bias_table_empty_overlap_returns_empty_df():
    gefs = _agg_df(["2010-01-01"], "alta_frontera", 1, [1.0])
    tigge = _agg_df(["2010-01-02"], "alta_frontera", 1, [5.0])
    bias = m.compute_bias_table(gefs, tigge)
    assert bias.empty


def test_compute_bias_table_multiplicative_uses_ratio_of_sums_not_mean_of_ratios():
    # dia con gefs=0 rompería una media de cocientes por division por cero; el metodo
    # multiplicativo usa cociente de sumas para evitarlo
    run_dates = ["2010-01-01", "2010-01-02"]
    gefs = _agg_df(run_dates, "alta_frontera", 1, [0.0, 10.0])
    tigge = _agg_df(run_dates, "alta_frontera", 1, [5.0, 15.0])
    bias = m.compute_bias_table(gefs, tigge, method="multiplicative")
    # suma tigge=20, suma gefs=10 -> factor 2.0
    assert bias.iloc[0]["factor"] == pytest.approx(2.0)


def test_apply_bias_additive_shifts_and_clips_at_zero():
    gefs_agg = _agg_df(["2010-01-01", "2010-01-02"], "alta_frontera", 1, [0.0, 10.0])
    bias_table = pd.DataFrame(
        {
            "subcuenca_nombre": ["alta_frontera"],
            "horizon_days": [1],
            "method": ["additive"],
            "bias_mm": [-3.0],  # GEFS sobreestima 3mm en promedio
            "factor": [np.nan],
            "n_days": [10],
            "mean_gefs_mm": [5.0],
            "mean_tigge_mm": [2.0],
        }
    )
    out = m.apply_bias(gefs_agg, bias_table, method="additive")
    assert out.loc[out["run_date"] == "2010-01-01", "precip_calibrado_mm"].iloc[0] == pytest.approx(0.0)  # 0 - 3 clippeado a 0
    assert out.loc[out["run_date"] == "2010-01-02", "precip_calibrado_mm"].iloc[0] == pytest.approx(7.0)  # 10 - 3
    assert out["calibrado"].all()


def test_apply_bias_leaves_uncalibrated_combos_untouched_and_flagged():
    gefs_agg = _agg_df(["2010-01-01"], "baja_salto_grande", 3, [7.0])
    bias_table = pd.DataFrame(
        columns=["subcuenca_nombre", "horizon_days", "method", "bias_mm", "factor", "n_days",
                 "mean_gefs_mm", "mean_tigge_mm"]
    )
    out = m.apply_bias(gefs_agg, bias_table, method="additive")
    assert out.iloc[0]["precip_calibrado_mm"] == pytest.approx(7.0)
    assert out.iloc[0]["calibrado"] == False  # noqa: E712


def test_apply_bias_multiplicative():
    gefs_agg = _agg_df(["2010-01-01"], "alta_frontera", 1, [10.0])
    bias_table = pd.DataFrame(
        {
            "subcuenca_nombre": ["alta_frontera"],
            "horizon_days": [1],
            "method": ["multiplicative"],
            "bias_mm": [np.nan],
            "factor": [1.5],
            "n_days": [5],
            "mean_gefs_mm": [4.0],
            "mean_tigge_mm": [6.0],
        }
    )
    out = m.apply_bias(gefs_agg, bias_table, method="multiplicative")
    assert out.iloc[0]["precip_calibrado_mm"] == pytest.approx(15.0)
