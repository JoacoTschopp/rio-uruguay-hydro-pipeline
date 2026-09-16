"""Tests de la ventana causal de B2.17: make_sequences y with_lookback.

La propiedad que importa es una sola: la ventana de la fila t termina en t y
nunca lo cruza. Todo lo demás (huecos como NaN, recorte del arranque, orden de
aplanado) existe para que esa propiedad se sostenga sin desalinear filas.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as D


def _ds(fechas, X):
    X = np.asarray(X, dtype=float)
    n = len(fechas)
    return D.Dataset(
        fecha=pd.DatetimeIndex(fechas), X=X, Y=np.zeros((n, 1)),
        q_actual=np.ones(n), tau=np.full(n, 0.5),
        feature_names=[f"f{j}" for j in range(X.shape[1])],
        horizons=(1,), tau_mode="test",
    )


def _contiguo(n=10):
    return _ds(pd.date_range("2020-01-01", periods=n), np.arange(float(n))[:, None])


def test_la_ventana_termina_en_t():
    rec, seq = D.make_sequences(_contiguo(), 3)
    assert np.array_equal(seq[:, -1, 0], rec.X[:, 0])


def test_la_ventana_solo_mira_atras():
    """El valor del día i es i: ninguna ventana puede contener un valor mayor
    que el de su propia fila."""
    rec, seq = D.make_sequences(_contiguo(), 4)
    assert (seq.max(axis=(1, 2)) == rec.X[:, 0]).all()


def test_el_futuro_no_entra_en_la_ventana():
    """Perturbar el último día no puede cambiar ninguna ventana anterior."""
    ds = _contiguo()
    X2 = ds.X.copy()
    X2[-1] = 999.0
    _, seq = D.make_sequences(ds, 3)
    _, seq2 = D.make_sequences(_ds(ds.fecha, X2), 3)
    assert np.array_equal(seq[:-1], seq2[:-1])
    assert 999.0 not in seq2[:-1]


def test_el_arranque_sin_ventana_completa_se_descarta():
    rec, seq = D.make_sequences(_contiguo(10), 3)
    assert len(rec) == 8 and seq.shape == (8, 3, 1)
    assert str(rec.fecha[0].date()) == "2020-01-03"


def test_un_hueco_del_calendario_entra_como_nan():
    """Como en el snapshot real: una fila filtrada no corre la ventana, deja NaN
    en su lugar. El Preprocessor los imputa después con estadísticos de TRAIN."""
    fechas = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-04"])
    rec, seq = D.make_sequences(_ds(fechas, [[0.0], [1.0], [3.0]]), 3)
    assert len(rec) == 1                      # sólo el 04 tiene ventana completa
    assert np.isnan(seq[0, 1, 0])             # el 03 no existe: NaN en su lugar
    assert seq[0, 0, 0] == 1.0 and seq[0, 2, 0] == 3.0


def test_lookback_1_es_la_identidad():
    ds = _contiguo()
    rec, seq = D.make_sequences(ds, 1)
    assert len(rec) == len(ds) and np.array_equal(seq[:, 0], ds.X)


def test_aplanado_ordena_de_viejo_a_nuevo():
    ds = _ds(pd.date_range("2020-01-01", periods=6),
             np.arange(12.0).reshape(6, 2))
    flat = D.with_lookback(ds, 3)
    n_f = len(ds.feature_names)
    assert flat.X.shape == (4, 3 * n_f)
    # las últimas F columnas son el día t, y los nombres lo dicen
    assert np.array_equal(flat.X[:, -n_f:], ds.X[2:])
    assert flat.feature_names[:2] == ["f0_tm2", "f1_tm2"]
    assert flat.feature_names[-2:] == ["f0_tm0", "f1_tm0"]
    # fila 0 = días 0,1,2 aplanados en orden
    assert np.array_equal(flat.X[0], np.arange(6.0))


def test_el_resto_del_dataset_queda_alineado():
    ds = _contiguo()
    ds.Y[:, 0] = np.arange(10.0) * 10
    flat = D.with_lookback(ds, 4)
    assert np.array_equal(flat.Y[:, 0], np.arange(3.0, 10.0) * 10)
    assert len(flat.fecha) == len(flat.X) == len(flat.tau) == 7


def test_lookback_invalido_falla_temprano():
    try:
        D.make_sequences(_contiguo(), 0)
    except ValueError:
        return
    raise AssertionError("lookback=0 tiene que fallar")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de lookback OK")
