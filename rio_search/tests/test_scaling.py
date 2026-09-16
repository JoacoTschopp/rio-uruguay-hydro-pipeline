"""Tests de B7.02: escalado de features desacoplado del estándar.

Dos garantías: (1) `standard` sigue siendo bit a bit lo que era — el ancla no se
mueve por accidente; (2) cada escalado alternativo hace lo que dice su fórmula,
con los estadísticos salidos de TRAIN y sin romperse en columnas casi constantes
(las banderas de calidad tienen IQR = 0).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search import train as train_mod
from rio_search.train import Preprocessor, run_experiment
from rio_search.tests.test_target_param import _ds, KW


def _xy(n=500, f=4, seed=13):
    rng = np.random.default_rng(seed)
    X = rng.lognormal(1.0, 1.0, size=(n, f))          # cola pesada, como el caudal
    Y = rng.normal(1000.0, 100.0, size=(n, 2))
    return X, Y


def test_standard_es_el_de_siempre():
    """El default no puede cambiar: mismo resultado que la fórmula (X−μ)/σ que
    usaba el Preprocessor antes de que existiera `scaling`."""
    X, Y = _xy()
    pre = Preprocessor().fit(X, Y)
    esperado = (X - X.mean(axis=0)) / X.std(axis=0)
    assert np.allclose(pre.transform_x(X), esperado)
    assert pre.scaling == "standard"


def test_robust_es_mediana_iqr():
    X, Y = _xy()
    pre = Preprocessor(scaling="robust").fit(X, Y)
    q25, q50, q75 = np.percentile(X, [25.0, 50.0, 75.0], axis=0)
    assert np.allclose(pre.transform_x(X), (X - q50) / (q75 - q25))


def test_robust_no_estalla_con_iqr_cero():
    """Una bandera que casi siempre vale 0 tiene IQR = 0: el divisor cae a 1 y
    la columna sale centrada, no infinita."""
    X, Y = _xy()
    X[:, 0] = 0.0
    X[::50, 0] = 1.0                                   # 2 % de unos: IQR = 0
    pre = Preprocessor(scaling="robust").fit(X, Y)
    z = pre.transform_x(X)
    assert np.isfinite(z).all()
    assert np.allclose(pre.x_scale[0], 1.0)


def test_quantile_mapea_a_uniforme_y_recorta_fuera_de_rango():
    X, Y = _xy()
    pre = Preprocessor(scaling="quantile").fit(X, Y)
    z = pre.transform_x(X)
    assert abs(float(z.mean())) < 0.01                 # uniforme centrada en 0
    assert z.min() >= -0.5 and z.max() <= 0.5
    # Fuera del rango de TRAIN se recorta al extremo de la CDF de puntos medios:
    # el mismo valor que recibe el máximo de TRAIN, no más.
    fuera = np.full((1, X.shape[1]), X.max() * 10)
    assert np.allclose(pre.transform_x(fuera), z.max())


def test_los_estadisticos_salen_solo_de_train():
    """Espejo del test de B7.01: refittear con otras filas cambia el escalado,
    pero transformar filas nuevas con un `pre` ya ajustado no lo toca."""
    X, Y = _xy()
    pre = Preprocessor(scaling="robust").fit(X[:250], Y[:250])
    centro = pre.x_center.copy()
    pre.transform_x(X[250:] * 100.0)
    assert np.array_equal(pre.x_center, centro)


def test_run_experiment_corre_con_cada_scaling():
    """Humo de punta a punta: cada opción entrena y da métricas finitas, y una
    opción inexistente se rechaza con nombre y opciones en el error."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    for s in train_mod.SCALINGS:
        r = run_experiment(ds, splits, scaling=s, **KW)
        assert np.isfinite(r["val"]["mean"]["rmse"]), s
        assert r["scaling"] == s
    try:
        run_experiment(ds, splits, scaling="zscore", **KW)
    except ValueError as e:
        assert "zscore" in str(e)
    else:
        raise AssertionError("un scaling inexistente tiene que fallar fuerte")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de scaling OK")
