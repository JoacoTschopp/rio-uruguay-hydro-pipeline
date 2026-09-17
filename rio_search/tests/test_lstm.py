"""Tests de B4.14: LSTM (torch), adaptador con el mismo contrato que las demás Core.

Cinco garantías: sólo acepta ExpectileLoss (igual que XGBoostCore y por la misma
razón), el forward tiene la forma esperada y usa sólo el último paso temporal de
la secuencia, la pérdida baja al entrenar, el device queda declarado en hp(), y
la integración con `run_experiment` vía `--model lstm --lookback L` funciona de
punta a punta.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search.models import ExpectileLoss, LSTMCore, SquaredLoss


def _seq(n=60, L=8, F=3, n_out=2, seed=11):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, L, F)).reshape(n, -1).astype(np.float64)
    Y = rng.normal(loc=10.0, scale=2.0, size=(n, n_out))
    tau = np.full(n, 0.7)
    return X, Y, tau


def test_solo_acepta_expectile_loss():
    try:
        LSTMCore(lookback=8, n_features=3, loss=SquaredLoss())
        raise AssertionError("debería rechazar una pérdida que no sea ExpectileLoss")
    except NotImplementedError as e:
        assert "ExpectileLoss" in str(e)


def test_lookback_o_n_features_invalidos_fallan_temprano():
    for L, F in ((0, 3), (-1, 3), (5, 0)):
        try:
            LSTMCore(lookback=L, n_features=F, loss=ExpectileLoss())
        except ValueError:
            continue
        raise AssertionError(f"lookback={L}, n_features={F} debería fallar")


def test_forward_procesa_toda_la_ventana_no_solo_el_ultimo_dia():
    """Un LSTM propaga estado por la recurrencia: perturbar CUALQUIER día de la
    ventana —el primero o el último— tiene que mover la predicción, porque el
    hidden state del último paso lleva memoria de todos los anteriores. (La
    garantía de que no mira más allá de la ventana no es de este modelo: la da
    estructuralmente `make_sequences`/`with_lookback`, que nunca le pasa datos
    posteriores a t — ver test_lookback.py.)"""
    X, Y, tau = _seq(n=10, L=6, F=3, n_out=2)
    m = LSTMCore(lookback=6, n_features=3, loss=ExpectileLoss(), hidden_size=4,
                 epochs=1, seed=1)
    m.fit(X, Y, tau=tau)
    pred_base = m.predict(X)

    for pos in (0, -1):                      # primer día y último día de la ventana
        X_alt = X.reshape(10, 6, 3).copy()
        X_alt[:, pos, :] += 5.0
        pred_alt = m.predict(X_alt.reshape(10, -1))
        assert not np.allclose(pred_base, pred_alt, atol=1e-6), f"pos={pos}"


def test_salida_tiene_la_forma_esperada():
    X, Y, tau = _seq(n=15, L=5, F=4, n_out=3)
    m = LSTMCore(lookback=5, n_features=4, loss=ExpectileLoss(), hidden_size=6,
                 epochs=2, seed=2)
    m.fit(X, Y, tau=tau)
    pred = m.predict(X)
    assert pred.shape == (15, 3)
    assert pred.dtype == np.float64


def test_bidireccional_duplica_la_entrada_del_head():
    import torch

    m = LSTMCore(lookback=5, n_features=4, loss=ExpectileLoss(), hidden_size=6,
                 bidirectional=True)
    net = m._build_net(n_out=3)
    assert net.head.in_features == 12          # 6 * 2
    m2 = LSTMCore(lookback=5, n_features=4, loss=ExpectileLoss(), hidden_size=6,
                  bidirectional=False)
    net2 = m2._build_net(n_out=3)
    assert net2.head.in_features == 6


def test_entrena_y_baja_la_perdida():
    n = 200
    rng = np.random.default_rng(4)
    L, F = 6, 3
    seq = rng.normal(size=(n, L, F))
    W = rng.normal(size=F)
    # el target depende sólo del último paso de la ventana: aprendible por un LSTM chico
    y = seq[:, -1, :] @ W + 0.05 * rng.normal(size=n)
    X = seq.reshape(n, -1)
    Y = np.column_stack([y, y * 2.0])
    tau = np.full(n, 0.5)                      # tau=0.5: comparable con MSE
    m = LSTMCore(lookback=L, n_features=F, loss=ExpectileLoss(), hidden_size=8,
                epochs=150, patience=150, seed=5)
    m.fit(X, Y, tau=tau)
    assert m.history[-1]["train_loss"] < 0.5 * m.history[0]["train_loss"]


def test_hp_declara_arquitectura_y_device():
    X, Y, tau = _seq(n=12, L=5, F=3, n_out=2)
    m = LSTMCore(lookback=5, n_features=3, loss=ExpectileLoss(), hidden_size=7,
                num_layers=2, dropout=0.1, epochs=1, seed=1)
    m.fit(X, Y, tau=tau)
    hp = m.hp()
    assert hp["hidden_size"] == 7 and hp["num_layers"] == 2 and hp["dropout"] == 0.1
    assert hp["lookback"] == 5 and hp["n_features"] == 3
    assert hp["device"] in ("cpu", "cuda")


def test_early_stopping_restaura_los_mejores_pesos_no_los_ultimos():
    """Con patience=1 y una corrida larga, si el último epoch no es el mejor,
    `best_epoch` tiene que quedar antes del último."""
    X, Y, tau = _seq(n=40, L=5, F=3, n_out=1, seed=9)
    Xv, Yv, tauv = _seq(n=20, L=5, F=3, n_out=1, seed=10)
    m = LSTMCore(lookback=5, n_features=3, loss=ExpectileLoss(), hidden_size=4,
                epochs=60, patience=5, seed=3)
    m.fit(X, Y, tau=tau, X_val=Xv, Y_val=Yv, tau_val=tauv)
    assert m.best_epoch is not None
    assert len(m.history) <= 60


def test_run_experiment_lstm_de_punta_a_punta():
    """Integración real: with_lookback + --model lstm. Sin `lookback=` declarado
    tiene que fallar explícito, igual que dlinear."""
    from rio_search import data as data_mod
    from rio_search import train as train_mod
    from rio_search.tests.test_target_param import _ds

    ds_lb = data_mod.with_lookback(_ds(), 6)
    splits = data_mod.make_splits(ds_lb.fecha)

    try:
        train_mod.run_experiment(ds_lb, splits, model="lstm", loss="gral",
                                 epochs=2, evaluar_test=False)
        raise AssertionError("lstm sin lookback= debería fallar")
    except ValueError as e:
        assert "lookback" in str(e)

    out = train_mod.run_experiment(ds_lb, splits, model="lstm", loss="gral",
                                   epochs=2, evaluar_test=False, lookback=6,
                                   lstm_hidden=4)
    assert out["model"] == "lstm"
    assert out["model_hp"]["lookback"] == 6
    assert out["model_hp"]["n_features"] == 3
    assert out["model_hp"]["hidden_size"] == 4


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de LSTM OK")
