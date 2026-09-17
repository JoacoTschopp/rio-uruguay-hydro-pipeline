"""Tests de B4.08: XGBoost con objetivo custom (grad/hess analíticos de ExpectileLoss).

La garantía central no es que XGBoost gane, sino dos cosas de las que depende
que la comparación sea honesta: (1) el objetivo custom reproduce exactamente
`ExpectileLoss` — no una aproximación cuadrática — y (2) el criterio de parada
temprana mira esa misma pérdida asimétrica en VAL, no un RMSE simétrico que no
ve la asimetría que se está entrenando.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

xgboost = pytest.importorskip("xgboost")

from rio_search import data as data_mod
from rio_search.models import ExpectileLoss, SquaredLoss, XGBoostCore
from rio_search.train import run_experiment
from rio_search.tests.test_target_param import _ds


def test_objetivo_custom_coincide_con_expectile_loss():
    """grad/hess de XGBoostCore ES ExpectileLoss.grad, no una aproximación."""
    loss = ExpectileLoss()
    rng = np.random.default_rng(0)
    tau = rng.uniform(0.2, 0.8, size=200)
    preds = rng.normal(1000, 100, size=200)
    y = preds + rng.normal(0, 50, size=200)
    e = y - preds

    obj = XGBoostCore._objective(tau)
    dmat = xgboost.DMatrix(np.zeros((200, 1)), label=y)
    grad, hess = obj(preds, dmat)

    # DMatrix guarda el label en float32: comparar contra ESA versión (no el `e`
    # en float64 de arriba), si no la comparación queda limitada por el redondeo
    # de precisión en vez de por la fórmula.
    e_efectiva = dmat.get_label().astype(np.float64) - preds
    assert np.allclose(grad, loss.grad(e_efectiva, tau))
    # hess numérico: perturbar la predicción y comparar contra el analítico
    eps = 1e-3
    grad_mas, _ = obj(preds + eps, dmat)
    hess_numerico = (grad_mas - grad) / eps
    assert np.allclose(hess, hess_numerico, atol=1e-2)
    assert np.all(hess > 0)          # w = τ o 1−τ, ambos en (0,1): hess siempre positivo


def test_custom_metric_reproduce_el_valor_de_la_perdida():
    loss = ExpectileLoss()
    tau = np.full(50, 0.7)
    y = np.full(50, 1000.0)
    preds = y - 25.0        # e = 25 > 0 en todas las filas
    dmat = xgboost.DMatrix(np.zeros((50, 1)), label=y)

    core = XGBoostCore(loss=loss)
    feval = core._custom_metric(dmat, tau)
    nombre, valor = feval(preds, dmat)
    assert nombre == "expectile"
    assert np.isclose(valor, float(np.mean(loss.value(y - preds, tau))))


def test_solo_acepta_expectile():
    with pytest.raises(NotImplementedError):
        XGBoostCore(loss=SquaredLoss())


def test_no_soporta_podado_por_epoca():
    core = XGBoostCore(loss=ExpectileLoss(), epochs=10)
    X = np.zeros((20, 2))
    Y = np.ones((20, 1))
    with pytest.raises(NotImplementedError):
        core.fit(X, Y, tau=np.full(20, 0.5), on_epoch=lambda *a: True)


def test_fit_predict_multi_salida_un_booster_por_columna():
    ds = _ds(n=600)
    splits = data_mod.make_splits(ds.fecha, test_days=60, val_days=120)
    tr, va = splits.train, splits.val

    core = XGBoostCore(loss=ExpectileLoss(), epochs=25, patience=5, max_depth=2)
    core.fit(ds.X[tr], ds.Y[tr], tau=ds.tau[tr],
             X_val=ds.X[va], Y_val=ds.Y[va], tau_val=ds.tau[va])

    assert len(core.boosters) == 2                  # un booster por horizonte
    assert len(core.history) == 2
    assert isinstance(core.best_epoch, list) and len(core.best_epoch) == 2

    pred = core.predict(ds.X[va])
    assert pred.shape == (va.sum(), 2)
    assert np.all(np.isfinite(pred))


def test_fit_respeta_nan_por_columna():
    ds = _ds(n=400)
    Y = ds.Y.copy()
    Y[:30, 0] = np.nan                               # sin target en la primera columna
    splits = data_mod.make_splits(ds.fecha, test_days=40, val_days=80)
    tr, va = splits.train, splits.val

    core = XGBoostCore(loss=ExpectileLoss(), epochs=15, patience=5, max_depth=2)
    core.fit(ds.X[tr], Y[tr], tau=ds.tau[tr], X_val=ds.X[va], Y_val=Y[va], tau_val=ds.tau[va])
    pred = core.predict(ds.X[va])
    assert np.all(np.isfinite(pred))                 # entrenó igual, sin romperse


def test_run_experiment_corre_xgb_con_gral():
    ds = _ds(n=700)
    splits = data_mod.make_splits(ds.fecha, test_days=60, val_days=140)
    r = run_experiment(ds, splits, model="xgb", loss="gral", epochs=25, patience=5,
                       evaluar_test=False)
    assert np.isfinite(r["val"]["mean"]["rmse"])
    assert r["elementwise_loss"] == "expectile" and r["target_transform"] == "log"
    assert "model_hp" in r and r["model_hp"]["max_depth"] == 4      # default declarado


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de XGBoostCore OK")
