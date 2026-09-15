"""Modulador de régimen: de la lluvia a τ, un valor por día.

Produce el τ que consume `rio_search.metrics.gral`. El diseño y la evidencia que
lo justifica están en `docs/funcion_ganancia_regimen.html`; en resumen:

    A(t) = percentil( Σ_{i=1..30}  P̄(t−i) )            humedad antecedente observada
    F(t) = percentil( Σ_{k=1..14}  γ^k · P̂(t+k) )      lluvia pronosticada, por lead
    W(t) = w_ant · A(t) + w_fc · F(t)
    r(t) = tanh( κ · (2·W(t) − 1) )                    índice de régimen en [−1, +1]
    τ(t) = clip( 0,5 + (τ_max − 0,5)·r(t), 1−τ_max, τ_max )

Dos invariantes que no se pueden romper:

1. **El modulador sólo puede leer información disponible en t₀.** Nunca el caudal
   observado del día que se quiere predecir. Condicionar la verificación sobre
   el resultado observado vuelve el score manipulable: un modelo sesgado a
   crecida quedaría bien evaluado justo en los días donde se lo mira.
   `assert_causal` verifica esto sobre las columnas que se le pasen.

2. **La serie de lluvia tiene que ser estacionaria.** `lluvia_acumulada_mm` en
   Gold es una *suma* sobre un número variable de estaciones (0 a 177 según la
   época): usarla directamente haría que el régimen dependa de cuántos
   pluviómetros había. Usar la media por estación o la grilla MERGE de CPTEC.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

__all__ = ["GateParams", "DEFAULT_PARAMS", "pct_rank", "lead_weights",
           "rolling_sum", "forecast_accum", "regime_index", "tau_from_index",
           "build_tau", "assert_causal", "regime_labels"]


@dataclass(frozen=True)
class GateParams:
    """Parámetros del modulador. Ver §04 de docs/funcion_ganancia_regimen.html: cuál se declara y cuál se ajusta."""

    #: Asimetría máxima. τ_max = 0,85 equivale a declarar que subestimar en
    #: crecida plena cuesta τ/(1−τ) = 5,7 veces lo que sobrestimar.
    #: **No se ajusta a los datos**: codifica un costo operativo. Sensibilidad sí.
    tau_max: float = 0.85
    #: Nitidez del tanh. 2,2 reparte los días ≈ 35 / 30 / 35 %.
    kappa: float = 2.2
    #: Decaimiento del peso por lead del pronóstico (los leads cortos pesan más).
    gamma: float = 0.85
    #: Pesos de humedad antecedente y de pronóstico. El 0,35 / 0,65 sale de la
    #: evidencia: la señal de pronóstico es la que aísla el riesgo de subestimar.
    w_ant: float = 0.35
    w_fc: float = 0.65
    #: Ventanas, en días.
    ant_days: int = 30
    fc_days: int = 14

    def __post_init__(self):
        if not 0.5 < self.tau_max < 1.0:
            raise ValueError("tau_max debe estar en (0,5, 1)")
        if abs(self.w_ant + self.w_fc - 1.0) > 1e-9:
            raise ValueError("w_ant + w_fc debe sumar 1")

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_PARAMS = GateParams()


def pct_rank(x) -> np.ndarray:
    """Percentil de cada valor dentro de la serie, en [0, 1]. Propaga NaN.

    Se usa el rango promedio para los empates, igual que `rank(method="average")`.
    """
    x = np.asarray(x, dtype=float).ravel()
    out = np.full(x.shape, np.nan)
    ok = np.isfinite(x)
    n = int(ok.sum())
    if n == 0:
        return out
    vals = x[ok]
    order = np.argsort(vals, kind="mergesort")
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    # promedio de rangos entre empates
    sorted_vals = vals[order]
    start = 0
    for i in range(1, n + 1):
        if i == n or sorted_vals[i] != sorted_vals[start]:
            if i - start > 1:
                ranks[order[start:i]] = (start + 1 + i) / 2.0
            start = i
    out[ok] = ranks / n
    return out


def lead_weights(gamma: float, n: int) -> np.ndarray:
    """Pesos γ^k normalizados para los leads 1..n."""
    if n < 1:
        raise ValueError("n debe ser >= 1")
    w = np.array([gamma ** k for k in range(1, n + 1)], dtype=float)
    return w / w.sum()


def rolling_sum(x, window: int, min_periods: int | None = None) -> np.ndarray:
    """Suma móvil hacia atrás **estricta**: la ventana en t cubre t−window .. t−1.

    Excluye el día t a propósito: la humedad antecedente no debe incluir la
    lluvia del propio día de emisión, que ya está contada en el estado del río.
    """
    x = np.asarray(x, dtype=float).ravel()
    if min_periods is None:
        min_periods = int(np.ceil(0.8 * window))
    n = x.size
    out = np.full(n, np.nan)
    valid = np.isfinite(x)
    filled = np.where(valid, x, 0.0)
    csum = np.concatenate(([0.0], np.cumsum(filled)))
    ccnt = np.concatenate(([0.0], np.cumsum(valid.astype(float))))
    for t in range(n):
        lo, hi = max(0, t - window), t          # [t-window, t)  -> excluye t
        if hi <= lo:
            continue
        cnt = ccnt[hi] - ccnt[lo]
        if cnt >= min_periods:
            out[t] = csum[hi] - csum[lo]
    return out


def forecast_accum(rain_future, gamma: float, n_leads: int,
                   min_periods: int | None = None) -> np.ndarray:
    """Acumulado ponderado por lead de la lluvia en t+1 .. t+n_leads.

    `rain_future` puede ser:

    - una serie diaria 1-D: se construyen los leads desplazándola. Esto es el
      modo **oráculo** (lluvia observada futura como sustituto del pronóstico)
      y sólo sirve para análisis retrospectivo, nunca para operar.
    - una matriz 2-D `(n_días, n_leads)` con el pronóstico real emitido en t.
    """
    arr = np.asarray(rain_future, dtype=float)
    w = lead_weights(gamma, n_leads)
    if arr.ndim == 1:
        n = arr.size
        leads = np.full((n, n_leads), np.nan)
        for k in range(1, n_leads + 1):
            leads[: n - k, k - 1] = arr[k:]
    elif arr.ndim == 2:
        if arr.shape[1] < n_leads:
            raise ValueError(f"se necesitan {n_leads} leads, hay {arr.shape[1]}")
        leads = arr[:, :n_leads]
    else:
        raise ValueError("rain_future debe ser 1-D o 2-D")

    if min_periods is None:
        min_periods = int(np.ceil(0.8 * n_leads))
    valid = np.isfinite(leads)
    filled = np.where(valid, leads, 0.0)
    out = (filled * w).sum(axis=1)
    out[valid.sum(axis=1) < min_periods] = np.nan
    return out


def regime_index(a_pct, f_pct, params: GateParams = DEFAULT_PARAMS) -> np.ndarray:
    """Índice de régimen r ∈ [−1, +1]. −1 estiaje pleno, 0 neutro, +1 crecida."""
    a = np.asarray(a_pct, dtype=float)
    f = np.asarray(f_pct, dtype=float)
    w = params.w_ant * a + params.w_fc * f
    return np.tanh(params.kappa * (2.0 * w - 1.0))


def tau_from_index(r, params: GateParams = DEFAULT_PARAMS) -> np.ndarray:
    """Mapea el índice de régimen a τ, acotado a [1−τ_max, τ_max]."""
    r = np.asarray(r, dtype=float)
    tau = 0.5 + (params.tau_max - 0.5) * r
    return np.clip(tau, 1.0 - params.tau_max, params.tau_max)


def build_tau(rain_daily, *, forecast_rain=None, mode: str = "oracle",
              params: GateParams = DEFAULT_PARAMS) -> dict:
    """Construye la serie τ a partir de la lluvia.

    Parameters
    ----------
    rain_daily : serie diaria de lluvia **media por estación** (mm), o media
        areal de grilla. Nunca la suma cruda sobre estaciones.
    forecast_rain : matriz `(n_días, n_leads)` de lluvia pronosticada emitida en
        cada día. Si es None y `mode="oracle"`, se sustituye por la lluvia
        observada futura.
    mode : ``"forecast"`` (operativo, requiere `forecast_rain`),
        ``"oracle"`` (retrospectivo, pronóstico perfecto),
        ``"antecedent"`` (sólo pasado: τ depende únicamente de A, es 100 %
        causal y es lo único disponible hasta que entren las columnas de
        pronóstico a Gold en la Fase 4 del roadmap).

    Returns
    -------
    dict con ``tau``, ``r``, ``a_pct``, ``f_pct``, ``mode`` y ``params``.
    """
    rain = np.asarray(rain_daily, dtype=float).ravel()
    ant = rolling_sum(rain, params.ant_days)
    a_pct = pct_rank(ant)

    if mode == "antecedent":
        f_pct = None
        w = a_pct
        r = np.tanh(params.kappa * (2.0 * w - 1.0))
    else:
        if mode == "forecast":
            if forecast_rain is None:
                raise ValueError('mode="forecast" requiere forecast_rain')
            src = forecast_rain
        elif mode == "oracle":
            src = rain if forecast_rain is None else forecast_rain
        else:
            raise ValueError(f"mode desconocido: {mode!r}")
        f_pct = pct_rank(forecast_accum(src, params.gamma, params.fc_days))
        r = regime_index(a_pct, f_pct, params)

    return {
        "tau": tau_from_index(r, params),
        "r": r,
        "a_pct": a_pct,
        "f_pct": f_pct,
        "mode": mode,
        "params": params,
    }


def regime_labels(tau, wet: float = 0.65, dry: float = 0.35) -> np.ndarray:
    """Etiqueta legible por día: ``"humedo"`` / ``"neutro"`` / ``"seco"``.

    Sólo para reportes y gráficos. G-RAL usa τ continuo, no estas etiquetas.
    """
    tau = np.asarray(tau, dtype=float)
    out = np.full(tau.shape, "neutro", dtype=object)
    out[tau > wet] = "humedo"
    out[tau < dry] = "seco"
    out[~np.isfinite(tau)] = "sin_dato"
    return out


def assert_causal(column_names) -> None:
    """Falla si alguna columna usada por el modulador mira al futuro del target.

    Test de regresión del invariante 1: ninguna columna ``*_t_mas_*d`` puede
    entrar al cálculo de τ. Es fácil de romper sin darse cuenta al evaluar sobre
    un dataframe que ya tiene los targets al lado.
    """
    offenders = [c for c in column_names if "t_mas" in str(c)]
    if offenders:
        raise ValueError(
            "el modulador no puede leer columnas de target: " + ", ".join(map(str, offenders))
        )
