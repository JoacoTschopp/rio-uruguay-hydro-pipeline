"""Tests de B4.03: MLP profundo (lista de anchos).

Dos garantías. La de compatibilidad: `hidden=38` y `hidden=[38]` son la MISMA
red, bit a bit — mismos dims y mismo orden de sorteos del rng — así que el ancla
no se mueve por esta generalización. La de corrección: el backward generalizado
a N capas coincide con el gradiente numérico, que es la única autoridad.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search.models import MLPCore, SquaredLoss


def _datos(n=80, n_in=5, n_out=3, seed=7):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, n_in))
    W = rng.normal(size=(n_in, n_out))
    Y = np.tanh(X @ W) + 0.1 * rng.normal(size=(n, n_out))
    return X, Y


def test_un_entero_y_su_lista_son_la_misma_red():
    X, Y = _datos()
    kw = dict(loss=SquaredLoss(), epochs=40, seed=123)
    a = MLPCore(hidden=38, **kw).fit(X, Y)
    b = MLPCore(hidden=[38], **kw).fit(X, Y)
    assert set(a.params) == set(b.params) == {"W1", "b1", "W2", "b2"}
    for k in a.params:
        assert np.array_equal(a.params[k], b.params[k]), k
    assert np.array_equal(a.predict(X), b.predict(X))


def test_backward_profundo_coincide_con_el_gradiente_numerico():
    """Chequeo por diferencias finitas de las 3 capas de una red [7, 5]."""
    X, Y = _datos(n=25, n_in=4, n_out=2)
    m = MLPCore(hidden=[7, 5], loss=SquaredLoss(), seed=99)
    rng = np.random.default_rng(0)
    params = m._init_params(X.shape[1], Y.shape[1], rng)
    mask = np.ones_like(Y, dtype=bool)
    n_valid = mask.sum()

    # La MISMA cantidad que usa fit(): G = loss.grad(e)·mask/n con e = Y − yhat.
    # loss.grad ya devuelve ∂value/∂yhat (−2e en el MSE), así que backward(G)
    # es directamente dL/dW y debe coincidir con la derivada numérica.
    yhat, cache = m._forward(X, params)
    G_fit = m.loss.grad(Y - yhat) * mask / n_valid
    grads = m._backward(X, cache, G_fit, params)

    def perdida(p):
        yh, _ = m._forward(X, p)
        return float(np.sum(m.loss.value(Y - yh)) / n_valid)

    eps = 1e-6
    for k in sorted(params):
        g_num = np.zeros_like(params[k])
        it = np.nditer(params[k], flags=["multi_index"])
        for _ in it:
            i = it.multi_index
            p2 = {kk: vv.copy() for kk, vv in params.items()}
            p2[k][i] += eps
            up = perdida(p2)
            p2[k][i] -= 2 * eps
            down = perdida(p2)
            g_num[i] = (up - down) / (2 * eps)
        assert np.allclose(grads[k], g_num, atol=1e-6), k


def test_tres_capas_entrena_y_baja_la_perdida():
    X, Y = _datos(n=120)
    m = MLPCore(hidden=[16, 16, 16], loss=SquaredLoss(), epochs=150, seed=5)
    m.fit(X, Y)
    assert set(m.params) == {f"{w}{i}" for i in (1, 2, 3, 4) for w in ("W", "b")}
    assert m._weight_keys() == ("W1", "W2", "W3", "W4")
    assert m.history[-1]["train_loss"] < 0.5 * m.history[0]["train_loss"]


def test_anchos_invalidos_fallan_temprano():
    for malo in ([], [0], [16, -1]):
        try:
            MLPCore(hidden=malo, loss=SquaredLoss())
        except ValueError:
            continue
        raise AssertionError(f"hidden={malo!r} debería fallar")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de MLP profundo OK")
