"""Métricas de evaluación del pronóstico de caudal.

Funciones puras sobre arrays de NumPy, sin estado y sin más dependencias que
NumPy. Todas descartan los pares con NaN en observado o predicho y reportan la
cobertura efectiva por separado, igual que el resto del pipeline.

Contiene las métricas hidrológicas estándar (RMSE, MAE, MAPE, NSE, KGE, PBIAS,
R²) y la métrica asimétrica por régimen **G-RAL**, documentada en
`docs/funcion_ganancia_regimen.html`.

G-RAL en una línea:

    ψ_τ(ε) = 2 · |τ − 1{ε < 0}| · ε²      con  ε = ln Q_obs − ln Q_pred

donde τ sale del modulador de régimen (`rio_search.gate`). Con τ = 0,5 y sin
transformar, ψ se reduce al error cuadrático y G-RAL devuelve exactamente el
RMSE — esa igualdad es un test de regresión, no una aproximación.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "rmse", "mae", "mape", "nse", "kge", "pbias", "r2",
    "expectile_se", "expectile_se_series", "gral", "violation_rates",
    "skill_score", "evaluate", "dm_test", "WET_THRESHOLD", "DRY_THRESHOLD", "Q_FLOOR",
]

#: Por encima de este τ el día se considera de régimen húmedo al reportar
#: tasas de violación. No interviene en el cálculo de G-RAL.
WET_THRESHOLD = 0.65
#: Por debajo de este τ el día se considera de régimen seco.
DRY_THRESHOLD = 0.35
#: Piso del logaritmo, en m³/s. Está por debajo del p1 observado (204 m³/s):
#: nunca se activa con datos reales, sólo protege de una predicción ≤ 0.
Q_FLOOR = 100.0


def _pairs(y_true, y_pred, tau=None):
    """Alinea las series y descarta los pares no evaluables.

    Devuelve `(y_true, y_pred, tau, coverage)` con los tres arrays ya filtrados.
    `coverage` es la fracción de filas de entrada que sobrevivió.
    """
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    if y_true.shape != y_pred.shape:
        raise ValueError(f"formas distintas: {y_true.shape} vs {y_pred.shape}")

    ok = np.isfinite(y_true) & np.isfinite(y_pred)
    if tau is not None:
        tau = np.asarray(tau, dtype=float).ravel()
        if tau.shape != y_true.shape:
            raise ValueError(f"tau tiene forma {tau.shape}, se esperaba {y_true.shape}")
        ok &= np.isfinite(tau)
        tau = tau[ok]

    n_in = y_true.size
    coverage = float(ok.sum()) / n_in if n_in else 0.0
    return y_true[ok], y_pred[ok], tau, coverage


def _empty(values):
    return values.size == 0


# --------------------------------------------------------------------------
# Métricas estándar
# --------------------------------------------------------------------------

def rmse(y_true, y_pred) -> float:
    """Raíz del error cuadrático medio, en las unidades de la serie."""
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if _empty(yt):
        return float("nan")
    return float(np.sqrt(np.mean((yt - yp) ** 2)))


def mae(y_true, y_pred) -> float:
    """Error absoluto medio."""
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if _empty(yt):
        return float("nan")
    return float(np.mean(np.abs(yt - yp)))


def mape(y_true, y_pred, eps: float = 1.0) -> float:
    """Error porcentual absoluto medio, en porcentaje.

    `eps` es un piso sobre |y_true| para no dividir por cero. Con caudales del
    río Uruguay (mínimo observado 145 m³/s) nunca llega a activarse.
    """
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if _empty(yt):
        return float("nan")
    denom = np.maximum(np.abs(yt), eps)
    return float(100.0 * np.mean(np.abs((yt - yp) / denom)))


def nse(y_true, y_pred) -> float:
    """Nash-Sutcliffe. 1 es predicción perfecta; 0 iguala a la media observada."""
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if _empty(yt):
        return float("nan")
    denom = float(np.sum((yt - yt.mean()) ** 2))
    if denom == 0.0:
        return float("nan")
    return float(1.0 - np.sum((yt - yp) ** 2) / denom)


def kge(y_true, y_pred) -> float:
    """Kling-Gupta (2009): 1 − sqrt((r−1)² + (α−1)² + (β−1)²).

    Con una predicción constante la correlación no está definida; por convención
    se toma r = 0, que es lo que da el valor de referencia KGE(media) = −0,41.
    """
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if yt.size < 2:
        return float("nan")
    sd_obs, sd_sim = float(yt.std()), float(yp.std())
    mean_obs, mean_sim = float(yt.mean()), float(yp.mean())
    if sd_obs == 0.0 or mean_obs == 0.0:
        return float("nan")
    r = 0.0 if sd_sim == 0.0 else float(np.corrcoef(yt, yp)[0, 1])
    if not np.isfinite(r):
        r = 0.0
    alpha = sd_sim / sd_obs
    beta = mean_sim / mean_obs
    return float(1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2))


def pbias(y_true, y_pred) -> float:
    """Sesgo porcentual. Positivo = el modelo sobrestima."""
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if _empty(yt):
        return float("nan")
    total = float(np.sum(yt))
    if total == 0.0:
        return float("nan")
    return float(100.0 * np.sum(yp - yt) / total)


def r2(y_true, y_pred) -> float:
    """Coeficiente de determinación (cuadrado de la correlación de Pearson)."""
    yt, yp, _, _ = _pairs(y_true, y_pred)
    if yt.size < 2 or yt.std() == 0.0 or yp.std() == 0.0:
        return float("nan")
    return float(np.corrcoef(yt, yp)[0, 1] ** 2)


# --------------------------------------------------------------------------
# Métrica asimétrica por régimen
# --------------------------------------------------------------------------

def expectile_se(e, tau):
    """Error cuadrático asimétrico, elemento a elemento.

        ψ_τ(e) = 2 · |τ − 1{e < 0}| · e²

    Con la convención `e = observado − predicho`, un `e > 0` significa que el
    modelo **subestimó**. Por eso τ > 0,5 castiga más la subestimación (crecida)
    y τ < 0,5 castiga más la sobrestimación (estiaje).

    En τ = 0,5 el factor vale 1 en las dos ramas y ψ(e) = e² exactamente.
    """
    e = np.asarray(e, dtype=float)
    tau = np.asarray(tau, dtype=float)
    if np.any((tau <= 0.0) | (tau >= 1.0)):
        raise ValueError("tau debe estar en (0, 1)")
    w = np.where(e < 0.0, 1.0 - tau, tau)
    return 2.0 * w * e ** 2


def expectile_se_grad(e, tau):
    """Derivada de `expectile_se` respecto del **valor predicho**.

    Con `e = y − ŷ`:  ∂ψ/∂ŷ = −4 · |τ − 1{e<0}| · e.
    Es continua en e = 0 (tiende a 0 por los dos lados), que es la propiedad que
    permite usar esta pérdida para entrenar por gradiente.
    """
    e = np.asarray(e, dtype=float)
    tau = np.asarray(tau, dtype=float)
    w = np.where(e < 0.0, 1.0 - tau, tau)
    return -4.0 * w * e


def expectile_se_series(y_true, y_pred, tau, *, log: bool = True, q_floor: float = Q_FLOOR):
    """La serie ψ_τ elemento a elemento que `gral` promedia, más la máscara de
    qué filas sobrevivieron el filtro de NaN, en el orden de entrada original.

    `gral()` es sólo `sqrt(media(psi))` de esta serie: existe como función
    aparte para que un llamador (p. ej. una serie diaria por fecha) pueda
    quedarse con el detalle por fila sin reimplementar el filtrado ni el
    espacio (log o crudo) — sería fácil que las dos copias del cálculo
    divergieran con el tiempo.

    Devuelve `(psi, ok)`. `psi` tiene `ok.sum()` elementos; `ok` es un array
    booleano del mismo largo que `y_true`, así se puede indexar una fecha
    externa (`fecha[ok]`) para alinearla con `psi` sin volver a filtrar.
    """
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    if np.isscalar(tau):
        tau = np.full(y_true.shape, float(tau))
    tau = np.asarray(tau, dtype=float).ravel()
    ok = np.isfinite(y_true) & np.isfinite(y_pred) & np.isfinite(tau)
    yt, yp, tau_c = y_true[ok], y_pred[ok], tau[ok]
    if log:
        eps = np.log(np.maximum(yt, q_floor)) - np.log(np.maximum(yp, q_floor))
    else:
        eps = yt - yp
    return expectile_se(eps, tau_c), ok


def gral(y_true, y_pred, tau, *, log: bool = True, q_floor: float = Q_FLOOR) -> float:
    """G-RAL: ganancia regime-asimétrica, opcionalmente en escala logarítmica.

        G-RAL = sqrt( media( ψ_τ(ε) ) )

    con ε = ln max(y, q_floor) − ln max(ŷ, q_floor) si `log`, o ε = y − ŷ si no.

    Parameters
    ----------
    tau : array de la misma longitud que las series, o escalar.
        Sale de `rio_search.gate.build_tau`. Un τ escalar de 0,5 con `log=False`
        reproduce el RMSE exactamente.

    Notes
    -----
    Con `log=True` el resultado es adimensional (error relativo): **no** se puede
    comparar contra un RMSE en m³/s. Con `log=False` queda en m³/s.
    """
    psi, ok = expectile_se_series(y_true, y_pred, tau, log=log, q_floor=q_floor)
    if not ok.any():
        return float("nan")
    return float(np.sqrt(np.mean(psi)))


def dm_test(loss1, loss2, h: int = 1) -> dict:
    """Test de Diebold-Mariano sobre dos series de pérdida **por día**.

    `loss1` y `loss2` son la pérdida diaria de cada pronóstico — la que sea
    (ψ_τ, error cuadrático en log): el test no elige la pérdida, la recibe.
    H0: E[d] = 0 con d_t = loss1_t − loss2_t. La varianza de d̄ es HAC de
    Newey-West con `h − 1` rezagos y pesos de Bartlett — los errores a h pasos
    son MA(h−1) incluso para un pronóstico óptimo (Diebold & Mariano 1995) — y
    el estadístico lleva la corrección de muestra chica de
    Harvey-Leybourne-Newbold (1997).

    **dm > 0 significa que el primer pronóstico pierde** (su pérdida media es
    mayor). La p es bilateral y sale de la normal estándar: con un VAL de un año
    (n ≥ 285) la diferencia con la t de Student es irrelevante, y el repo no
    carga scipy para eso.

    Complementa al umbral de ruido del corredor, no lo reemplaza: aquél cubre el
    ruido de inicialización entre semillas; éste, el ruido de la muestra
    temporal, que es el que queda cuando las semillas ya están promediadas.
    """
    import math

    l1 = np.asarray(loss1, dtype=float).ravel()
    l2 = np.asarray(loss2, dtype=float).ravel()
    if l1.shape != l2.shape:
        raise ValueError("las dos series de pérdida deben tener la misma longitud")
    if h < 1:
        raise ValueError("h debe ser >= 1")
    ok = np.isfinite(l1) & np.isfinite(l2)
    d = l1[ok] - l2[ok]
    n = int(d.size)
    salida = {"dm": float("nan"), "p": float("nan"), "n": n, "mean_d": float("nan")}
    if n < max(2 * h, 10):
        return salida                       # con tan pocos días el test no dice nada

    dbar = float(d.mean())
    dc = d - dbar
    var = float(np.mean(dc * dc))
    for k in range(1, h):
        var += 2.0 * (1.0 - k / h) * float(np.mean(dc[k:] * dc[:-k]))
    var = max(var, 1e-300) / n              # Bartlett garantiza var >= 0; el piso
    dm = dbar / math.sqrt(var)              # evita el 0/0 de dos series idénticas
    dm *= math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)      # HLN 1997
    salida.update(dm=float(dm), p=float(math.erfc(abs(dm) / math.sqrt(2.0))),
                  mean_d=dbar)
    return salida


def violation_rates(
    y_true, y_pred, tau, *,
    wet: float = WET_THRESHOLD,
    dry: float = DRY_THRESHOLD,
) -> dict:
    """Tasas de violación operativa, el complemento obligatorio de G-RAL.

    Un escalar agregado puede expresar "subestimar cuesta caro", nunca "nunca
    subestimar". La restricción dura se mide acá:

    - ``v_plus``  : P(subestima | régimen húmedo)   — debe bajar
    - ``v_minus`` : P(sobrestima | régimen seco)    — debe bajar
    - ``fa_wet``  : P(sobrestima | régimen húmedo)  — falsa alarma, contrapeso
      indispensable: sin ella la forma trivial de bajar ``v_plus`` es pronosticar
      siempre de más.
    - ``fa_dry``  : P(subestima | régimen seco)

    Devuelve NaN en la tasa cuyo régimen no tiene días en la muestra.
    """
    yt, yp, tau_c, _ = _pairs(y_true, y_pred, tau)
    out = {"v_plus": float("nan"), "v_minus": float("nan"),
           "fa_wet": float("nan"), "fa_dry": float("nan"),
           "n_wet": 0, "n_dry": 0}
    if _empty(yt):
        return out
    e = yt - yp
    is_wet, is_dry = tau_c > wet, tau_c < dry
    out["n_wet"], out["n_dry"] = int(is_wet.sum()), int(is_dry.sum())
    if out["n_wet"]:
        out["v_plus"] = float(np.mean(e[is_wet] > 0))
        out["fa_wet"] = float(np.mean(e[is_wet] < 0))
    if out["n_dry"]:
        out["v_minus"] = float(np.mean(e[is_dry] < 0))
        out["fa_dry"] = float(np.mean(e[is_dry] > 0))
    return out


def skill_score(metric_model: float, metric_reference: float) -> float:
    """1 − métrica_modelo / métrica_referencia. Positivo = mejor que la referencia.

    Válido para métricas donde menos es mejor (RMSE, MAE, G-RAL).
    """
    if not np.isfinite(metric_model) or not np.isfinite(metric_reference):
        return float("nan")
    if metric_reference == 0.0:
        return float("nan")
    return float(1.0 - metric_model / metric_reference)


def evaluate(y_true, y_pred, tau=None, *, q_floor: float = Q_FLOOR) -> dict:
    """Todas las métricas de una vez, con la cobertura efectiva.

    Si `tau` es None se omiten G-RAL y las tasas de violación: el resto de las
    métricas no dependen del régimen.
    """
    _, _, _, coverage = _pairs(y_true, y_pred)
    out = {
        "n": int(np.sum(np.isfinite(np.asarray(y_true, float).ravel())
                        & np.isfinite(np.asarray(y_pred, float).ravel()))),
        "coverage": coverage,
        "rmse": rmse(y_true, y_pred),
        "mae": mae(y_true, y_pred),
        "mape": mape(y_true, y_pred),
        "nse": nse(y_true, y_pred),
        "kge": kge(y_true, y_pred),
        "pbias": pbias(y_true, y_pred),
        "r2": r2(y_true, y_pred),
    }
    if tau is not None:
        out["gral"] = gral(y_true, y_pred, tau, log=True, q_floor=q_floor)
        out["gral_raw"] = gral(y_true, y_pred, tau, log=False)
        out.update(violation_rates(y_true, y_pred, tau))
    return out
