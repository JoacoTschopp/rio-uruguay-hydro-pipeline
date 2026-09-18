"""Tests del baseline estacional (B0.05): aprende el ciclo anual y sólo de TRAIN."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search.models import SeasonalNaive


def _serie_anual(anios=6, amplitud=1000.0, base=3000.0, start="2010-01-01"):
    fecha = pd.date_range(start, periods=anios * 365, freq="D")
    doy = fecha.dayofyear.to_numpy()
    q = base + amplitud * np.sin(2 * np.pi * doy / 365.25)
    return fecha, q


def test_estacional_aprende_el_ciclo_anual():
    fecha, q = _serie_anual()
    tr = fecha < "2014-01-01"
    m = SeasonalNaive(7).fit(fecha[tr], q[tr])
    pred = m.predict(fecha[~tr], horizons=(1, 14))
    doy_1 = (fecha[~tr] + pd.Timedelta(days=1)).dayofyear.to_numpy()
    esperado = 3000.0 + 1000.0 * np.sin(2 * np.pi * doy_1 / 365.25)
    # la ventana ±7 suaviza el pico de la senoide; alcanza con seguir el ciclo de cerca
    assert np.nanmax(np.abs(pred[:, 0] - esperado)) < 60.0


def test_estacional_predice_el_doy_del_target_no_el_de_emision():
    fecha, q = _serie_anual()
    m = SeasonalNaive(7).fit(fecha, q)
    pred = m.predict(fecha[:5], horizons=(1, 14))
    # t+14 cae 13 días más adelante en el ciclo que t+1: no pueden coincidir
    assert not np.allclose(pred[:, 0], pred[:, 1])


def test_estacional_solo_usa_train():
    fecha, q = _serie_anual()
    tr = fecha < "2014-01-01"
    m = SeasonalNaive(7).fit(fecha[tr], q[tr])
    q2 = q.copy()
    q2[~tr] += 50000.0                     # corromper VAL/TEST no debe cambiar nada
    m2 = SeasonalNaive(7).fit(fecha[tr], q2[tr])
    va = fecha[~tr]
    assert np.array_equal(m.predict(va, (1, 7)), m2.predict(va, (1, 7)))


def test_estacional_ventana_circular_en_el_cambio_de_anio():
    # datos sólo de la primera semana de enero: el 31/12 tiene que heredar esa
    # media por la ventana circular, no caer al promedio global
    fecha = pd.DatetimeIndex([f"{y}-01-0{d}" for y in (2010, 2011, 2012) for d in range(1, 8)])
    q = np.full(len(fecha), 500.0)
    m = SeasonalNaive(7).fit(fecha, q)
    pred = m.predict(pd.DatetimeIndex(["2013-12-30"]), horizons=(1,))   # doy(t+1) = 365
    assert pred[0, 0] == 500.0


def test_estacional_dia_sin_datos_cae_a_la_media_global():
    fecha = pd.DatetimeIndex([f"2010-06-{d:02d}" for d in range(1, 11)])
    m = SeasonalNaive(2).fit(fecha, np.full(10, 700.0))
    pred = m.predict(pd.DatetimeIndex(["2011-01-01"]), horizons=(1,))
    assert pred[0, 0] == 700.0             # global == 700 porque la serie es constante


def test_run_baselines_incluye_el_estacional():
    from rio_search import data as data_mod
    from rio_search.train import run_baselines

    fecha, q = _serie_anual()
    n = len(fecha)
    rng = np.random.default_rng(7)
    ds = data_mod.Dataset(
        fecha=fecha, X=rng.normal(size=(n, 3)),
        Y=np.repeat(q.reshape(-1, 1), 2, axis=1) + rng.normal(0, 10, size=(n, 2)),
        q_actual=q, tau=np.full(n, 0.5), feature_names=["a", "b", "c"],
        horizons=(1, 14), tau_mode="test")
    splits = data_mod.make_splits(ds.fecha)
    out = run_baselines(ds, splits, evaluar_test=False)
    assert "estacional doy ±7d" in out
    m = out["estacional doy ±7d"]["val"]["mean"]
    assert np.isfinite(m["rmse"]) and np.isfinite(m["gral"])
    assert "test" not in out["estacional doy ±7d"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de baselines OK")
