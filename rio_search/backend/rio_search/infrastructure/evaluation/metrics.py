"""Metricas de evaluacion (Fase 2, docs/rio_search_plan.md §3.7): funciones puras con NumPy,
nunca Polars ni pandas (Decision #9) -- reciben y devuelven arrays/floats, sin efectos de lado.
Viven en `infrastructure`, no en `domain`: el dominio de este repo se mantiene sin dependencias
de terceros (ver `domain/datasets/feature_transform.py`: "el dominio no importa Polars"), y
NumPy es la unica libreria numerica que estas funciones necesitan -- mismo criterio que
`infrastructure.datasets.sequence_builder`/`target_builder` (Fase 1), que ya usan NumPy en
`infrastructure` por la misma razon.

Todas las funciones ignoran pares no finitos (NaN/inf) en `y_true`/`y_pred` antes de calcular
-- asi cubren los huecos de targets conocidos en TEST (§2.1) sin que el llamador tenga que
pre-filtrar. Devuelven `nan` cuando no queda ningun par valido (o cuando la metrica no esta
definida, p. ej. NSE con varianza observada cero).
"""

from __future__ import annotations

import numpy as np

ArrayLike = "np.ndarray | list[float]"


def _paired_finite(y_true: ArrayLike, y_pred: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    obs = np.asarray(y_true, dtype=np.float64)
    sim = np.asarray(y_pred, dtype=np.float64)
    mask = np.isfinite(obs) & np.isfinite(sim)
    return obs[mask], sim[mask]


def rmse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    obs, sim = _paired_finite(y_true, y_pred)
    if obs.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((obs - sim) ** 2)))


def mae(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    obs, sim = _paired_finite(y_true, y_pred)
    if obs.size == 0:
        return float("nan")
    return float(np.mean(np.abs(obs - sim)))


def mape(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Porcentaje; excluye pares con observado 0 (division indefinida)."""
    obs, sim = _paired_finite(y_true, y_pred)
    mask = obs != 0
    obs, sim = obs[mask], sim[mask]
    if obs.size == 0:
        return float("nan")
    return float(100.0 * np.mean(np.abs((obs - sim) / obs)))


def nse(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Nash-Sutcliffe: `1 - sum((obs-sim)^2) / sum((obs-mean(obs))^2)`. `1.0` en prediccion
    perfecta; `nan` si la varianza observada es cero (denominador indefinido)."""
    obs, sim = _paired_finite(y_true, y_pred)
    if obs.size == 0:
        return float("nan")
    denom = float(np.sum((obs - obs.mean()) ** 2))
    if denom == 0.0:
        return float("nan")
    return float(1.0 - np.sum((obs - sim) ** 2) / denom)


def kge(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Kling-Gupta: `1 - sqrt((r-1)^2 + (alpha-1)^2 + (beta-1)^2)` con `r` = correlacion de
    Pearson, `alpha` = std(sim)/std(obs), `beta` = mean(sim)/mean(obs). Cuando `sim` es
    constante (`std(sim) == 0`, p. ej. predecir siempre la media de `obs`) la correlacion es
    matematicamente indefinida (0/0); por convencion de la literatura de KGE se toma `r = 0`
    en ese caso -- da el resultado conocido "KGE de predecir la media = 1 - sqrt(2) ~= -0.41"
    (§5: valor de referencia para el test)."""
    obs, sim = _paired_finite(y_true, y_pred)
    if obs.size == 0:
        return float("nan")
    obs_std = float(obs.std())
    obs_mean = float(obs.mean())
    if obs_std == 0.0 or obs_mean == 0.0:
        return float("nan")
    sim_std = float(sim.std())
    sim_mean = float(sim.mean())
    if sim_std == 0.0:
        r = 0.0
    else:
        with np.errstate(invalid="ignore"):
            r = float(np.corrcoef(obs, sim)[0, 1])
        if not np.isfinite(r):
            r = 0.0
    alpha = sim_std / obs_std
    beta = sim_mean / obs_mean
    return float(1.0 - np.sqrt((r - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2))


def pbias(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Porcentaje de sesgo: `100 * sum(sim-obs) / sum(obs)`."""
    obs, sim = _paired_finite(y_true, y_pred)
    if obs.size == 0 or float(np.sum(obs)) == 0.0:
        return float("nan")
    return float(100.0 * np.sum(sim - obs) / np.sum(obs))


def r_squared(y_true: ArrayLike, y_pred: ArrayLike) -> float:
    """Coeficiente de determinacion como correlacion de Pearson al cuadrado (convencion
    hidrologica habitual, distinta de NSE)."""
    obs, sim = _paired_finite(y_true, y_pred)
    if obs.size < 2 or obs.std() == 0.0 or sim.std() == 0.0:
        return float("nan")
    with np.errstate(invalid="ignore"):
        r = float(np.corrcoef(obs, sim)[0, 1])
    if not np.isfinite(r):
        return float("nan")
    return float(r**2)


def peak_error(y_true: ArrayLike, y_pred: ArrayLike, top_fraction: float = 0.05) -> dict[str, float]:
    """MAE y sesgo (`mean(sim-obs)`) sobre el `top_fraction` (default 5%) de mayor caudal
    observado (§3.7: "error en picos")."""
    obs, sim = _paired_finite(y_true, y_pred)
    n = obs.size
    if n == 0:
        return {"mae": float("nan"), "bias": float("nan"), "n": 0.0}
    k = max(1, int(np.ceil(n * top_fraction)))
    idx = np.argsort(obs)[-k:]
    obs_peak, sim_peak = obs[idx], sim[idx]
    return {
        "mae": float(np.mean(np.abs(obs_peak - sim_peak))),
        "bias": float(np.mean(sim_peak - obs_peak)),
        "n": float(k),
    }


def skill_score(rmse_model: float, rmse_reference: float) -> float:
    """`1 - RMSE_modelo / RMSE_persistencia` (§3.7). Cuando `rmse_model == rmse_reference`
    (el propio modelo evaluado ES la persistencia, o cualquier caso degenerado con RMSE
    identico) da `0.0` exacto en punto flotante (`1 - x/x == 1 - 1.0 == 0.0` para `x != 0`),
    no una aproximacion -- es la verificacion del criterio de cierre de la Fase 2 ("skill de
    persistencia = 0 por construccion")."""
    if not np.isfinite(rmse_reference) or rmse_reference == 0.0:
        return float("nan")
    return float(1.0 - rmse_model / rmse_reference)
