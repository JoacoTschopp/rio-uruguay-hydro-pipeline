"""Tests de B5.02: un modelo por horizonte, mismos HP que el multi-salida.

Lo que hay que garantizar no es que per_horizon gane o pierda, sino que sea
**comparable**: mismas features, mismo preprocesamiento, misma evaluación. La
única diferencia permitida es que la representación no se comparte.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import data as data_mod
from rio_search.train import run_experiment


def _ds(n=900, seed=3, escalas=(1.0, 3.0)):
    """Dos horizontes con el MISMO generador pero distinta escala: si los modelos
    per-horizonte se cruzaran de columna, el sesgo porcentual lo delata."""
    rng = np.random.default_rng(seed)
    fecha = pd.date_range("2018-01-01", periods=n, freq="D")
    x = rng.normal(size=(n, 3))
    y = 1000.0 + 200.0 * x[:, 0] + rng.normal(0, 50, n)
    Y = np.column_stack([y * e for e in escalas])
    return data_mod.Dataset(fecha=fecha, X=x, Y=Y, q_actual=y,
                            tau=np.full(n, 0.85), feature_names=["a", "b", "c"],
                            horizons=(1, 2), tau_mode="test")


KW = dict(model="linear", loss="mse", epochs=120, evaluar_test=False)


def test_estructura_de_la_salida():
    """La bitácora dice qué modo corrió, y epochs/best_epoch son por horizonte."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, per_horizon=True, **KW)
    assert r["horizonte"] == "per_horizon"
    assert isinstance(r["epochs_run"], list) and len(r["epochs_run"]) == 2
    assert isinstance(r["best_epoch"], list) and len(r["best_epoch"]) == 2
    assert set(r["val"]["per_horizon"]) == {"h01", "h02"}
    assert np.isfinite(r["val"]["mean"]["gral"])


def test_multi_salida_no_cambia():
    """Regresión: el camino por defecto sigue reportando escalares."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, **KW)
    assert r["horizonte"] == "multi_output"
    assert isinstance(r["epochs_run"], int) and isinstance(r["best_epoch"], int)


def test_cada_modelo_aprende_su_columna():
    """Con targets a escala 1x y 3x, un cruce de columnas daría pbias de ±200 %.
    Cada modelo tiene que quedar cerca de SU escala."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, per_horizon=True, **KW)
    for h in ("h01", "h02"):
        assert abs(r["val"]["per_horizon"][h]["pbias"]) < 20.0, h


def test_la_mascara_actua_por_columna():
    """La cola sin target a h=2 (como los 14 días reales) no rompe ni contamina:
    el modelo de h=1 sigue entrenando con esas filas."""
    ds = _ds()
    ds.Y[-250:, 1] = np.nan          # entra en TRAIN+VAL: h02 pierde su cola
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    r = run_experiment(ds, splits, per_horizon=True, **KW)
    assert np.isfinite(r["val"]["per_horizon"]["h01"]["rmse"])
    assert abs(r["val"]["per_horizon"]["h01"]["pbias"]) < 20.0


def test_on_epoch_es_incompatible():
    """El podado por época está definido sobre UN entrenamiento; con ocho sería
    ambiguo. Mejor negarse que podar cualquier cosa."""
    ds = _ds()
    splits = data_mod.make_splits(ds.fecha, test_days=100, val_days=200)
    try:
        run_experiment(ds, splits, per_horizon=True,
                       on_epoch=lambda e, v: False, **KW)
    except ValueError:
        return
    raise AssertionError("per_horizon + on_epoch tenía que levantar ValueError")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de per_horizon OK")
