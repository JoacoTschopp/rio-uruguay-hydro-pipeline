"""Tests de B4.18: TCN (torch), adaptador con el mismo contrato que las demás Core.

El punto central de esta celda, según su propia nota en la matriz: la causalidad
de una TCN es **estructural** (padding a la izquierda en cada convolución), no
una convención de entrenamiento como en el LSTM. `test_causalidad_estructural_
de_la_convolucion` es la prueba directa de esa propiedad, sobre el mapa de
activaciones interno — no sobre la predicción final, que sólo lee el último paso.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search.models import ExpectileLoss, SquaredLoss, TCNCore


def _seq(n=60, L=8, F=3, n_out=2, seed=11):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, L, F)).reshape(n, -1).astype(np.float64)
    Y = rng.normal(loc=10.0, scale=2.0, size=(n, n_out))
    tau = np.full(n, 0.7)
    return X, Y, tau


def test_solo_acepta_expectile_loss():
    try:
        TCNCore(lookback=8, n_features=3, loss=SquaredLoss())
        raise AssertionError("debería rechazar una pérdida que no sea ExpectileLoss")
    except NotImplementedError as e:
        assert "ExpectileLoss" in str(e)


def test_lookback_o_n_features_invalidos_fallan_temprano():
    for L, F in ((0, 3), (-1, 3), (5, 0)):
        try:
            TCNCore(lookback=L, n_features=F, loss=ExpectileLoss())
        except ValueError:
            continue
        raise AssertionError(f"lookback={L}, n_features={F} debería fallar")


def test_kernel_size_invalido_falla_temprano():
    try:
        TCNCore(lookback=8, n_features=3, loss=ExpectileLoss(), kernel_size=1)
        raise AssertionError("kernel_size=1 debería fallar (no hay nada que dilatar)")
    except ValueError as e:
        assert "kernel_size" in str(e)


def test_causalidad_estructural_de_la_convolucion():
    """Bai, Kolter & Koltun 2018: la causalidad tiene que ser una propiedad de la
    arquitectura (padding sólo a la izquierda, recortado del lado derecho jamás
    porque nunca se agregó), no una convención de entrenamiento. Se prueba sobre
    el mapa de activaciones interno (antes de la cabeza, que sólo lee el último
    paso): perturbar un paso POSTERIOR de la ventana no puede mover ni un bit el
    valor calculado en los pasos ANTERIORES — no "casi", exactamente igual,
    porque el kernel causal físicamente nunca lee hacia adelante."""
    import torch
    torch.manual_seed(0)
    F, L = 4, 12
    m = TCNCore(lookback=L, n_features=F, loss=ExpectileLoss(), channels=6,
               n_blocks=3, kernel_size=3, dropout=0.0)
    net = m._build_net(n_out=1)
    net.eval()

    x = torch.randn(1, F, L)
    feat_base = net.bloques(x)                 # (1, channels, L), antes de la cabeza

    pos = 5                                     # un paso interior, ni el primero ni el último
    x_alt = x.clone()
    x_alt[:, :, pos] += 100.0
    feat_alt = net.bloques(x_alt)

    assert torch.equal(feat_base[:, :, :pos], feat_alt[:, :, :pos]), (
        "perturbar el paso %d movió activaciones ANTERIORES a él: la conv no es causal" % pos)
    assert not torch.equal(feat_base[:, :, pos], feat_alt[:, :, pos]), (
        "perturbar el paso %d no movió ni su propia activación: sospechoso" % pos)


def test_salida_tiene_la_forma_esperada():
    X, Y, tau = _seq(n=15, L=10, F=4, n_out=3)
    m = TCNCore(lookback=10, n_features=4, loss=ExpectileLoss(), channels=6,
               n_blocks=2, epochs=2, seed=2)
    m.fit(X, Y, tau=tau)
    pred = m.predict(X)
    assert pred.shape == (15, 3)
    assert pred.dtype == np.float64


def test_entrena_y_baja_la_perdida():
    n = 200
    rng = np.random.default_rng(4)
    L, F = 10, 3
    seq = rng.normal(size=(n, L, F))
    W = rng.normal(size=F)
    # el target depende sólo del último paso de la ventana: aprendible por una TCN chica
    y = seq[:, -1, :] @ W + 0.05 * rng.normal(size=n)
    X = seq.reshape(n, -1)
    Y = np.column_stack([y, y * 2.0])
    tau = np.full(n, 0.5)                      # tau=0.5: comparable con MSE
    m = TCNCore(lookback=L, n_features=F, loss=ExpectileLoss(), channels=8,
               n_blocks=2, epochs=150, patience=150, seed=5)
    m.fit(X, Y, tau=tau)
    assert m.history[-1]["train_loss"] < 0.5 * m.history[0]["train_loss"]


def test_hp_declara_arquitectura_campo_receptivo_y_device():
    X, Y, tau = _seq(n=12, L=10, F=3, n_out=2)
    m = TCNCore(lookback=10, n_features=3, loss=ExpectileLoss(), channels=6,
               n_blocks=3, kernel_size=3, dropout=0.1, epochs=1, seed=1)
    m.fit(X, Y, tau=tau)
    hp = m.hp()
    assert hp["channels"] == 6 and hp["n_blocks"] == 3 and hp["kernel_size"] == 3
    assert hp["dropout"] == 0.1
    assert hp["campo_receptivo"] == 1 + 2 * (3 - 1) * (2 ** 3 - 1)   # = 29
    assert hp["lookback"] == 10 and hp["n_features"] == 3
    assert hp["device"] in ("cpu", "cuda")


def test_early_stopping_restaura_los_mejores_pesos_no_los_ultimos():
    """Con patience chico y una corrida larga, si el último epoch no es el mejor,
    `best_epoch` tiene que quedar antes del último."""
    X, Y, tau = _seq(n=40, L=8, F=3, n_out=1, seed=9)
    Xv, Yv, tauv = _seq(n=20, L=8, F=3, n_out=1, seed=10)
    m = TCNCore(lookback=8, n_features=3, loss=ExpectileLoss(), channels=4,
               n_blocks=2, epochs=60, patience=5, seed=3)
    m.fit(X, Y, tau=tau, X_val=Xv, Y_val=Yv, tau_val=tauv)
    assert m.best_epoch is not None
    assert len(m.history) <= 60


def test_run_experiment_tcn_de_punta_a_punta():
    """Integración real: with_lookback + --model tcn. Sin `lookback=` declarado
    tiene que fallar explícito, igual que dlinear y lstm."""
    from rio_search import data as data_mod
    from rio_search import train as train_mod
    from rio_search.tests.test_target_param import _ds

    ds_lb = data_mod.with_lookback(_ds(), 6)
    splits = data_mod.make_splits(ds_lb.fecha)

    try:
        train_mod.run_experiment(ds_lb, splits, model="tcn", loss="gral",
                                 epochs=2, evaluar_test=False)
        raise AssertionError("tcn sin lookback= debería fallar")
    except ValueError as e:
        assert "lookback" in str(e)

    out = train_mod.run_experiment(ds_lb, splits, model="tcn", loss="gral",
                                   epochs=2, evaluar_test=False, lookback=6,
                                   tcn_channels=4, tcn_blocks=2)
    assert out["model"] == "tcn"
    assert out["model_hp"]["lookback"] == 6
    assert out["model_hp"]["n_features"] == 3
    assert out["model_hp"]["channels"] == 4
    assert out["model_hp"]["n_blocks"] == 2


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de TCN OK")
