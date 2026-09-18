"""Tests de la serie diaria de ψ_τ (pedido directo de Joaquín, no una celda).

La garantía central: la serie diaria no es un cálculo paralelo que puede
divergir del `gral` por horizonte ya reportado — es la MISMA aritmética
(`metrics.expectile_se_series`, que `metrics.gral` también usa) vista sin
promediar. `sqrt(media(psi_tau))` de la serie tiene que reproducir `gral`
calculado directo sobre los mismos arrays, bit a bit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search import metrics as metrics_mod
from rio_search.daily_series import _a_serie_larga


def _ds_con_tau_variable(n=120, seed=7):
    """Un Dataset sintético chico, con τ variable (no constante) y dos
    horizontes — lo mínimo para probar la serie diaria sin tocar el snapshot
    real ni entrenar nada.
    """
    rng = np.random.default_rng(seed)
    fecha = pd.date_range("2020-01-01", periods=n, freq="D")
    y1 = 1000.0 + rng.normal(0, 80, n)
    y2 = 1200.0 + rng.normal(0, 90, n)
    Y = np.column_stack([y1, y2])
    tau = np.where(np.arange(n) % 3 == 0, 0.85, np.where(np.arange(n) % 3 == 1, 0.15, 0.5))
    return data_mod.Dataset(fecha=fecha, X=rng.normal(size=(n, 2)), Y=Y, q_actual=y1,
                            tau=tau, feature_names=["a", "b"], horizons=(1, 7), tau_mode="test")


def _val_a_la_mitad(ds):
    va = np.zeros(len(ds), dtype=bool)
    va[len(ds) // 2:] = True
    return type("S", (), {"val": va})()


def test_reproduce_el_gral_por_horizonte_calculado_directo():
    """El chequeo de consistencia central: sqrt(media(psi_tau)) por horizonte
    == gral() calculado sobre los mismos arrays, sin pasar por la serie."""
    ds = _ds_con_tau_variable()
    splits = _val_a_la_mitad(ds)
    rng = np.random.default_rng(1)
    pred = ds.Y + rng.normal(0, 40, ds.Y.shape)   # una predicción cualquiera, con error

    df = _a_serie_larga(ds, splits, pred[splits.val], "modelo_x")

    for j, h in enumerate(ds.horizons):
        esperado = metrics_mod.gral(ds.Y[splits.val, j], pred[splits.val, j], ds.tau[splits.val])
        obtenido = np.sqrt(df.loc[df["horizonte"] == f"h{h:02d}", "psi_tau"].mean())
        assert np.isclose(obtenido, esperado, rtol=0, atol=1e-12), (h, obtenido, esperado)


def test_tau_de_la_serie_coincide_con_el_modulador():
    ds = _ds_con_tau_variable()
    splits = _val_a_la_mitad(ds)
    pred = ds.Y.copy()

    df = _a_serie_larga(ds, splits, pred[splits.val], "modelo_x")

    tau_esperado_por_fecha = dict(zip(ds.fecha[splits.val], ds.tau[splits.val]))
    for _, fila in df.iterrows():
        assert fila["tau"] == tau_esperado_por_fecha[fila["fecha"]]
    # y varía de verdad — no es un valor pegado por accidente
    assert df["tau"].nunique() >= 3


def test_fila_con_prediccion_no_finita_se_descarta_sin_desalinear():
    """Un NaN en una fecha puntual no debe correr las fechas siguientes: la
    fila con NaN desaparece, el resto conserva su (fecha, tau) originales."""
    ds = _ds_con_tau_variable()
    splits = _val_a_la_mitad(ds)
    pred = ds.Y.copy()
    idx_nan = np.flatnonzero(splits.val)[3]
    pred_val = pred[splits.val].copy()
    pred_val[3, 0] = np.nan   # sólo el horizonte 0 (h01) de esa fila

    df = _a_serie_larga(ds, splits, pred_val, "modelo_x")

    fecha_faltante = ds.fecha[idx_nan]
    h01 = df[df["horizonte"] == "h01"]
    h07 = df[df["horizonte"] == "h07"]
    assert fecha_faltante not in set(h01["fecha"])       # se descartó en h01...
    assert fecha_faltante in set(h07["fecha"])            # ...pero no en h07
    assert len(h01) == int(splits.val.sum()) - 1
    assert len(h07) == int(splits.val.sum())


def test_columnas_y_modelo():
    ds = _ds_con_tau_variable()
    splits = _val_a_la_mitad(ds)
    df = _a_serie_larga(ds, splits, ds.Y[splits.val], "mi_modelo")
    assert list(df.columns) == ["modelo", "fecha", "horizonte", "tau", "psi_tau"]
    assert set(df["modelo"]) == {"mi_modelo"}
    assert set(df["horizonte"]) == {"h01", "h07"}
    # sin error, psi_tau es exactamente 0 en toda la serie
    assert (df["psi_tau"] == 0.0).all()


# --------------------------------------------------------------------------
# Integración con datos reales: se salta si no hay snapshot local
# --------------------------------------------------------------------------

def test_serie_real_reproduce_el_ensemble_de_semillas():
    """Sobre el snapshot real: la serie diaria de 'ancla' con 3 semillas tiene
    que reproducir el gral por horizonte que calcularía B10.01 (ensemble de
    esas mismas 3 semillas) — no el promedio-de-métricas de la celda
    individual, que es un número distinto a propósito (ver ensemble.py).
    3 semillas, no 2: el jackknife de `ensemble_semillas` necesita al menos
    2 miembros por pliegue."""
    if not data_mod.DEFAULT_SNAPSHOT.exists():
        return
    from rio_search.daily_series import serie_diaria
    from rio_search.ensemble import ensemble_semillas

    seeds = [20260828, 20260829, 20260830]
    df = serie_diaria("ancla", seeds)
    esperado = ensemble_semillas("gral", seeds)["val"]["per_horizon"]

    for h, bloque in esperado.items():
        obtenido = np.sqrt(df.loc[df["horizonte"] == h, "psi_tau"].mean())
        assert abs(obtenido - bloque["gral"]) < 1e-9, h


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
          if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de daily_series OK")
