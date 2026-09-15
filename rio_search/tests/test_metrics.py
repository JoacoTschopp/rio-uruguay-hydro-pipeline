"""Tests de las métricas contra valores conocidos.

    python -m pytest rio_search/tests -q
    python rio_search/tests/test_metrics.py      (sin pytest, corre igual)
"""

from __future__ import annotations

import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import metrics as M
from rio_search.models import ExpectileLoss, SquaredLoss


def test_prediccion_perfecta():
    y = np.array([100.0, 500.0, 2000.0, 8000.0])
    assert M.rmse(y, y) == 0.0
    assert M.mae(y, y) == 0.0
    assert M.nse(y, y) == 1.0
    assert abs(M.kge(y, y) - 1.0) < 1e-12
    assert M.pbias(y, y) == 0.0
    assert abs(M.gral(y, y, 0.8) - 0.0) < 1e-12


def test_nse_de_la_media_es_cero():
    y = np.array([1.0, 2.0, 3.0, 4.0, 10.0])
    pred = np.full_like(y, y.mean())
    assert abs(M.nse(y, pred) - 0.0) < 1e-12


def test_kge_de_la_media_es_menos_041():
    """Valor de referencia del plan §3.7: KGE de la predicción constante = −0,41.

    Sale de r = 0, alpha = 0, beta = 1  ->  1 − sqrt(2) = −0,4142.
    """
    rng = np.random.default_rng(0)
    y = rng.gamma(2.0, 500.0, size=2000)
    pred = np.full_like(y, y.mean())
    assert abs(M.kge(y, pred) - (1.0 - np.sqrt(2.0))) < 1e-9


def test_expectile_en_tau_medio_es_el_cuadrado():
    e = np.array([-3.0, -1.0, 0.0, 0.5, 4.0])
    assert np.allclose(M.expectile_se(e, 0.5), e ** 2)


def test_gral_con_tau_medio_y_sin_log_es_exactamente_rmse():
    """La propiedad que hace que la métrica nueva contenga a la vieja.

    Es la verificación de partida de la Decisión 039: no una aproximación.
    """
    rng = np.random.default_rng(42)
    y = rng.gamma(2.0, 900.0, size=5000) + 150.0
    pred = y * rng.normal(1.0, 0.25, size=y.size)
    pred = np.maximum(pred, 1.0)
    assert M.gral(y, pred, 0.5, log=False) == M.rmse(y, pred)


def test_asimetria_apunta_al_lado_correcto():
    """τ > 0,5 tiene que castigar más subestimar; τ < 0,5, más sobrestimar."""
    y = np.array([1000.0])
    subestima = np.array([800.0])     # e = +200
    sobrestima = np.array([1200.0])   # e = −200

    alto = 0.8
    assert M.gral(y, subestima, alto, log=False) > M.gral(y, sobrestima, alto, log=False)
    bajo = 0.2
    assert M.gral(y, sobrestima, bajo, log=False) > M.gral(y, subestima, bajo, log=False)


def test_razon_de_penalizacion_es_tau_sobre_uno_menos_tau():
    """La identidad que permite fijar τ desde el costo: τ = k/(k+1)."""
    for tau in (0.6, 0.75, 0.8, 0.9):
        sub = M.expectile_se(np.array([1.0]), tau)[0]     # e > 0
        sobre = M.expectile_se(np.array([-1.0]), tau)[0]  # e < 0
        assert abs(sub / sobre - tau / (1.0 - tau)) < 1e-12


def test_tasas_de_violacion():
    y = np.array([100.0, 100.0, 100.0, 100.0])
    pred = np.array([90.0, 110.0, 90.0, 110.0])   # sub, sobre, sub, sobre
    tau = np.array([0.85, 0.85, 0.15, 0.15])      # húmedo, húmedo, seco, seco
    v = M.violation_rates(y, pred, tau)
    assert v["n_wet"] == 2 and v["n_dry"] == 2
    assert v["v_plus"] == 0.5     # 1 de 2 días húmedos subestima
    assert v["fa_wet"] == 0.5
    assert v["v_minus"] == 0.5    # 1 de 2 días secos sobrestima


def test_nan_se_descartan_y_se_reporta_cobertura():
    y = np.array([1.0, np.nan, 3.0, 4.0])
    pred = np.array([1.0, 2.0, np.nan, 4.0])
    out = M.evaluate(y, pred)
    assert out["n"] == 2
    assert abs(out["coverage"] - 0.5) < 1e-12
    assert out["rmse"] == 0.0


def test_gradiente_de_la_expectil_es_continuo_en_cero():
    """La razón de elegir expectil y no pinball: derivable en e = 0."""
    loss = ExpectileLoss()
    tau = np.array([0.85])
    izq = loss.grad(np.array([-1e-9]), tau)[0]
    der = loss.grad(np.array([+1e-9]), tau)[0]
    assert abs(izq) < 1e-8 and abs(der) < 1e-8


def test_gradiente_numerico_coincide_con_el_analitico():
    rng = np.random.default_rng(7)
    for loss, tau in ((SquaredLoss(), None), (ExpectileLoss(), np.array([0.8, 0.2, 0.65]))):
        y = np.array([10.0, -4.0, 2.5])
        yhat = rng.normal(size=3)
        h = 1e-6
        analitico = loss.grad(y - yhat, tau)
        numerico = np.array([
            (loss.value(y - (yhat + h * np.eye(3)[i]), tau).sum()
             - loss.value(y - (yhat - h * np.eye(3)[i]), tau).sum()) / (2 * h)
            for i in range(3)
        ])
        assert np.allclose(analitico, numerico, atol=1e-5), loss.name


def test_skill_score():
    assert M.skill_score(50.0, 100.0) == 0.5
    assert M.skill_score(100.0, 100.0) == 0.0
    assert M.skill_score(150.0, 100.0) == -0.5


def test_tau_fuera_de_rango_falla():
    for bad in (0.0, 1.0, -0.1, 1.2):
        try:
            M.expectile_se(np.array([1.0]), bad)
        except ValueError:
            continue
        raise AssertionError(f"τ = {bad} debería haber fallado")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests de métricas OK")
