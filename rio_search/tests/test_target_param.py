"""Tests de B3.04: target diferencial — el modelo predice Q(t+h) − Q(t).

Lo que hay que garantizar no es que delta gane, sino que la contabilidad sea
exacta: el entrenamiento ocurre en el espacio del cambio, pero la evaluación
ocurre SIEMPRE en m³/s contra el caudal observado, reconstruyendo con el
q_actual del mismo día.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search import metrics as metrics_mod
from rio_search import train as train_mod
from rio_search.train import run_experiment


def _ds(n=900, seed=3, escalas=(1.0, 3.0)):
    rng = np.random.default_rng(seed)
    fecha = pd.date_range("2018-01-01", periods=n, freq="D")
    x = rng.normal(size=(n, 3))
    y = 1000.0 + 200.0 * x[:, 0] + rng.normal(0, 50, n)
    Y = np.column_stack([y * e for e in escalas])
    return data_mod.Dataset(fecha=fecha, X=x, Y=Y, q_actual=y,
                            tau=np.full(n, 0.85), feature_names=["a", "b", "c"],
                            horizons=(1, 2), tau_mode="test")


KW = dict(model="linear", loss="mse", epochs=120, evaluar_test=False)


class _CoreCero:
    """Un 'modelo' que predice siempre 0 en el espacio estandarizado: su inversa
    es exactamente la media del target de TRAIN, y eso deja la aritmética de la
    reconstrucción sin ningún lugar donde esconderse."""

    def __init__(self, **kw):
        self.history, self.best_epoch, self.pruned = [0.0], 0, False

    def fit(self, X, Y, **kw):
        self._nout = Y.shape[1]
        return self

    def predict(self, X):
        return np.zeros((len(X), self._nout))


def test_reconstruye_sumando_q_actual():
    """Con el core nulo, la predicción en m³/s tiene que ser q_actual + media(Δ
    de TRAIN), y las métricas tienen que salir de compararla contra ds.Y en el
    espacio original — no contra el delta."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    original = train_mod.LinearCore
    train_mod.LinearCore = _CoreCero
    try:
        r = run_experiment(ds, splits, target_param="delta", **KW)
    finally:
        train_mod.LinearCore = original

    delta = ds.Y - ds.q_actual[:, None]
    mu = float(np.nanmean(delta[splits.train]))        # fit aplana los horizontes
    pred = np.maximum(ds.q_actual[splits.val] + mu, 0.0)   # igual en ambos horizontes
    for j, h in enumerate(("h01", "h02")):
        esperado = metrics_mod.evaluate(ds.Y[splits.val][:, j], pred,
                                        ds.tau[splits.val])["rmse"]
        assert abs(r["val"]["per_horizon"][h]["rmse"] - esperado) < 1e-9, h


def test_delta_no_admite_transform_log():
    """log(Δ) no existe para un río que baja. Mejor negarse que devolver NaN."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    try:
        run_experiment(ds, splits, loss="gral", target_param="delta",
                       model="linear", epochs=10, evaluar_test=False)
    except ValueError:
        return
    raise AssertionError("delta + transformación log tenía que levantar ValueError")


def test_target_param_desconocido_levanta():
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    try:
        run_experiment(ds, splits, target_param="ratio", **KW)
    except ValueError:
        return
    raise AssertionError("ratio es B3.05: mientras no exista, tiene que negarse")


def test_el_default_sigue_siendo_nivel():
    """Regresión: sin el kwarg, nada cambia y la bitácora lo dice."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, **KW)
    assert r["target_param"] == "nivel"
    r2 = run_experiment(ds, splits, target_param="delta", **KW)
    assert r2["target_param"] == "delta"
    assert np.isfinite(r2["val"]["mean"]["rmse"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de target_param OK")
