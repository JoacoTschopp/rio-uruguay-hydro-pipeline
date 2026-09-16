"""Tests de las features hidrológicas a mano: API (B2.12) y dinámica del caudal (B2.13).

Las dos celdas son la misma hipótesis — conocimiento del dominio resumido en pocas
columnas le gana a la historia cruda (B2.17 quedó descartada) — así que comparten
archivo. Cada feature nueva se prueba por definición y por **causalidad**: perturbar
el futuro no puede cambiar el valor de hoy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as D


def _df_lluvia(p, count=None):
    p = np.asarray(p, dtype=float)
    n = len(p)
    if count is None:
        count = np.ones(n)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "lluvia_acumulada_mm": p,
        "lluvia_agregado_alta_frontera_station_count": np.asarray(count, dtype=float),
    }, index=idx)


# --------------------------------------------------------------------------
# B2.12 — índice de precipitación antecedente
# --------------------------------------------------------------------------

def test_api_equivale_a_la_suma_geometrica():
    """La recursión ewm tiene que ser exactamente API(t) = Σ k^i · P(t−i)."""
    rng = np.random.default_rng(7)
    p = rng.gamma(0.5, 8.0, size=200)
    out = D._derive_rain(_df_lluvia(p))
    t, k = 120, 0.90
    directo = sum(k ** i * p[t - i] for i in range(t + 1))
    assert np.isclose(out["api_k090"].iloc[t], directo, rtol=1e-9)


def test_api_no_mira_el_futuro():
    p = np.full(100, 2.0)
    q = p.copy()
    q[60:] = 50.0                                    # diluvio, pero mañana
    a = D._derive_rain(_df_lluvia(p))["api_k095"]
    b = D._derive_rain(_df_lluvia(q))["api_k095"]
    assert np.allclose(a.iloc[30:60], b.iloc[30:60])
    assert b.iloc[60] > a.iloc[60]


def test_api_arranque_en_frio_es_nan():
    """Sin 30 días de historia el API inventaría sequía; mejor NaN e imputar."""
    api = D._derive_rain(_df_lluvia(np.ones(50)))["api_k090"]
    assert api.iloc[:30].isna().all()
    assert np.isfinite(api.iloc[30])


def test_api_un_hueco_cuenta_como_dia_seco():
    """station_count=0 deja P en NaN; dentro de la recursión vale 0: el índice
    decae ese día en vez de romperse o congelarse."""
    count = np.ones(60)
    count[40] = 0.0
    api = D._derive_rain(_df_lluvia(np.ones(60), count))["api_k085"]
    assert np.isfinite(api.iloc[40]) and np.isfinite(api.iloc[41])
    assert np.isclose(api.iloc[40], 0.85 * api.iloc[39])


def test_api_decaimientos_ordenados():
    """A igual lluvia, k más grande recuerda más: api_k095 ≥ api_k085 en régimen
    estacionario tras una racha."""
    p = np.zeros(120)
    p[40:80] = 5.0                                   # racha y después seca
    out = D._derive_rain(_df_lluvia(p))
    assert out["api_k095"].iloc[110] > out["api_k085"].iloc[110] >= 0.0


def test_grupo_lluvia_api_declarado():
    assert D.FEATURE_GROUPS["lluvia_api"] == ("api_k085", "api_k090", "api_k095")


# --------------------------------------------------------------------------
# B2.13 — dinámica del caudal
# --------------------------------------------------------------------------

def _df_caudal(q):
    q = np.asarray(q, dtype=float)
    idx = pd.date_range("2020-01-01", periods=len(q), freq="D")
    return pd.DataFrame({"caudal_actual_m3s": q}, index=idx)


def test_log_ratio_por_definicion():
    out = D._derive_flow_dynamics(_df_caudal([100.0, 110.0, 99.0]))
    assert np.isclose(out["caudal_log_ratio_1d"].iloc[1], np.log(110.0 / 100.0))
    assert np.isnan(out["caudal_log_ratio_1d"].iloc[0])


def test_recesion_exponencial_da_pendiente_constante():
    """En Q = Q₀·e^(−t/τ) la pendiente log es −1/τ exacta y la curvatura, cero."""
    tau = 25.0
    t = np.arange(60.0)
    out = D._derive_flow_dynamics(_df_caudal(5000.0 * np.exp(-t / tau)))
    pend = out["caudal_log_pendiente_7d"].iloc[10:]
    assert np.allclose(pend, -1.0 / tau, atol=1e-9)
    assert np.allclose(out["caudal_log_curvatura"].iloc[2:], 0.0, atol=1e-9)


def test_dias_desde_pico_se_confirma_al_dia_siguiente():
    """Pico en t=10; en t=10 todavía no se sabe (sería mirar t=11): NaN hasta
    ahí, 1 en t=11, y sigue contando."""
    q = np.concatenate([np.linspace(100, 200, 11), np.linspace(195, 150, 10)])
    out = D._derive_flow_dynamics(_df_caudal(q))
    d = out["caudal_dias_desde_pico"]
    assert d.iloc[:11].isna().all()
    assert d.iloc[11] == 1.0 and d.iloc[15] == 5.0


def test_dinamica_no_mira_el_futuro():
    """Perturbar el futuro no puede cambiar ninguna columna en el pasado."""
    rng = np.random.default_rng(3)
    q = 1000.0 + np.cumsum(rng.normal(0, 20, 120))
    q2 = q.copy()
    q2[80:] += 5000.0                              # crecida, pero mañana
    a = D._derive_flow_dynamics(_df_caudal(q))
    b = D._derive_flow_dynamics(_df_caudal(q2))
    for col in D.FEATURE_GROUPS["dinamica_caudal"]:
        va, vb = a[col].iloc[:80], b[col].iloc[:80]
        assert ((va == vb) | (va.isna() & vb.isna())).all(), col


def test_caudal_no_positivo_no_rompe_el_log():
    out = D._derive_flow_dynamics(_df_caudal([100.0, 0.0, 120.0]))
    assert np.isnan(out["caudal_log_ratio_1d"].iloc[1])
    assert np.isfinite(out["caudal_actual_m3s"]).all()


def test_grupo_dinamica_declarado():
    assert D.FEATURE_GROUPS["dinamica_caudal"] == (
        "caudal_log_ratio_1d", "caudal_log_curvatura",
        "caudal_log_pendiente_7d", "caudal_dias_desde_pico")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de features hidro OK")
