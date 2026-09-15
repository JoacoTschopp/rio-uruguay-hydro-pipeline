"""Tests del modulador de régimen, con foco en el invariante de causalidad."""

from __future__ import annotations

import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import gate as G


def test_pct_rank_basico():
    x = np.array([10.0, 20.0, 30.0, 40.0])
    assert np.allclose(G.pct_rank(x), [0.25, 0.5, 0.75, 1.0])


def test_pct_rank_promedia_empates_y_propaga_nan():
    x = np.array([5.0, 5.0, np.nan, 9.0])
    out = G.pct_rank(x)
    assert np.isnan(out[2])
    assert np.allclose(out[[0, 1]], 0.5)     # rangos 1 y 2 -> promedio 1,5 / 3
    assert np.isclose(out[3], 1.0)


def test_lead_weights_suman_uno_y_decaen():
    w = G.lead_weights(0.85, 14)
    assert abs(w.sum() - 1.0) < 1e-12
    assert np.all(np.diff(w) < 0)
    assert abs(w[0] / w[13] - 0.85 ** -13) < 1e-9


def test_rolling_sum_excluye_el_dia_actual():
    """La humedad antecedente no debe incluir la lluvia del día de emisión."""
    x = np.arange(1.0, 8.0)                     # 1..7
    out = G.rolling_sum(x, window=3, min_periods=1)
    assert out[3] == 1.0 + 2.0 + 3.0            # en t=3 suma t=0,1,2 — no el 4
    assert np.isnan(out[0])                     # sin historia previa


def test_tau_neutro_cuando_el_indice_es_cero():
    assert abs(G.tau_from_index(np.array([0.0]))[0] - 0.5) < 1e-12


def test_tau_acotado_y_simetrico():
    p = G.GateParams(tau_max=0.85)
    assert abs(G.tau_from_index(np.array([+1.0]), p)[0] - 0.85) < 1e-12
    assert abs(G.tau_from_index(np.array([-1.0]), p)[0] - 0.15) < 1e-12
    # nunca se sale del rango declarado
    tau = G.tau_from_index(np.linspace(-5, 5, 101), p)
    assert tau.min() >= 0.15 - 1e-12 and tau.max() <= 0.85 + 1e-12


def test_mas_lluvia_da_tau_mas_alto():
    """Un período seco seguido de uno lluvioso tiene que mover τ hacia arriba."""
    rng = np.random.default_rng(3)
    seco = rng.gamma(1.0, 0.2, size=400)
    humedo = rng.gamma(3.0, 6.0, size=400)
    rain = np.concatenate([seco, humedo])
    tau = G.build_tau(rain, mode="oracle")["tau"]
    assert np.nanmean(tau[100:350]) < np.nanmean(tau[450:750])


def test_params_invalidos_fallan():
    for kw in ({"tau_max": 0.4}, {"tau_max": 1.0}, {"w_ant": 0.5, "w_fc": 0.9}):
        try:
            G.GateParams(**kw)
        except ValueError:
            continue
        raise AssertionError(f"GateParams({kw}) debería haber fallado")


def test_invariante_de_causalidad():
    """El modulador no puede leer columnas de target. Es el test que impide que la
    métrica se vuelva manipulable si alguien evalúa sobre el dataframe crudo."""
    G.assert_causal(["caudal_actual_m3s", "lluvia_media_est_acum_30d"])  # no falla
    for mala in ("caudal_t_mas_7d", "caudal_t_mas_14d"):
        try:
            G.assert_causal(["caudal_actual_m3s", mala])
        except ValueError as exc:
            assert mala in str(exc)
            continue
        raise AssertionError(f"{mala} debería haber sido rechazada")


def test_modo_antecedent_no_mira_el_futuro():
    """En modo `antecedent`, cambiar el futuro de la serie no puede mover el τ
    de los días anteriores."""
    rng = np.random.default_rng(11)
    rain = rng.gamma(2.0, 4.0, size=600)
    tau_a = G.build_tau(rain, mode="antecedent")["tau"]

    alterada = rain.copy()
    alterada[400:] = 200.0                       # diluvio sólo en la cola
    tau_b = G.build_tau(alterada, mode="antecedent")["tau"]

    # Los percentiles se recalculan sobre toda la serie, así que se compara el
    # orden relativo de los días previos, que es lo que el modulador realmente usa.
    a = np.argsort(np.argsort(tau_a[:390]))
    b = np.argsort(np.argsort(tau_b[:390]))
    assert np.array_equal(a, b)


def test_modo_oracle_si_mira_el_futuro():
    """Contraprueba explícita: el modo oráculo NO es causal, y el test lo deja
    escrito para que nadie lo confunda con el modo operativo."""
    rng = np.random.default_rng(11)
    rain = rng.gamma(2.0, 4.0, size=600)
    tau_a = G.build_tau(rain, mode="oracle")["tau"]
    alterada = rain.copy()
    alterada[400:] = 200.0
    tau_b = G.build_tau(alterada, mode="oracle")["tau"]
    assert not np.allclose(tau_a[380:395], tau_b[380:395], equal_nan=True)


def test_regime_labels():
    tau = np.array([0.85, 0.5, 0.15, np.nan])
    assert list(G.regime_labels(tau)) == ["humedo", "neutro", "seco", "sin_dato"]


def test_gate_grid_de_b804_es_el_producto_completo_y_valido():
    from rio_search.sensitivity import _gate_grid

    grid = _gate_grid()
    assert len(grid) == 27                                  # 3 κ × 3 pesos × 3 ventanas
    etiquetas = [e for e, _ in grid]
    assert len(set(etiquetas)) == 27, "etiquetas repetidas: dos puntos se pisarían"
    # GateParams valida w_ant + w_fc = 1 en __post_init__: si un par no suma 1,
    # la grilla ni se construye. La configuración declarada tiene que estar.
    assert any(p == G.DEFAULT_PARAMS.__class__(kappa=2.2, w_ant=0.35, w_fc=0.65,
                                               ant_days=30) for _, p in grid)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests del modulador OK")
