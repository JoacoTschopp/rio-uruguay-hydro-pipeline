"""Tests de `train_tau` (B1.06): τ constante al entrenar, modulador intacto al medir."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search.train import run_experiment


def _ds(n=900, seed=3):
    rng = np.random.default_rng(seed)
    fecha = pd.date_range("2018-01-01", periods=n, freq="D")
    x = rng.normal(size=(n, 3))
    y = 1000.0 + 200.0 * x[:, 0] + rng.normal(0, 50, n)
    Y = np.repeat(y.reshape(-1, 1), 2, axis=1)
    return data_mod.Dataset(fecha=fecha, X=x, Y=Y, q_actual=y,
                            tau=np.full(n, 0.85), feature_names=["a", "b", "c"],
                            horizons=(1, 2), tau_mode="test")


def test_tau_constante_cambia_el_entrenamiento():
    """Entrenar con τ = 0,15 tiene que sesgar hacia abajo respecto de τ = 0,85."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    kw = dict(model="linear", loss="gral", epochs=120, evaluar_test=False)
    alto = run_experiment(ds, splits, **kw)                              # entrena con ds.tau = 0,85
    bajo = run_experiment(ds, splits, train_tau=np.full(len(ds), 0.15), **kw)
    # pbias = sesgo porcentual: τ alto empuja a sobrestimar, τ bajo a subestimar
    assert bajo["val"]["mean"]["pbias"] < alto["val"]["mean"]["pbias"]
    assert bajo["train_tau_es_el_del_modulador"] is False
    assert alto["train_tau_es_el_del_modulador"] is True


def test_tau_constante_no_toca_la_evaluacion():
    """Las dos corridas se miden con el mismo ds.tau: mismos días húmedos en V+."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    kw = dict(model="linear", loss="gral", epochs=40, evaluar_test=False)
    r = run_experiment(ds, splits, train_tau=np.full(len(ds), 0.5), **kw)
    # con ds.tau = 0,85 todos los días son húmedos: V+ está definido y V− no existe
    m = r["val"]["per_horizon"]["h01"]
    assert np.isfinite(m["v_plus"])
    assert not np.isfinite(m["v_minus"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de train_tau OK")
