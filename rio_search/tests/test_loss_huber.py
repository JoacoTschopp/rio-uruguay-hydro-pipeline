"""Tests de B1.07: pérdida de Huber.

La garantía central es de compatibilidad: en la rama cuadrática Huber ES el MSE
del proyecto (e², no ½e²), así los hiperparámetros del ancla significan lo mismo
al cambiar de pérdida. δ = 1,345 se declara a priori — no sale de VAL.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search.models import LOSSES, HuberLoss, SquaredLoss
from rio_search.train import LOSS_CONFIGS, run_experiment
from rio_search.tests.test_target_param import _ds


def test_rama_cuadratica_es_el_mse_del_proyecto():
    h, m = HuberLoss(delta=1.345), SquaredLoss()
    e = np.linspace(-1.3, 1.3, 41)
    assert np.allclose(h.value(e), m.value(e))
    assert np.allclose(h.grad(e), m.grad(e))


def test_rama_lineal_acota_el_gradiente_y_empalma_continuo():
    d = 1.345
    h = HuberLoss(delta=d)
    e = np.array([-10.0, -2.0, 2.0, 10.0])
    assert np.allclose(h.value(e), 2.0 * d * np.abs(e) - d ** 2)
    assert np.allclose(np.abs(h.grad(e)), 2.0 * d)      # capado: el pico no manda
    # Continuidad C1 en el empalme |e| = δ: mismo valor y mismo gradiente
    eps = 1e-9
    assert abs(h.value(np.array([d - eps]))[0] - h.value(np.array([d + eps]))[0]) < 1e-6
    assert abs(h.grad(np.array([d - eps]))[0] - h.grad(np.array([d + eps]))[0]) < 1e-6


def test_registrada_con_delta_declarado():
    assert LOSS_CONFIGS["huber"] == ("huber", "none")
    assert LOSS_CONFIGS["huber_log"] == ("huber", "log")
    assert isinstance(LOSSES["huber"], HuberLoss)
    assert LOSSES["huber"].delta == 1.345


def test_run_experiment_corre_huber_log():
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, model="linear", loss="huber_log",
                       epochs=120, evaluar_test=False)
    assert np.isfinite(r["val"]["mean"]["rmse"])
    assert r["elementwise_loss"] == "huber" and r["target_transform"] == "log"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de huber OK")
