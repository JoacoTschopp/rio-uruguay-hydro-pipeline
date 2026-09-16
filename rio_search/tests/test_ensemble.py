"""Tests de B10.01/B10.02: ensembles por promedio de predicciones (G-05).

La garantía central es la razón de ser de la celda: promediar PREDICCIONES no es
promediar métricas. Dos miembros con errores simétricos tienen métricas
individuales mediocres y un ensemble exacto — si el código promediara métricas,
ese caso daría lo mismo que cada miembro y el test lo caza.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import rio_search.ensemble as E
from rio_search.train import run_experiment
from rio_search.tests.test_target_param import _ds
from rio_search import data as data_mod


def test_promediar_predicciones_no_es_promediar_metricas():
    verdad = np.full((10, 2), 1000.0)
    arriba, abajo = verdad + 200.0, verdad - 200.0     # errores simétricos
    ens = E.promedio_predicciones(np.stack([arriba, abajo]))
    assert np.allclose(ens, verdad)                    # el ensemble acierta exacto
    # mientras que la media de los RMSE individuales es 200, no 0
    rmse_ind = np.mean([np.sqrt(np.mean((p - verdad) ** 2)) for p in (arriba, abajo)])
    assert rmse_ind == 200.0


def test_jackknife_deja_uno_afuera_en_orden():
    preds = np.stack([np.full((4, 2), v) for v in (1.0, 2.0, 3.0)])
    loo = E.jackknife(preds)
    assert len(loo) == 3
    assert np.allclose(loo[0], 2.5)      # sin el miembro 1.0
    assert np.allclose(loo[2], 1.5)      # sin el miembro 3.0


def test_con_sd_y_miembros_identicos_da_cero():
    media = {"gral": 0.5, "rmse": 900.0}
    muestras = [dict(media) for _ in range(5)]
    out = E._con_sd(media, muestras)
    assert out["gral_sd"] == 0.0 and out["rmse_sd"] == 0.0
    assert out["gral"] == 0.5            # la media no se toca


def test_run_experiment_devuelve_predicciones_solo_si_se_piden():
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha)
    kw = dict(model="linear", loss="mse", epochs=30, evaluar_test=False)
    con = run_experiment(ds, splits, return_predictions=True, **kw)
    n_val = int(np.sum(splits.val))
    assert con["predicciones"]["val"].shape == (n_val, ds.Y.shape[1])
    assert "test" not in con["predicciones"]            # VAL únicamente (R3)
    sin = run_experiment(ds, splits, **kw)
    assert "predicciones" not in sin                    # no puede caer en un JSON


def _fake_corrida(fechas, ruido):
    n = len(fechas)
    ds = types.SimpleNamespace(fecha=fechas, Y=np.full((n, 2), 1000.0),
                               tau=np.full(n, 0.85), horizons=(1, 2))
    splits = types.SimpleNamespace(val=np.ones(n, dtype=bool))
    preds = np.stack([ds.Y + ruido, ds.Y + ruido])      # 2 semillas iguales
    metricas = [{"gral": 0.5, "rmse": 1.0, "nse": 0.9, "kge": 0.9,
                 "v_plus": 0.1, "v_minus": 0.1}] * 2
    return ds, splits, preds, metricas


def test_ensemble_configs_aparea_por_semilla_y_cancela_errores_simetricos():
    fechas = pd.date_range("2020-01-01", periods=8, freq="D")
    fakes = {"a": _fake_corrida(fechas, +150.0), "b": _fake_corrida(fechas, -150.0)}
    orig = E.predicciones_miembro
    E.predicciones_miembro = lambda nombre, seeds, snapshot=None: fakes[nombre]
    try:
        out = E.ensemble_configs(["a", "b"], seeds=[1, 2])
    finally:
        E.predicciones_miembro = orig
    m = out["val"]["mean"]
    assert m["rmse"] < 1e-9 and m["rmse_sd"] == 0.0     # simétricos: se cancelan
    assert out["n_miembros"] == 2


def test_ensemble_configs_rechaza_val_desalineado():
    f1 = pd.date_range("2020-01-01", periods=8, freq="D")
    f2 = pd.date_range("2020-06-01", periods=8, freq="D")
    fakes = {"a": _fake_corrida(f1, 0.0), "b": _fake_corrida(f2, 0.0)}
    orig = E.predicciones_miembro
    E.predicciones_miembro = lambda nombre, seeds, snapshot=None: fakes[nombre]
    try:
        try:
            E.ensemble_configs(["a", "b"], seeds=[1, 2])
        except ValueError as e:
            assert "alineado" in str(e)
        else:
            raise AssertionError("VAL desalineado tendría que haber fallado")
    finally:
        E.predicciones_miembro = orig


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de ensemble OK")
