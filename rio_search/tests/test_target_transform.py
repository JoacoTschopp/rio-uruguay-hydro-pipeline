"""Tests de B3.03: transformaciones del target desacopladas de la pérdida.

Dos garantías: (1) toda transformación invierte exacto — el entrenamiento puede
ocurrir en el espacio que sea, pero lo que se evalúa es caudal en m³/s; (2) la
λ de Box-Cox / Yeo-Johnson sale de TRAIN por máxima verosimilitud, no de una
elección a ojo ni de datos que el modelo no debería ver.
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
from rio_search.train import (Preprocessor, run_experiment,
                              _ajustar_lambda, _yeojohnson, _yeojohnson_inv)
from rio_search.tests.test_target_param import _ds, _CoreCero, KW


def test_ida_y_vuelta_exacta_en_todas():
    """transform_y → inverse_y tiene que devolver el target original, para las
    cinco transformaciones, con λ arbitraria donde aplique. Los datos van bien
    por encima de Q_FLOOR = 100: debajo del piso las transformaciones positivas
    recortan a propósito, y eso no es un error de inversión."""
    rng = np.random.default_rng(7)
    Y = np.exp(rng.normal(7.5, 0.5, size=(400, 2)))          # caudal-like, ≫ 100
    X = rng.normal(size=(400, 3))
    for t in train_mod.TARGET_TRANSFORMS:
        pre = Preprocessor(target_transform=t, target_lambda=0.7).fit(X, Y)
        back = pre.inverse_y(pre.transform_y(Y))
        assert np.allclose(back, Y, rtol=1e-8), t


def test_yeojohnson_invierte_tambien_negativos():
    """La única de la familia definida en toda la recta: un delta cabe entero."""
    rng = np.random.default_rng(11)
    y = rng.normal(0.0, 300.0, size=1000)                    # mitad negativo
    for lam in (-0.5, 0.0, 0.7, 1.0, 2.0):
        back = _yeojohnson_inv(_yeojohnson(y, lam), lam)
        assert np.allclose(back, y, rtol=1e-8, atol=1e-8), lam


def test_lambda_recupera_la_forma_conocida():
    """MLE de manual: sobre datos lognormales la λ óptima es ~0 (el log); sobre
    datos ya gaussianos es ~1 (no tocar)."""
    rng = np.random.default_rng(5)
    lognormal = np.exp(rng.normal(7.0, 1.0, 20000))
    gauss = rng.normal(1000.0, 50.0, 20000)
    assert abs(_ajustar_lambda(lognormal, "boxcox", 1.0)) <= 0.25
    assert _ajustar_lambda(gauss, "boxcox", 1.0) >= 0.5
    assert abs(_ajustar_lambda(lognormal, "yeojohnson", 1.0)) <= 0.25


def test_identidad_reproduce_al_acoplado():
    """El override con el MISMO valor que fija la pérdida no puede cambiar ni un
    bit del resultado: si la inversa estuviera rota, esta igualdad estalla."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    a = run_experiment(ds, splits, **KW)                            # mse → none
    b = run_experiment(ds, splits, target_transform="none", **KW)
    assert a["val"]["mean"]["rmse"] == b["val"]["mean"]["rmse"]
    c = run_experiment(ds, splits, model="linear", loss="mse_log",
                       epochs=120, evaluar_test=False)              # mse_log → log
    d = run_experiment(ds, splits, model="linear", loss="mse_log",
                       target_transform="log", epochs=120, evaluar_test=False)
    assert c["val"]["mean"]["rmse"] == d["val"]["mean"]["rmse"]


def test_pow4_evalua_en_espacio_original():
    """Con el core nulo, la predicción es (media de Y^(1/4) en TRAIN)^4 y las
    métricas se calculan contra ds.Y en m³/s. Una inversa mal hecha no puede
    reproducir este número."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    original = train_mod.LinearCore
    train_mod.LinearCore = _CoreCero
    try:
        r = run_experiment(ds, splits, target_transform="pow4", **KW)
    finally:
        train_mod.LinearCore = original
    mu = float(np.nanmean(np.power(ds.Y[splits.train], 0.25)))
    pred = np.full(splits.val.sum() if splits.val.dtype == bool else len(ds.Y[splits.val]),
                   mu ** 4)
    esperado = metrics_mod.evaluate(ds.Y[splits.val][:, 0], pred,
                                    ds.tau[splits.val])["rmse"]
    assert abs(r["val"]["per_horizon"]["h01"]["rmse"] - esperado) < 1e-9


def test_delta_admite_yeojohnson():
    """El delta rechaza log/pow4/boxcox (positividad) pero Yeo-Johnson sí lo
    acepta: la combinación corre y da métricas finitas."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, target_param="delta",
                       target_transform="yeojohnson", **KW)
    assert np.isfinite(r["val"]["mean"]["rmse"])
    assert r["target_lambda"] is not None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de target_transform OK")
