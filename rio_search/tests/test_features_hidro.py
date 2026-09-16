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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de features hidro OK")
