"""Tests de B1.10: NSE como pérdida.

Lo que hay que garantizar es la normalización: el MSE se reescala por la
varianza del target de TRAIN, por horizonte, y esa varianza sale de TRAIN en
cada corrida — no de VAL, no de un estado global.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search import train as train_mod
from rio_search.models import LOSSES, NSELoss, SquaredLoss
from rio_search.train import LOSS_CONFIGS, run_experiment
from rio_search.tests.test_target_param import _ds


def test_es_mse_reescalado_por_varianza():
    rng = np.random.default_rng(3)
    e = rng.normal(size=(50, 3))
    var = np.array([0.25, 1.0, 4.0])
    nse = NSELoss(var, eps=0.0)
    assert np.allclose(nse.value(e), e ** 2 / var)      # broadcast (50,3)/(3,)
    assert np.allclose(nse.grad(e), -2.0 * e / var)


def test_invariante_a_la_escala_del_target():
    """El punto de la normalización: reescalar target y error por la misma
    constante no cambia la pérdida — un horizonte 'grande' no domina el lote."""
    rng = np.random.default_rng(5)
    e, var, s = rng.normal(size=200), 0.7, 40.0
    a = NSELoss(np.array([var]), eps=0.0).value(e)
    b = NSELoss(np.array([var * s ** 2]), eps=0.0).value(e * s)
    assert np.allclose(a, b)


def test_sin_calibrar_es_el_mse_del_proyecto():
    """La instancia del registro global no tiene varianza: pesa 1 y coincide con
    SquaredLoss. La calibración ocurre por corrida, en run_experiment."""
    e = np.linspace(-3, 3, 31)
    assert isinstance(LOSSES["nse"], NSELoss) and LOSSES["nse"].var is None
    assert np.allclose(LOSSES["nse"].value(e), SquaredLoss().value(e))
    assert np.allclose(LOSSES["nse"].grad(e), SquaredLoss().grad(e))
    assert LOSS_CONFIGS["nse_loss"] == ("nse", "none")


def test_run_experiment_calibra_con_la_varianza_de_train():
    """Se captura la instancia que run_experiment construye y se compara su σ²
    contra la varianza real del target estandarizado de TRAIN."""
    capturadas = []
    original = train_mod.NSELoss

    class _Espia(NSELoss):
        def __init__(self, var=None, eps=1e-6):
            super().__init__(var, eps)
            capturadas.append(self)

    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    train_mod.NSELoss = _Espia
    try:
        r = run_experiment(ds, splits, model="linear", loss="nse_loss",
                           epochs=120, evaluar_test=False)
    finally:
        train_mod.NSELoss = original
    assert np.isfinite(r["val"]["mean"]["rmse"])
    var = capturadas[0].var
    assert var is not None and var.shape == (2,)
    pre = train_mod.Preprocessor().fit(ds.X[splits.train], ds.Y[splits.train])
    esperada = np.nanvar(pre.transform_y(ds.Y[splits.train]), axis=0)
    assert np.allclose(var, esperada)


def test_per_horizon_recibe_su_columna():
    """Con per_horizon cada modelo entrena con la σ² de SU horizonte: corre y
    da métricas finitas (un broadcast mal hecho estalla acá)."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, model="linear", loss="nse_loss",
                       per_horizon=True, epochs=120, evaluar_test=False)
    assert np.isfinite(r["val"]["mean"]["rmse"])
    assert r["horizonte"] == "per_horizon"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de nse_loss OK")
