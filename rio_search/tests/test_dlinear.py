"""Tests de B4.13: DLinear (descomposición tendencia+estacional + capa lineal).

Cuatro garantías: la descomposición reconstruye exacto (trend + seasonal == seq),
la media móvil es causal-segura (no mira fuera de la ventana ya recortada por
`make_sequences`), el backward coincide con el gradiente numérico, y la
integración con `run_experiment` vía `--model dlinear --lookback L` funciona
de punta a punta sin torch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search.models import DLinearCore, SquaredLoss


def _seq(n=40, L=10, F=3, seed=7):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n, L, F)), rng


def test_trend_mas_seasonal_reconstruye_la_ventana_exacta():
    seq, _ = _seq()
    n, L, F = seq.shape
    m = DLinearCore(lookback=L, n_features=F, loss=SquaredLoss())
    trend_flat, seasonal_flat = m._decompose_flat(seq.reshape(n, -1))
    trend = trend_flat.reshape(n, L, F)
    seasonal = seasonal_flat.reshape(n, L, F)
    assert np.allclose(trend + seasonal, seq)


def test_kernel_impar_y_acotado_por_lookback():
    m = DLinearCore(lookback=10, n_features=3, loss=SquaredLoss())
    assert m.kernel == 9        # min(10, 25) = 10 -> par -> baja a 9
    m2 = DLinearCore(lookback=60, n_features=3, loss=SquaredLoss())
    assert m2.kernel == 25      # tope declarado
    m3 = DLinearCore(lookback=60, n_features=3, kernel=7, loss=SquaredLoss())
    assert m3.kernel == 7


def test_media_movil_es_causal_no_mira_fuera_de_la_ventana():
    """Perturbar UN día de la ventana no puede mover el trend de un día lejano
    más allá de lo que el kernel alcanza — y el padding es por borde, nunca
    trae datos de fuera de `seq`."""
    seq, rng = _seq(n=5, L=12, F=2)
    m = DLinearCore(lookback=12, n_features=2, kernel=5, loss=SquaredLoss())
    base = m._moving_average(seq)
    alterada = seq.copy()
    alterada[:, 0, :] += 1000.0   # perturbación grande en el primer día
    movida = m._moving_average(alterada)
    # El kernel=5 con padding por borde: el primer día sólo puede afectar los
    # primeros (kernel//2 + 1) = 3 pasos de la media móvil.
    assert np.allclose(base[:, 3:, :], movida[:, 3:, :])
    assert not np.allclose(base[:, 0, :], movida[:, 0, :])


def test_backward_coincide_con_el_gradiente_numerico():
    seq, rng = _seq(n=20, L=6, F=3, seed=99)
    X = seq.reshape(20, -1)
    Y = rng.normal(size=(20, 2))
    m = DLinearCore(lookback=6, n_features=3, kernel=3, loss=SquaredLoss(), seed=5)
    params = m._init_params(X.shape[1], Y.shape[1], np.random.default_rng(0))
    # Zero-init (como LinearCore) da gradiente idénticamente nulo en Wt/Ws con
    # SquaredLoss simétrica: se rompe la simetría para que el chequeo sea real.
    params = {k: v + 0.01 * np.random.default_rng(1).normal(size=v.shape)
              for k, v in params.items()}
    mask = np.ones_like(Y, dtype=bool)
    n_valid = mask.sum()

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


def test_entrena_y_baja_la_perdida():
    seq, rng = _seq(n=150, L=8, F=4, seed=3)
    X = seq.reshape(150, -1)
    W = rng.normal(size=(X.shape[1], 2))
    Y = X @ W + 0.05 * rng.normal(size=(150, 2))
    m = DLinearCore(lookback=8, n_features=4, loss=SquaredLoss(), epochs=200, seed=5)
    m.fit(X, Y)
    assert set(m.params) == {"Wt", "Ws", "b"}
    assert m._weight_keys() == ("Wt", "Ws")
    assert m.history[-1]["train_loss"] < 0.5 * m.history[0]["train_loss"]


def test_hp_declara_lookback_kernel_y_n_features():
    m = DLinearCore(lookback=30, n_features=19, loss=SquaredLoss())
    assert m.hp() == {"lookback": 30, "n_features": 19, "kernel_media_movil": 25}


def test_lookback_o_n_features_invalidos_fallan_temprano():
    for L, F in ((0, 3), (-1, 3), (5, 0)):
        try:
            DLinearCore(lookback=L, n_features=F, loss=SquaredLoss())
        except ValueError:
            continue
        raise AssertionError(f"lookback={L}, n_features={F} debería fallar")


def test_run_experiment_dlinear_de_punta_a_punta():
    """Integración real sobre un Dataset sintético (sin depender del snapshot
    Gold local): with_lookback + --model dlinear. Sin `lookback=` declarado
    tiene que fallar explícito en vez de entrenar con una forma incorrecta."""
    from rio_search import data as data_mod
    from rio_search import train as train_mod
    from rio_search.tests.test_target_param import _ds

    ds_lb = data_mod.with_lookback(_ds(), 6)
    splits = data_mod.make_splits(ds_lb.fecha)

    try:
        train_mod.run_experiment(ds_lb, splits, model="dlinear", loss="mse",
                                 epochs=3, evaluar_test=False)
        raise AssertionError("dlinear sin lookback= debería fallar")
    except ValueError as e:
        assert "lookback" in str(e)

    out = train_mod.run_experiment(ds_lb, splits, model="dlinear", loss="mse",
                                   epochs=3, evaluar_test=False, lookback=6)
    assert out["model"] == "dlinear"
    assert out["model_hp"]["lookback"] == 6
    assert out["model_hp"]["n_features"] == 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de DLinear OK")
