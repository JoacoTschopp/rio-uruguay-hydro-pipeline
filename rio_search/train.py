"""Arnés de entrenamiento y evaluación con pérdida seleccionable.

    python -m rio_search.train --model mlp --loss gral
    python -m rio_search.train --compare            # corre la grilla 2x2 completa

El experimento que justifica el arnés es una grilla 2×2 que **separa los dos
ingredientes** de G-RAL, porque el informe encontró que no aportan lo mismo:

                      escala cruda (m³/s)      escala log
    simétrica         mse                      mse_log
    asimétrica (τ)    expectile_raw            gral

`mse` es el entrenamiento actual del proyecto. `gral` es la propuesta.
`mse_log` aísla el efecto de la transformación, y `expectile_raw` el de la
asimetría sola — que según la evidencia retrospectiva no alcanza.

Cada configuración entrena con **todo lo demás idéntico**: mismos datos, mismos
splits, misma semilla, misma arquitectura, mismo preprocesamiento. Lo único que
cambia es la pérdida.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _utf8_console() -> None:
    """La consola de Windows arranca en cp1252 y no puede escribir τ ni →.

    Sin esto el arnés muere con UnicodeEncodeError después de haber entrenado,
    que es la peor forma de fallar. `errors="replace"` garantiza que en una
    terminal vieja se degrade a un signo de pregunta en vez de romperse.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

from . import data as data_mod
from . import gate as gate_mod
from . import metrics as metrics_mod
from .models import (LOSSES, ClimatologyBaseline, DampedPersistence, DLinearCore,
                     LinearCore, LSTMCore, MLPCore, NSELoss, PersistenceBaseline,
                     SeasonalNaive, XGBoostCore)

__all__ = ["LOSS_CONFIGS", "Preprocessor", "run_experiment", "run_comparison", "main"]

#: Cada entrada es (nombre de la pérdida elemento a elemento, transformación del
#: target). La transformación log es la que estabiliza la varianza entre estiaje
#: y crecida; la pérdida expectil es la que introduce la asimetría.
LOSS_CONFIGS: dict[str, tuple[str, str]] = {
    "mse":           ("mse",       "none"),
    "mae":           ("mae",       "none"),
    "mse_log":       ("mse",       "log"),
    "expectile_raw": ("expectile", "none"),
    "gral":          ("expectile", "log"),
    "huber":         ("huber",     "none"),
    "huber_log":     ("huber",     "log"),
    "nse_loss":      ("nse",       "none"),
}


# --------------------------------------------------------------------------
# Preprocesamiento — todo se ajusta con TRAIN únicamente
# --------------------------------------------------------------------------

TARGET_TRANSFORMS = ("none", "log", "pow4", "boxcox", "yeojohnson")

SCALINGS = ("standard", "robust", "minmax", "quantile", "none")


def _yeojohnson(y, lam):
    """Yeo-Johnson hacia adelante. Definida en toda la recta: es la única de la
    familia que un target delta (negativo) puede usar."""
    y = np.asarray(y, dtype=float)
    out = np.full(y.shape, np.nan)
    with np.errstate(invalid="ignore"):
        pos = y >= 0
        out[pos] = (np.log1p(y[pos]) if abs(lam) < 1e-12
                    else (np.power(y[pos] + 1.0, lam) - 1.0) / lam)
        neg = y < 0
        out[neg] = (-np.log1p(-y[neg]) if abs(lam - 2.0) < 1e-12
                    else -(np.power(1.0 - y[neg], 2.0 - lam) - 1.0) / (2.0 - lam))
    return out


def _yeojohnson_inv(z, lam):
    z = np.asarray(z, dtype=float)
    out = np.full(z.shape, np.nan)
    with np.errstate(invalid="ignore"):
        pos = z >= 0
        out[pos] = (np.expm1(z[pos]) if abs(lam) < 1e-12
                    else np.power(np.maximum(lam * z[pos] + 1.0, 1e-12), 1.0 / lam) - 1.0)
        neg = z < 0
        out[neg] = (-np.expm1(-z[neg]) if abs(lam - 2.0) < 1e-12
                    else 1.0 - np.power(np.maximum(1.0 - (2.0 - lam) * z[neg], 1e-12),
                                        1.0 / (2.0 - lam)))
    return out


def _ajustar_lambda(y, transform, q_floor, grid=None):
    """λ por máxima verosimilitud perfilada, SOLO con TRAIN y sin scipy: barrido
    fino sobre [−1, 2]. El término (λ−1)·Σ log|·| es el jacobiano — sin él, el
    óptimo colapsaría en la λ que más encoja la escala."""
    y = np.asarray(y, dtype=float).ravel()
    y = y[np.isfinite(y)]
    grid = np.linspace(-1.0, 2.0, 121) if grid is None else np.asarray(grid, float)
    if transform == "boxcox":
        y = np.maximum(y, q_floor)
        logy = np.log(y)
        jac = float(logy.sum())
        def z_de(lam):
            return logy if abs(lam) < 1e-12 else (np.power(y, lam) - 1.0) / lam
    else:                                    # yeojohnson
        jac = float((np.sign(y) * np.log1p(np.abs(y))).sum())
        def z_de(lam):
            return _yeojohnson(y, lam)
    def llf(lam):
        v = float(np.var(z_de(lam)))
        return -0.5 * y.size * np.log(max(v, 1e-300)) + (lam - 1.0) * jac
    return float(grid[int(np.argmax([llf(l) for l in grid]))])


@dataclass
class Preprocessor:
    """Imputación + escalado de features, y transformación + escalado del target.

    Los estadísticos salen sólo de TRAIN. El target se estandariza para que el
    optimizador converja, y eso no altera la asimetría: escalar por una constante
    positiva no cambia el signo del error, que es lo único que mira τ.
    """

    target_transform: str = "none"
    scaling: str = "standard"
    q_floor: float = metrics_mod.Q_FLOOR
    target_lambda: float | None = None
    x_median: np.ndarray | None = None
    x_mean: np.ndarray | None = None
    x_std: np.ndarray | None = None
    x_center: np.ndarray | None = None
    x_scale: np.ndarray | None = None
    x_train_sorted: np.ndarray | None = None
    y_mean: float | None = None
    y_std: float | None = None

    def _t(self, y):
        if self.target_transform == "log":
            return np.log(np.maximum(y, self.q_floor))
        if self.target_transform == "pow4":
            return np.power(np.maximum(y, self.q_floor), 0.25)
        if self.target_transform == "boxcox":
            lam, yf = self.target_lambda, np.maximum(y, self.q_floor)
            return np.log(yf) if abs(lam) < 1e-12 else (np.power(yf, lam) - 1.0) / lam
        if self.target_transform == "yeojohnson":
            return _yeojohnson(y, self.target_lambda)
        return y

    def _t_inv(self, z):
        if self.target_transform == "log":
            return np.exp(z)
        if self.target_transform == "pow4":
            return np.power(np.maximum(z, 0.0), 4.0)
        if self.target_transform == "boxcox":
            lam = self.target_lambda
            return (np.exp(z) if abs(lam) < 1e-12
                    else np.power(np.maximum(lam * z + 1.0, 1e-12), 1.0 / lam))
        if self.target_transform == "yeojohnson":
            return _yeojohnson_inv(z, self.target_lambda)
        return z

    def fit(self, X, Y):
        self.x_median = np.nanmedian(X, axis=0)
        self.x_median = np.where(np.isfinite(self.x_median), self.x_median, 0.0)
        Xi = self._impute(X)
        self.x_mean = Xi.mean(axis=0)
        std = Xi.std(axis=0)
        self.x_std = np.where(std > 1e-12, std, 1.0)
        # B7: centro/escala según `scaling`. Con caudales de cola pesada la media
        # y el desvío quedan dominados por las crecidas; mediana/IQR no.
        if self.scaling == "standard":
            self.x_center, self.x_scale = self.x_mean, self.x_std
        elif self.scaling == "robust":
            q25, q50, q75 = np.percentile(Xi, [25.0, 50.0, 75.0], axis=0)
            iqr = q75 - q25
            self.x_center = q50
            self.x_scale = np.where(iqr > 1e-12, iqr, 1.0)
        elif self.scaling == "minmax":
            lo, hi = Xi.min(axis=0), Xi.max(axis=0)
            ancho = hi - lo
            self.x_center = lo
            self.x_scale = np.where(ancho > 1e-12, ancho, 1.0)
        elif self.scaling == "quantile":
            self.x_train_sorted = np.sort(Xi, axis=0)
        elif self.scaling != "none":
            raise ValueError(f"scaling desconocido: {self.scaling!r}. "
                             f"Opciones: {SCALINGS}")

        if self.target_transform in ("boxcox", "yeojohnson") and self.target_lambda is None:
            self.target_lambda = _ajustar_lambda(Y[np.isfinite(Y)], self.target_transform,
                                                 self.q_floor)
        ty = self._t(Y[np.isfinite(Y)])
        self.y_mean = float(ty.mean())
        self.y_std = float(ty.std()) or 1.0
        return self

    def _impute(self, X):
        out = np.array(X, dtype=float, copy=True)
        bad = ~np.isfinite(out)
        if bad.any():
            out[bad] = np.take(self.x_median, np.where(bad)[1])
        return out

    def transform_x(self, X):
        Xi = self._impute(X)
        if self.scaling == "none":
            return Xi
        if self.scaling == "quantile":
            # CDF empírica de TRAIN, centrada en 0; fuera de rango, np.interp
            # recorta a los extremos (±0,5).
            n = self.x_train_sorted.shape[0]
            cdf = (np.arange(n) + 0.5) / n
            cols = [np.interp(Xi[:, j], self.x_train_sorted[:, j], cdf)
                    for j in range(Xi.shape[1])]
            return np.column_stack(cols) - 0.5
        return (Xi - self.x_center) / self.x_scale

    def transform_y(self, Y):
        with np.errstate(invalid="ignore"):
            return (self._t(Y) - self.y_mean) / self.y_std

    def inverse_y(self, Z):
        return self._t_inv(Z * self.y_std + self.y_mean)

    def imputed_fraction(self, X) -> float:
        X = np.asarray(X, dtype=float)
        return float(np.mean(~np.isfinite(X)))


# --------------------------------------------------------------------------
# Evaluación
# --------------------------------------------------------------------------

def _evaluate_split(y_true, y_pred, tau, horizons) -> dict:
    """Métricas por horizonte y agregadas. `y_*` son (n, n_horizontes) en m³/s."""
    per_h = {}
    for j, h in enumerate(horizons):
        per_h[f"h{h:02d}"] = metrics_mod.evaluate(y_true[:, j], y_pred[:, j], tau)
    agg = {}
    for key in ("rmse", "mae", "nse", "kge", "gral", "pbias",
                "v_plus", "v_minus", "fa_wet", "fa_dry"):
        vals = [m[key] for m in per_h.values() if key in m and np.isfinite(m[key])]
        agg[key] = float(np.mean(vals)) if vals else float("nan")
    return {"mean": agg, "per_horizon": per_h}


# --------------------------------------------------------------------------
# Corrida
# --------------------------------------------------------------------------

def run_experiment(ds, splits, *, model: str = "mlp", loss: str = "mse",
                   hidden: int = 64, epochs: int = 600, lr: float = 0.01,
                   l2: float = 1e-4, patience: int = 60, seed: int = 20260828,
                   eval_tau=None, train_tau=None, on_epoch=None, verbose: bool = False,
                   evaluar_test: bool = True, per_horizon: bool = False,
                   target_param: str = "nivel",
                   target_transform: str | None = None,
                   scaling: str = "standard",
                   lookback: int | None = None,
                   lstm_hidden: int = 32, lstm_layers: int = 1, lstm_dropout: float = 0.0,
                   lstm_bidirectional: bool = False,
                   return_predictions: bool = False) -> dict:
    """Entrena una configuración y la evalúa en VAL y, si se pide, en TEST.

    `eval_tau` separa el τ con el que se **entrena** (`ds.tau`) del τ con el que
    se **mide** (por defecto el mismo). Hace falta en el barrido de τ_max: si la
    evaluación usara el τ de cada corrida, el umbral de "día húmedo" se movería
    junto con el parámetro y V+ se compararía sobre conjuntos de días distintos
    en cada fila. Con un τ de referencia fijo, las filas son comparables.

    `train_tau` es el espejo del anterior: reemplaza el τ con el que se
    **entrena** sin tocar el de la evaluación. Es el control de atribución de
    B1.06 — un τ constante entrena "asimetría sin modulador", y como la métrica
    sigue usando `ds.tau`, la diferencia con el ancla mide sólo lo que aporta
    que τ varíe día a día.

    `per_horizon=True` (B5.02) entrena un modelo independiente por horizonte, con
    los mismos HP y el mismo preprocesamiento: la única diferencia con el
    multi-salida es que la representación oculta no se comparte. La máscara de
    NaN opera por columna en ambos casos, así que cada modelo ve todas las filas
    donde SU horizonte existe. La evaluación junta las 8 columnas y usa el mismo
    `_evaluate_split`: los dos modos son comparables fila contra fila.

    `target_transform` (B3.03) reemplaza la transformación acoplada a la pérdida:
    la pérdida elemento a elemento no cambia, cambia el espacio donde se calcula.
    `boxcox` y `yeojohnson` ajustan su λ en TRAIN por máxima verosimilitud. La
    evaluación no se mueve del espacio original del caudal.

    `target_param="delta"` (B3.04) cambia QUÉ se predice: el modelo aprende
    Q(t+h) − Q(t) y la predicción final reconstruye sumando el q_actual del día.
    La parte trivial —la persistencia— queda descontada del aprendizaje, pero la
    evaluación no se mueve: siempre en m³/s contra el caudal observado. Un delta
    puede ser negativo, así que sólo admite transformaciones del target que
    acepten negativos.

    `scaling` (B7.02) elige el centrado/escala de las features — estándar,
    mediana/IQR, minmax, CDF empírica o nada. Los estadísticos salen siempre de
    TRAIN; el escalado del target no cambia (su transformación es el eje B3).

    `lookback` (obligatorio con `model="dlinear"` o `model="lstm"`, B4.13/B4.14) es
    el L de la ventana que `with_lookback` ya aplanó en `ds.X`: tanto `DLinearCore`
    como `LSTMCore` lo necesitan para reconstruir (N, L, F). `lstm_*` son la
    arquitectura del LSTM (B4.14), declarados, no tuneados por VAL.

    `evaluar_test=False` **no calcula** TEST y no lo deja en la salida. Es la
    forma estructural de sostener la regla del protocolo de búsqueda: TEST se mira
    una sola vez, al final, sobre la configuración campeona. Mientras el bloque
    exista en el JSON, la regla depende de que quien lo lee se abstenga; sin el
    bloque, no hay nada de qué abstenerse.
    """
    if loss not in LOSS_CONFIGS:
        raise KeyError(f"pérdida desconocida: {loss}. Opciones: {list(LOSS_CONFIGS)}")
    loss_name, transform = LOSS_CONFIGS[loss]
    loss_fn = LOSSES[loss_name]

    if target_transform is not None:                    # B3.03: cierra el gap G-02
        if target_transform not in TARGET_TRANSFORMS:
            raise ValueError(f"target_transform desconocido: {target_transform!r}. "
                             f"Opciones: {TARGET_TRANSFORMS}")
        transform = target_transform

    if target_param not in ("nivel", "delta"):
        raise ValueError(f"target_param desconocido: {target_param!r}. Opciones: "
                         "nivel, delta (ratio es B3.05 y depende de esta celda)")
    if target_param == "delta" and transform in ("log", "pow4", "boxcox"):
        raise ValueError(f"target_param=delta no admite la transformación {transform!r}: "
                         "un delta puede ser negativo. Usar una pérdida con "
                         "transformación none (p. ej. expectile_raw)")

    tr, va, te = splits.train, splits.val, splits.test
    # B3.04: con target delta el modelo aprende Q(t+h) − Q(t) — el residuo sobre
    # la persistencia — y la reconstrucción devuelve la parte trivial al final.
    Yobj = ds.Y - ds.q_actual[:, None] if target_param == "delta" else ds.Y
    if scaling not in SCALINGS:
        raise ValueError(f"scaling desconocido: {scaling!r}. Opciones: {SCALINGS}")
    pre = Preprocessor(target_transform=transform, scaling=scaling).fit(ds.X[tr], Yobj[tr])

    Xtr, Xva, Xte = (pre.transform_x(ds.X[m]) for m in (tr, va, te))
    Ztr, Zva = pre.transform_y(Yobj[tr]), pre.transform_y(Yobj[va])

    if loss_name == "nse":                  # B1.10: σ²_h por horizonte, de TRAIN
        loss_fn = NSELoss(np.nanvar(Ztr, axis=0))

    core_cls = {"mlp": MLPCore, "linear": LinearCore, "xgb": XGBoostCore,
                "dlinear": DLinearCore, "lstm": LSTMCore}[model]
    if model in ("dlinear", "lstm"):
        if not lookback:
            raise ValueError(f"model={model!r} necesita lookback: ds.X tiene que venir "
                             "de with_lookback(ds, lookback) y el mismo L pasarse acá")
        n_in = Xtr.shape[1]
        if n_in % lookback != 0:
            raise ValueError(f"lookback={lookback} no divide a n_in={n_in}: "
                             "ds.X no parece venir de with_lookback con ese L")
    kw = dict(loss=loss_fn, epochs=epochs, lr=lr, l2=l2, patience=patience,
              seed=seed, verbose=verbose)

    def nuevo_core(loss_j=None):
        kw2 = kw if loss_j is None else dict(kw, loss=loss_j)
        if model == "mlp":
            return core_cls(hidden=hidden, **kw2)
        if model == "dlinear":
            return core_cls(lookback=lookback, n_features=Xtr.shape[1] // lookback, **kw2)
        if model == "lstm":
            return core_cls(lookback=lookback, n_features=Xtr.shape[1] // lookback,
                            hidden_size=lstm_hidden, num_layers=lstm_layers,
                            dropout=lstm_dropout, bidirectional=lstm_bidirectional, **kw2)
        return core_cls(**kw2)

    if per_horizon and on_epoch is not None:
        raise ValueError("per_horizon no soporta on_epoch: el podado por época está "
                         "definido sobre un único entrenamiento, no sobre ocho")

    tau_entrena = ds.tau if train_tau is None else np.asarray(train_tau, dtype=float)
    tau_tr = tau_entrena[tr] if loss_fn.uses_tau else None
    tau_va = tau_entrena[va] if loss_fn.uses_tau else None
    t0 = time.perf_counter()
    if per_horizon:
        cores = []
        for j in range(Ztr.shape[1]):
            # NSE por horizonte: cada modelo recibe SU σ², no el vector entero
            loss_j = (NSELoss(loss_fn.var[j:j + 1], eps=loss_fn.eps)
                      if isinstance(loss_fn, NSELoss) and loss_fn.var is not None
                      else None)
            c = nuevo_core(loss_j)
            c.fit(Xtr, Ztr[:, j:j + 1], tau=tau_tr,
                  X_val=Xva, Y_val=Zva[:, j:j + 1], tau_val=tau_va)
            cores.append(c)
    else:
        c = nuevo_core()
        c.fit(Xtr, Ztr, tau=tau_tr, X_val=Xva, Y_val=Zva, tau_val=tau_va,
              on_epoch=on_epoch)
        cores = [c]
    fit_seconds = time.perf_counter() - t0

    out = {
        "model": model, "loss": loss, "elementwise_loss": loss_name,
        "target_transform": transform, "target_param": target_param,
        "target_lambda": pre.target_lambda, "scaling": scaling,
        "hidden": hidden if model == "mlp" else None,
        "lr": lr, "l2": l2, "patience": patience, "epochs_max": epochs,
        "seed": seed,
        "horizonte": "per_horizon" if per_horizon else "multi_output",
        "epochs_run": ([len(c.history) for c in cores] if per_horizon
                       else len(cores[0].history)),
        "best_epoch": ([c.best_epoch for c in cores] if per_horizon
                       else cores[0].best_epoch),
        "pruned": any(c.pruned for c in cores),
        "time_fit_s": round(fit_seconds, 3),
        "imputed_fraction_train": round(pre.imputed_fraction(ds.X[tr]), 4),
        "splits": splits.describe(ds.fecha),
    }
    if hasattr(cores[0], "hp"):        # B4.08: hiperparámetros de árbol declarados,
        out["model_hp"] = cores[0].hp()  # sin equivalente en lr/l2/epochs/patience
    tau_eval = ds.tau if eval_tau is None else np.asarray(eval_tau, dtype=float)
    out["eval_tau_is_train_tau"] = eval_tau is None and train_tau is None
    out["train_tau_es_el_del_modulador"] = train_tau is None
    out["test_evaluado"] = bool(evaluar_test)
    a_evaluar = [("val", va, Xva)] + ([("test", te, Xte)] if evaluar_test else [])
    for name, m, X in a_evaluar:
        Z = (np.hstack([c.predict(X) for c in cores]) if per_horizon
             else cores[0].predict(X))
        inv = pre.inverse_y(Z)
        if target_param == "delta":
            inv = ds.q_actual[m][:, None] + inv
        pred = np.maximum(inv, 0.0)
        out[name] = _evaluate_split(ds.Y[m], pred, tau_eval[m], ds.horizons)
        if return_predictions:
            # G-05 (B10): la predicción en m³/s, en memoria, para que un ensemble
            # promedie PREDICCIONES y no métricas. Es un ndarray a propósito: no
            # debe caer en un JSON de resultados — quien lo pide lo consume y lo
            # descarta (rio_search/ensemble.py).
            out.setdefault("predicciones", {})[name] = pred
    return out


def run_baselines(ds, splits, *, evaluar_test: bool = True) -> dict:
    """Persistencia, persistencia amortiguada y climatología, sobre los mismos splits."""
    n_h = len(ds.horizons)
    preds = {
        "persistencia": PersistenceBaseline().predict(ds.q_actual, n_h),
        "persistencia x 0.90": DampedPersistence(0.90).predict(ds.q_actual, n_h),
        "persistencia x 1.10": DampedPersistence(1.10).predict(ds.q_actual, n_h),
        "climatologia 30 d": ClimatologyBaseline(30).predict(ds.q_actual, n_h),
    }
    # El estacional es el único baseline que aprende algo, y lo aprende de TRAIN
    # únicamente: la media por día del año no puede ver los años de VAL/TEST.
    estacional = SeasonalNaive(7).fit(ds.fecha[splits.train], ds.q_actual[splits.train])
    preds[estacional.name] = estacional.predict(ds.fecha, ds.horizons)
    splits_a_medir = [("val", splits.val)] + ([("test", splits.test)] if evaluar_test else [])
    out = {}
    for name, p in preds.items():
        row = {"model": name, "loss": None}
        for split_name, m in splits_a_medir:
            row[split_name] = _evaluate_split(ds.Y[m], p[m], ds.tau[m], ds.horizons)
        out[name] = row
    return out


def _aggregate_seeds(runs: list[dict], split: str) -> dict:
    """Media y desvío entre semillas de cada métrica agregada.

    Con 285 días de TEST y una sola semilla, una diferencia de 0,01 en una tasa
    de violación es ruido de inicialización. Reportar el desvío entre semillas es
    lo que separa un resultado de un número.
    """
    keys = runs[0][split]["mean"].keys()
    out = {}
    for k in keys:
        vals = np.array([r[split]["mean"][k] for r in runs], dtype=float)
        vals = vals[np.isfinite(vals)]
        out[k] = float(vals.mean()) if vals.size else float("nan")
        out[f"{k}_sd"] = float(vals.std(ddof=1)) if vals.size > 1 else 0.0
    return out


def run_experiment_seeds(ds, splits, *, seeds, **kw) -> dict:
    """Corre la misma configuración con varias semillas y agrega."""
    runs = [run_experiment(ds, splits, seed=s, **kw) for s in seeds]
    merged = dict(runs[0])
    merged["seeds"] = list(seeds)
    merged["n_seeds"] = len(seeds)
    for split in ("val", "test"):
        if split not in runs[0]:            # corrida con evaluar_test=False
            merged.pop(split, None)
            continue
        merged[split] = {"mean": _aggregate_seeds(runs, split),
                         "per_seed": [r[split]["mean"] for r in runs],
                         "per_horizon": runs[0][split]["per_horizon"]}
    merged["time_fit_s"] = round(sum(r["time_fit_s"] for r in runs), 3)
    return merged


def run_comparison(ds, splits, *, model: str = "mlp", losses=None,
                   seeds=(20260828,), **kw) -> dict:
    losses = list(losses or LOSS_CONFIGS)
    results = {"dataset": {
        "n": len(ds), "desde": str(ds.fecha.min().date()), "hasta": str(ds.fecha.max().date()),
        "n_features": ds.X.shape[1], "features": ds.feature_names,
        "horizons": list(ds.horizons), "tau_mode": ds.tau_mode,
        "tau_reparto": {
            "humedo_pct": round(100 * float(np.mean(ds.tau > metrics_mod.WET_THRESHOLD)), 1),
            "neutro_pct": round(100 * float(np.mean(
                (ds.tau >= metrics_mod.DRY_THRESHOLD) & (ds.tau <= metrics_mod.WET_THRESHOLD))), 1),
            "seco_pct": round(100 * float(np.mean(ds.tau < metrics_mod.DRY_THRESHOLD)), 1),
        },
    }, "splits": splits.describe(ds.fecha),
        "baselines": run_baselines(ds, splits, evaluar_test=kw.get("evaluar_test", True)),
        "models": {}}
    results["seeds"] = list(seeds)
    for loss in losses:
        print(f"  entrenando {model} con loss={loss} "
              f"({len(seeds)} semilla{'s' if len(seeds) > 1 else ''}) ...", flush=True)
        results["models"][loss] = run_experiment_seeds(
            ds, splits, model=model, loss=loss, seeds=seeds, **kw)
    return results


# --------------------------------------------------------------------------
# Reporte de consola
# --------------------------------------------------------------------------

def _fmt(v, nd=3):
    """Formato inequívoco: nunca separador de miles, que en es-AR se confunde
    con la coma decimal (`1.699` se lee como 1,699 y son 1699 m³/s)."""
    if v is None or not np.isfinite(v):
        return "—"
    return f"{v:.{nd}f}"


def _fmt_sd(v, sd, nd=3):
    if v is None or not np.isfinite(v):
        return "—"
    return f"{v:.{nd}f}" + (f"±{sd:.{nd}f}" if sd else "")


def _row(label: str, m: dict) -> str:
    g = lambda k: m.get(f"{k}_sd", 0.0)
    return (f"{label:22s}{_fmt(m['rmse'], 0):>12s}{_fmt(m['nse'], 2):>8s}{_fmt(m['kge'], 2):>8s}"
            f"{_fmt_sd(m['gral'], g('gral')):>15s}"
            f"{_fmt_sd(m['v_plus'], g('v_plus')):>15s}"
            f"{_fmt_sd(m['v_minus'], g('v_minus')):>15s}"
            f"{_fmt(m['fa_wet'], 2):>9s}")


def print_table(results: dict, split: str = "test") -> None:
    hdr = (f"{'modelo / pérdida':22s}{'RMSE m3/s':>12s}{'NSE':>8s}{'KGE':>8s}"
           f"{'G-RAL':>15s}{'V+ húm':>15s}{'V− seco':>15s}{'FA húm':>9s}")
    print("\n" + "=" * len(hdr))
    print(f"  SPLIT: {split.upper()}   (media sobre los 8 horizontes)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))

    rows = []
    for name, r in results["baselines"].items():
        rows.append((name, r[split]["mean"]))
    print("  " + "· baselines ·")
    for name, m in rows:
        print(_row(name, m))
    print("  " + "· modelos entrenados ·")
    for loss, r in results["models"].items():
        print(_row(f"{r['model']} · {loss}", r[split]["mean"]))
    print("-" * len(hdr))
    print("  V+ = P(subestima | régimen húmedo)   V− = P(sobrestima | régimen seco)")
    print("  FA = P(sobrestima | régimen húmedo), la falsa alarma que contrapesa a V+")


def _rankings(results: dict, split: str = "test") -> dict:
    items = [(f"{r['model']}·{loss}", r[split]["mean"]) for loss, r in results["models"].items()]
    items += [(n, r[split]["mean"]) for n, r in results["baselines"].items()]
    out = {}
    for key in ("rmse", "gral", "kge"):
        valid = [(n, m[key]) for n, m in items if np.isfinite(m[key])]
        reverse = key == "kge"          # en KGE, más es mejor
        out[key] = [n for n, _ in sorted(valid, key=lambda kv: kv[1], reverse=reverse)]
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _parse_hidden(s: str) -> int | list[int]:
    """`38` → una capa; `38,38` → lista de anchos (B4.03). Un entero se queda
    entero para que el nombre del archivo de salida y el JSON no cambien."""
    partes = [int(x) for x in str(s).split(",") if x.strip()]
    if not partes:
        raise argparse.ArgumentTypeError(f"--hidden inválido: {s!r}")
    return partes[0] if len(partes) == 1 else partes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=["mlp", "linear", "xgb", "dlinear", "lstm"], default="mlp")
    p.add_argument("--loss", choices=list(LOSS_CONFIGS), default="mse")
    p.add_argument("--compare", action="store_true",
                   help="corre todas las pérdidas de LOSS_CONFIGS y compara")
    p.add_argument("--target", choices=["caudal", "nivel"], default="caudal")
    p.add_argument("--tau-mode", choices=["oracle", "antecedent", "forecast"], default="oracle")
    p.add_argument("--tau-max", type=float, default=gate_mod.DEFAULT_PARAMS.tau_max)
    p.add_argument("--tau-constante", type=float, default=None, metavar="TAU",
                   help="entrenar con este τ fijo en vez del modulador (la evaluación "
                        "sigue usando el τ del modulador). Es el control de atribución "
                        "de B1.06: separa 'la asimetría ayuda' de 'el modulador ayuda'")
    p.add_argument("--hidden", type=_parse_hidden, default=64,
                   help="ancho de la capa oculta, o lista '38,38' para un MLP "
                        "profundo (B4.03): N capas tanh, mismas reglas de "
                        "entrenamiento")
    p.add_argument("--epochs", type=int, default=600)
    p.add_argument("--lr", type=float, default=0.01)
    p.add_argument("--l2", type=float, default=1e-4)
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--seeds", type=int, default=1,
                   help="cuántas semillas correr por configuración (media +- desvío)")
    p.add_argument("--patience", type=int, default=60,
                   help="épocas sin mejorar en VAL antes de cortar (early stopping)")
    p.add_argument("--train-start", default=None,
                   help="piso temporal de TRAIN, p. ej. 2008-01-01. Por defecto, el "
                        "principio de la serie")
    p.add_argument("--horizonte", choices=["multi_output", "per_horizon"],
                   default="multi_output",
                   help="B5: una red con todas las salidas, o un modelo por horizonte")
    p.add_argument("--target-transform", choices=list(TARGET_TRANSFORMS), default=None,
                   help="B3.03: reemplaza la transformación del target acoplada a la "
                        "pérdida (λ de Box-Cox / Yeo-Johnson se ajusta en TRAIN)")
    p.add_argument("--target-param", choices=["nivel", "delta"], default="nivel",
                   help="B3.04: qué se predice — el caudal (nivel) o su cambio "
                        "Q(t+h)−Q(t) (delta), reconstruido sumando q_actual")
    p.add_argument("--scaling", choices=list(SCALINGS), default="standard",
                   help="B7: escalado de features, con estadísticos de TRAIN "
                        "(robust = mediana/IQR)")
    p.add_argument("--lookback", type=int, default=None, metavar="L",
                   help="ventana causal de features (B2.17): el MLP consume la "
                        "ventana aplanada; sin el flag, sólo los lags de siempre")
    p.add_argument("--lstm-hidden", type=int, default=32,
                   help="ancho del hidden state del LSTM (B4.14)")
    p.add_argument("--lstm-layers", type=int, default=1,
                   help="capas apiladas del LSTM (B4.14)")
    p.add_argument("--lstm-dropout", type=float, default=0.0,
                   help="dropout entre capas del LSTM, sólo activo con --lstm-layers > 1")
    p.add_argument("--snapshot", default=None)
    p.add_argument("--legacy", action="store_true",
                   help="permitir un snapshot previo a las Decisiones 039/040 "
                        "(sólo para comparar contra los resultados viejos)")
    p.add_argument("--gate-rain", default="auto",
                   help="columna de lluvia del modulador: auto | lluvia_merge_alta_frontera_mm "
                        "| lluvia_media_est_mm")
    p.add_argument("--groups", default=None,
                   help="grupos de features separados por coma; por defecto "
                        + ",".join(data_mod.DEFAULT_GROUPS))
    p.add_argument("--out", default=None, help="ruta del JSON de resultados")
    p.add_argument("--split", choices=["val", "test"], default=None,
                   help="split a reportar en la tabla (default: test, o val con --no-test)")
    p.add_argument("--no-test", action="store_true",
                   help="no calcular TEST. Lo pide el protocolo de búsqueda: TEST se mira "
                        "una sola vez, sobre la configuración campeona. Sin el bloque en el "
                        "JSON, la regla no depende de la disciplina de quien lo lee")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    _utf8_console()

    if args.no_test and args.split == "test":
        p.error("--split test es incompatible con --no-test: no se puede reportar "
                "un split que no se calculó")
    if args.split is None:
        args.split = "val" if args.no_test else "test"

    params = gate_mod.GateParams(tau_max=args.tau_max)
    print(f"cargando snapshot Gold ...", flush=True)
    groups = tuple(g.strip() for g in args.groups.split(",")) if args.groups else data_mod.DEFAULT_GROUPS
    ds = data_mod.build_dataset(target=args.target, tau_mode=args.tau_mode,
                                gate_params=params, snapshot_path=args.snapshot,
                                groups=groups, permitir_legacy=args.legacy,
                                gate_rain_col=args.gate_rain)
    if args.lookback:
        ds = data_mod.with_lookback(ds, args.lookback)
    splits = data_mod.make_splits(ds.fecha, train_start=args.train_start)
    print(f"  {len(ds)} días · {ds.X.shape[1]} features · τ modo {ds.tau_mode} "
          f"(τ_max = {params.tau_max})")
    for name, info in splits.describe(ds.fecha).items():
        print(f"  {name:5s} n={info['n']:5d}  {info['desde']} → {info['hasta']}")

    kw = dict(hidden=args.hidden, epochs=args.epochs, lr=args.lr, l2=args.l2,
              patience=args.patience, verbose=args.verbose,
              evaluar_test=not args.no_test,
              per_horizon=args.horizonte == "per_horizon",
              target_param=args.target_param,
              target_transform=args.target_transform,
              scaling=args.scaling,
              lookback=args.lookback,
              lstm_hidden=args.lstm_hidden, lstm_layers=args.lstm_layers,
              lstm_dropout=args.lstm_dropout)
    if args.tau_constante is not None:
        if not 0.0 < args.tau_constante < 1.0:
            p.error("--tau-constante debe estar en (0, 1)")
        kw["train_tau"] = np.full(len(ds), args.tau_constante)
    seeds = [args.seed + i for i in range(max(1, args.seeds))]
    if args.compare:
        results = run_comparison(ds, splits, model=args.model, seeds=seeds, **kw)
    else:
        results = {"dataset": {"n": len(ds), "tau_mode": ds.tau_mode},
                   "splits": splits.describe(ds.fecha), "seeds": seeds,
                   "baselines": run_baselines(ds, splits, evaluar_test=not args.no_test),
                   "models": {args.loss: run_experiment_seeds(
                       ds, splits, model=args.model, loss=args.loss, seeds=seeds, **kw)}}
    results["rankings"] = _rankings(results, args.split)
    results["gate_params"] = params.as_dict()
    # Qué versión del dato produjo estos números. Sin esto, un JSON de resultados
    # no se puede fechar contra las correcciones de Gold.
    manifest = data_mod.read_manifest(
        Path(args.snapshot) if args.snapshot else data_mod.DEFAULT_SNAPSHOT)
    results["snapshot"] = {
        "path": str(args.snapshot or data_mod.DEFAULT_SNAPSHOT),
        "delta_version": (manifest or {}).get("delta_version"),
        "exported_at": (manifest or {}).get("exported_at"),
        "sha256": ((manifest or {}).get("file_sha256") or "")[:12] or None,
        "gate_rain": args.gate_rain,
        "groups": list(groups),
    }
    # Lo que define el corte temporal y el criterio de corte del entrenamiento. Sin
    # esto, dos JSON con los mismos hiperparámetros pueden no ser comparables.
    results["run_config"] = {"train_start": args.train_start, "patience": args.patience,
                             "test_evaluado": not args.no_test,
                             "tau_constante": args.tau_constante,
                             "lookback": args.lookback,
                             "horizonte": args.horizonte,
                             "target_param": args.target_param,
                             "target_transform": args.target_transform}

    print_table(results, args.split)
    print(f"\n  ranking por RMSE : {' < '.join(results['rankings']['rmse'])}")
    print(f"  ranking por G-RAL: {' < '.join(results['rankings']['gral'])}")

    out_path = Path(args.out) if args.out else (
        data_mod.REPO_ROOT / "rio_search" / "results" /
        f"{args.model}_{'compare' if args.compare else args.loss}_{args.tau_mode}"
        f"{'_legacy' if args.legacy else ''}{'_grid' if args.groups and 'cptec' in args.groups else ''}"
        f"{('_lb%d' % args.lookback) if args.lookback else ''}"
        f"{'_ph' if args.horizonte == 'per_horizon' else ''}"
        f"{'_delta' if args.target_param == 'delta' else ''}"
        f"{('_' + args.target_transform) if args.target_transform else ''}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    try:                                     # --out puede apuntar fuera del repo
        mostrar = out_path.resolve().relative_to(data_mod.REPO_ROOT)
    except ValueError:
        mostrar = out_path.resolve()
    print(f"\n  resultados → {mostrar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
