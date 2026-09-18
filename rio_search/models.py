"""Modelos y funciones de pérdida, en NumPy puro.

La pieza que importa acá es que **la función de pérdida es un parámetro**, no
algo cableado en el modelo: el mismo `MLPCore` se entrena con error cuadrático o
con la pérdida expectil asimétrica cambiando un argumento. Esa es la condición
para poder responder la pregunta de la tesis — ¿entrenar con G-RAL cambia el
comportamiento del modelo en los regímenes que importan? — con todo lo demás
idéntico: mismos datos, mismos splits, misma semilla, misma arquitectura.

Todas las pérdidas son elemento a elemento sobre `e = y − ŷ` y exponen su
gradiente respecto de ŷ, que es lo que consume el optimizador.

No usa PyTorch a propósito: el arnés tiene que correr sin GPU ni instalación
extra. Cuando Rio_Search levante su entorno `uv` con torch (Fase 0 del plan),
`ExpectileLoss` se traduce a tres líneas de tensores y las métricas de
`rio_search.metrics` se importan tal cual.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["Loss", "SquaredLoss", "AbsoluteLoss", "ExpectileLoss", "HuberLoss",
           "NSELoss", "LOSSES",
           "LinearCore", "MLPCore", "XGBoostCore", "DLinearCore", "LSTMCore",
           "PersistenceBaseline", "ClimatologyBaseline", "DampedPersistence", "SeasonalNaive"]


# --------------------------------------------------------------------------
# Pérdidas
# --------------------------------------------------------------------------

class Loss:
    """Interfaz: `value` y `grad` elemento a elemento sobre `e = y − ŷ`."""

    name = "base"
    uses_tau = False

    def value(self, e: np.ndarray, tau: np.ndarray | None = None) -> np.ndarray:
        raise NotImplementedError

    def grad(self, e: np.ndarray, tau: np.ndarray | None = None) -> np.ndarray:
        """∂L/∂ŷ, no ∂L/∂e — de ahí los signos negativos."""
        raise NotImplementedError


class SquaredLoss(Loss):
    """Error cuadrático. Es `ExpectileLoss` con τ = 0,5, escrito aparte para
    que el camino por defecto no dependa del modulador."""

    name = "mse"

    def value(self, e, tau=None):
        return e ** 2

    def grad(self, e, tau=None):
        return -2.0 * e


class AbsoluteLoss(Loss):
    name = "mae"

    def value(self, e, tau=None):
        return np.abs(e)

    def grad(self, e, tau=None):
        return -np.sign(e)


class ExpectileLoss(Loss):
    """ψ_τ(e) = 2·|τ − 1{e<0}|·e².

    Con `e = observado − predicho`, τ > 0,5 castiga más la subestimación. El
    gradiente es continuo en e = 0 (tiende a 0 por los dos lados), a diferencia
    de la pérdida pinball: por eso esta familia sirve para entrenar y la otra no,
    sin trucos.
    """

    name = "expectile"
    uses_tau = True

    def _w(self, e, tau):
        if tau is None:
            raise ValueError("ExpectileLoss necesita tau")
        return np.where(e < 0.0, 1.0 - tau, tau)

    def value(self, e, tau=None):
        return 2.0 * self._w(e, tau) * e ** 2

    def grad(self, e, tau=None):
        return -4.0 * self._w(e, tau) * e


class HuberLoss(Loss):
    """Cuadrática hasta δ, lineal más allá — robusta a picos aislados y a
    errores de aforo sin volverse ciega al tamaño del error como MAE.

    Escrita para coincidir con `SquaredLoss` en la rama cuadrática (e², no
    ½e²): así los HP del ancla siguen significando lo mismo. δ = 1,345 es la
    constante clásica de Huber (95 % de eficiencia bajo normalidad), aplicada
    en el espacio estandarizado del target donde σ = 1 — se declara, no se
    ajusta por VAL.
    """

    name = "huber"

    def __init__(self, delta: float = 1.345):
        self.delta = float(delta)

    def value(self, e, tau=None):
        a = np.abs(e)
        return np.where(a <= self.delta, e ** 2, 2.0 * self.delta * a - self.delta ** 2)

    def grad(self, e, tau=None):
        return -2.0 * np.clip(e, -self.delta, self.delta)


class NSELoss(Loss):
    """1 − NSE como pérdida: MSE normalizado por la varianza del target de
    TRAIN, por horizonte (Kratzert et al. 2019). El gradiente es el de MSE
    reescalado por 1/σ²_h: entrenar con la métrica que la hidrología reporta.

    `var` se calibra por corrida en `run_experiment` (sale de TRAIN, nunca de
    VAL). Sin calibrar (`var=None`) el peso es 1 y coincide con el MSE del
    proyecto — neutro por diseño, para que el registro global no dependa de un
    estado que todavía no existe.
    """

    name = "nse"

    def __init__(self, var=None, eps: float = 1e-6):
        self.var = None if var is None else np.asarray(var, dtype=float)
        self.eps = float(eps)

    def _w(self):
        return 1.0 if self.var is None else 1.0 / (self.var + self.eps)

    def value(self, e, tau=None):
        return self._w() * e ** 2

    def grad(self, e, tau=None):
        return -2.0 * self._w() * e


LOSSES: dict[str, Loss] = {
    "mse": SquaredLoss(),
    "mae": AbsoluteLoss(),
    "expectile": ExpectileLoss(),
    "huber": HuberLoss(),
    "nse": NSELoss(),
}


# --------------------------------------------------------------------------
# Optimizador
# --------------------------------------------------------------------------

@dataclass
class Adam:
    lr: float = 0.01
    beta1: float = 0.9
    beta2: float = 0.999
    eps: float = 1e-8
    _m: dict = field(default_factory=dict, repr=False)
    _v: dict = field(default_factory=dict, repr=False)
    _t: int = field(default=0, repr=False)

    def step(self, params: dict[str, np.ndarray], grads: dict[str, np.ndarray]) -> None:
        self._t += 1
        for k, g in grads.items():
            if k not in self._m:
                self._m[k] = np.zeros_like(g)
                self._v[k] = np.zeros_like(g)
            self._m[k] = self.beta1 * self._m[k] + (1 - self.beta1) * g
            self._v[k] = self.beta2 * self._v[k] + (1 - self.beta2) * g ** 2
            m_hat = self._m[k] / (1 - self.beta1 ** self._t)
            v_hat = self._v[k] / (1 - self.beta2 ** self._t)
            params[k] -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)


# --------------------------------------------------------------------------
# Modelos entrenables
# --------------------------------------------------------------------------

class _GradientModel:
    """Base con el bucle de entrenamiento común (full-batch + early stopping)."""

    def __init__(self, *, loss: Loss, epochs: int = 600, lr: float = 0.01,
                 l2: float = 1e-4, patience: int = 60, seed: int = 20260828,
                 verbose: bool = False):
        self.loss = loss
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2
        self.patience = patience
        self.seed = seed
        self.verbose = verbose
        self.params: dict[str, np.ndarray] = {}
        self.history: list[dict] = []
        self.best_epoch: int | None = None
        self.pruned: bool = False

    # --- a implementar por cada arquitectura ---
    def _init_params(self, n_in: int, n_out: int, rng) -> dict:
        raise NotImplementedError

    def _forward(self, X, params):
        raise NotImplementedError

    def _backward(self, X, cache, G, params) -> dict:
        raise NotImplementedError

    def _weight_keys(self) -> tuple[str, ...]:
        raise NotImplementedError

    # --- común ---
    def _mean_loss(self, X, Y, tau, mask, params) -> float:
        yhat, _ = self._forward(X, params)
        e = np.where(mask, Y - yhat, 0.0)
        return float(np.sum(self.loss.value(e, tau) * mask) / max(mask.sum(), 1))

    def fit(self, X, Y, tau=None, *, mask=None,
            X_val=None, Y_val=None, tau_val=None, mask_val=None,
            on_epoch=None):
        """Entrena full-batch con early stopping sobre VAL.

        `mask` es booleana (n, n_horizontes): False donde el target no es
        observable — la cola de la serie no tiene target a 14 días, y hay días
        sueltos sin caudal. Esas celdas no aportan pérdida ni gradiente, en vez
        de descartar la fila entera y perder los horizontes que sí existen.

        `on_epoch(epoch, val_loss) -> bool` se llama al final de cada época y, si
        devuelve True, corta el entrenamiento. Es el enganche que usa el podado de
        Optuna: un trial que ya se ve peor que la mediana no necesita terminar.
        Devolver True corta igual que el early stopping, dejando los mejores pesos.
        """
        rng = np.random.default_rng(self.seed)
        n, n_in = X.shape
        n_out = Y.shape[1]
        self.params = self._init_params(n_in, n_out, rng)
        opt = Adam(lr=self.lr)

        if self.loss.uses_tau and tau is None:
            raise ValueError(f"la pérdida {self.loss.name!r} necesita tau")
        mask = np.isfinite(Y) if mask is None else (np.asarray(mask, bool) & np.isfinite(Y))
        Y = np.where(mask, Y, 0.0)
        n_valid = max(int(mask.sum()), 1)

        tau_b = None if tau is None else np.broadcast_to(
            np.asarray(tau, float).reshape(-1, 1), Y.shape)
        if X_val is not None:
            mask_val = np.isfinite(Y_val) if mask_val is None else (
                np.asarray(mask_val, bool) & np.isfinite(Y_val))
            Y_val = np.where(mask_val, Y_val, 0.0)
        tau_val_b = None if tau_val is None else np.broadcast_to(
            np.asarray(tau_val, float).reshape(-1, 1), Y_val.shape)

        best = np.inf
        best_params = {k: v.copy() for k, v in self.params.items()}
        stale = 0
        scale = 1.0 / n_valid

        for epoch in range(1, self.epochs + 1):
            yhat, cache = self._forward(X, self.params)
            e = np.where(mask, Y - yhat, 0.0)
            G = self.loss.grad(e, tau_b) * mask * scale
            grads = self._backward(X, cache, G, self.params)
            for k in self._weight_keys():
                grads[k] = grads[k] + self.l2 * self.params[k]
            opt.step(self.params, grads)

            train_loss = float(np.sum(self.loss.value(e, tau_b) * mask) / n_valid)
            row = {"epoch": epoch, "train_loss": train_loss}
            if X_val is not None:
                row["val_loss"] = self._mean_loss(X_val, Y_val, tau_val_b, mask_val, self.params)
                monitor = row["val_loss"]
            else:
                monitor = train_loss
            self.history.append(row)

            if monitor < best - 1e-9:
                best, stale = monitor, 0
                best_params = {k: v.copy() for k, v in self.params.items()}
                self.best_epoch = epoch
            else:
                stale += 1
                if stale >= self.patience:
                    break

            if on_epoch is not None and on_epoch(epoch, monitor):
                self.pruned = True
                break
            if self.verbose and epoch % 50 == 0:
                print(f"  epoch {epoch:4d}  {row}")

        self.params = best_params
        return self

    def predict(self, X) -> np.ndarray:
        yhat, _ = self._forward(X, self.params)
        return yhat


class LinearCore(_GradientModel):
    """Regresión lineal multi-salida con regularización L2, por gradiente.

    Se entrena por gradiente y no en forma cerrada justamente para que acepte
    cualquier pérdida, incluida la asimétrica.
    """

    name = "linear"

    def _init_params(self, n_in, n_out, rng):
        return {"W": np.zeros((n_in, n_out)), "b": np.zeros(n_out)}

    def _forward(self, X, params):
        return X @ params["W"] + params["b"], None

    def _backward(self, X, cache, G, params):
        return {"W": X.T @ G, "b": G.sum(axis=0)}

    def _weight_keys(self):
        return ("W",)


class MLPCore(_GradientModel):
    """Perceptrón multicapa con tanh; `hidden` es un ancho o una lista de anchos.

    B4.03: con `hidden=[38, 38]` la red tiene dos capas ocultas. Un entero
    reproduce **bit a bit** la red de una capa de siempre: los `dims` y el orden
    de los sorteos del rng son los mismos, así que el ancla no se mueve. Sin
    dropout ni residuales: con 2–4 capas y L2, el early stopping sobre VAL es la
    regularización que ya gobierna al resto del arnés (queda declarado en la
    celda, no escondido).
    """

    name = "mlp"

    def __init__(self, hidden: int | list[int] = 64, **kw):
        super().__init__(**kw)
        self.hidden = hidden
        self.widths = [hidden] if isinstance(hidden, int) else [int(w) for w in hidden]
        if not self.widths or any(w < 1 for w in self.widths):
            raise ValueError(f"anchos ocultos inválidos: {hidden!r}")

    def _init_params(self, n_in, n_out, rng):
        # Xavier: mantiene la varianza estable a través de la tanh
        dims = [n_in] + self.widths + [n_out]
        params = {}
        for i in range(len(dims) - 1):
            s = np.sqrt(1.0 / dims[i])
            params[f"W{i + 1}"] = rng.normal(0, s, size=(dims[i], dims[i + 1]))
            params[f"b{i + 1}"] = np.zeros(dims[i + 1])
        return params

    def _forward(self, X, params):
        hs, a = [], X
        for i in range(1, len(self.widths) + 1):
            a = np.tanh(a @ params[f"W{i}"] + params[f"b{i}"])
            hs.append(a)
        L = len(self.widths) + 1
        return a @ params[f"W{L}"] + params[f"b{L}"], hs

    def _backward(self, X, cache, G, params):
        hs = cache
        L = len(self.widths) + 1
        grads = {f"W{L}": hs[-1].T @ G, f"b{L}": G.sum(axis=0)}
        d = G @ params[f"W{L}"].T
        for i in range(len(self.widths), 0, -1):
            dz = d * (1.0 - hs[i - 1] ** 2)
            prev = X if i == 1 else hs[i - 2]
            grads[f"W{i}"] = prev.T @ dz
            grads[f"b{i}"] = dz.sum(axis=0)
            if i > 1:
                d = dz @ params[f"W{i}"].T
        return grads

    def _weight_keys(self):
        return tuple(f"W{i}" for i in range(1, len(self.widths) + 2))


class DLinearCore(_GradientModel):
    """DLinear (Zeng et al. 2023): descomposición tendencia+estacional de la
    ventana y una capa lineal por componente.

    B4.13, sobre las secuencias de B2.17. Consume el tensor que `with_lookback`
    ya aplana a (N, L·F); acá se reconstruye a (N, L, F) para descomponer a lo
    largo de L (media móvil por feature, kernel impar declarado — no tuneado),
    y se aplana de nuevo antes de las dos capas lineales (trend/seasonal), que
    se entrenan por gradiente como el resto del arnés — así acepta la misma
    pérdida asimétrica que todo lo demás, no sólo MSE. Sin torch: es lineal, y
    el resto del arnés corre en NumPy puro a propósito (ver módulo).
    """

    name = "dlinear"

    def __init__(self, lookback: int, n_features: int, kernel: int | None = None, **kw):
        super().__init__(**kw)
        if lookback < 1 or n_features < 1:
            raise ValueError(f"lookback y n_features deben ser >= 1: {lookback}, {n_features}")
        self.lookback = lookback
        self.n_features = n_features
        k = kernel or min(lookback, 25)
        self.kernel = k if k % 2 == 1 else k - 1        # impar, para padding simétrico
        if self.kernel < 1:
            raise ValueError(f"kernel inválido: {self.kernel}")

    def _moving_average(self, seq: np.ndarray) -> np.ndarray:
        """Media móvil causal-segura a lo largo de L (eje 1), padding por borde.

        No mira fuera de la ventana ya recortada por `make_sequences` —el
        padding repite el primer/último día de la ventana, no toma datos de
        afuera— así que no introduce fuga nueva.
        """
        k, pad = self.kernel, self.kernel // 2
        padded = np.pad(seq, ((0, 0), (pad, pad), (0, 0)), mode="edge")
        csum = np.cumsum(padded, axis=1)
        csum = np.concatenate([np.zeros((seq.shape[0], 1, seq.shape[2])), csum], axis=1)
        return (csum[:, k:, :] - csum[:, :-k, :]) / k

    def _decompose_flat(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        seq = X.reshape(X.shape[0], self.lookback, self.n_features)
        trend = self._moving_average(seq)
        seasonal = seq - trend
        n = X.shape[0]
        return trend.reshape(n, -1), seasonal.reshape(n, -1)

    def _init_params(self, n_in, n_out, rng):
        return {"Wt": np.zeros((n_in, n_out)), "Ws": np.zeros((n_in, n_out)),
                "b": np.zeros(n_out)}

    def _forward(self, X, params):
        trend_flat, seasonal_flat = self._decompose_flat(X)
        yhat = trend_flat @ params["Wt"] + seasonal_flat @ params["Ws"] + params["b"]
        return yhat, {"trend_flat": trend_flat, "seasonal_flat": seasonal_flat}

    def _backward(self, X, cache, G, params):
        return {"Wt": cache["trend_flat"].T @ G, "Ws": cache["seasonal_flat"].T @ G,
                "b": G.sum(axis=0)}

    def _weight_keys(self):
        return ("Wt", "Ws")

    def hp(self) -> dict:
        return {"lookback": self.lookback, "n_features": self.n_features,
                "kernel_media_movil": self.kernel}


class XGBoostCore:
    """Adaptador de XGBoost al mismo contrato que `MLPCore`/`LinearCore` (B4.08).

    Gradient boosting no comparte representación entre horizontes como el MLP:
    acá cada columna de salida entrena su propio booster, así que el multi-salida
    y el `per_horizon` externo de B5.02 dan exactamente lo mismo — esta clase no
    necesita saber cuál de los dos la está llamando.

    El objetivo es el custom que pide la celda: grad/hess **analíticos** de
    `ExpectileLoss`, no el objetivo cuadrático por defecto de XGBoost — así
    entrena de verdad con G-RAL, no con una aproximación. Con
    `e = y − ŷ` y `w = τ` (o `1−τ` si `e<0`): `L = 2·w·e²`,
    `∂L/∂ŷ = −4·w·e`, `∂²L/∂ŷ² = 4·w` (w se trata como localmente constante en
    el kink de e=0, el tratamiento de subgradiente habitual). El criterio de
    early stopping usa esa misma pérdida, vía `custom_metric`, para que la
    parada temprana monitoree lo mismo que el MLP monitorea con `_mean_loss` —
    no un RMSE simétrico que no ve la asimetría que se está entrenando.

    Los hiperparámetros de árbol (profundidad, submuestreo, `min_child_weight`)
    no tienen equivalente en el arnés genérico de `lr`/`l2`/`epochs`/`patience`
    que comparten MLP y lineal — quedan declarados acá con valores de literatura
    para tabular de este tamaño (~10⁴ filas), no tuneados por VAL. `hp()` los
    expone para que `run_experiment` los deje en el JSON de salida.
    """

    name = "xgb"

    def __init__(self, *, loss, epochs: int = 600, lr: float = 0.05, l2: float = 1.0,
                 patience: int = 30, seed: int = 20260828, verbose: bool = False,
                 max_depth: int = 4, subsample: float = 0.8,
                 colsample_bytree: float = 0.8, min_child_weight: float = 5.0):
        if not isinstance(loss, ExpectileLoss):
            raise NotImplementedError(
                "XGBoostCore sólo tiene objetivo custom para ExpectileLoss (lo que "
                f"pide B4.08); pérdida recibida = {loss.name!r}")
        self.loss = loss
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2
        self.patience = patience
        self.seed = seed
        self.verbose = verbose
        self.max_depth = max_depth
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.min_child_weight = min_child_weight
        self.boosters: list = []
        self.history: list = []
        self.best_epoch: int | list[int] | None = None
        self.pruned = False

    def hp(self) -> dict:
        return {"max_depth": self.max_depth, "eta": self.lr, "reg_lambda": self.l2,
                "subsample": self.subsample, "colsample_bytree": self.colsample_bytree,
                "min_child_weight": self.min_child_weight,
                "n_estimators_max": self.epochs, "early_stopping_rounds": self.patience}

    def _params(self):
        return {"max_depth": self.max_depth, "eta": self.lr, "lambda": self.l2,
                "subsample": self.subsample, "colsample_bytree": self.colsample_bytree,
                "min_child_weight": self.min_child_weight, "seed": self.seed,
                "tree_method": "hist", "verbosity": 0}

    def _custom_metric(self, dtr, tau_tr, dva=None, tau_va=None):
        def feval(preds, dmat):
            tau_col = tau_va if (dva is not None and dmat is dva) else tau_tr
            e = dmat.get_label() - preds
            w = np.where(e < 0.0, 1.0 - tau_col, tau_col)
            return "expectile", float(np.mean(2.0 * w * e ** 2))
        return feval

    @staticmethod
    def _objective(tau_col):
        def obj(preds, dmat):
            e = dmat.get_label() - preds
            w = np.where(e < 0.0, 1.0 - tau_col, tau_col)
            return -4.0 * w * e, 4.0 * w
        return obj

    def fit(self, X, Y, tau=None, *, mask=None, X_val=None, Y_val=None,
            tau_val=None, mask_val=None, on_epoch=None):
        if on_epoch is not None:
            raise NotImplementedError("XGBoostCore no soporta podado por época (on_epoch)")
        import xgboost as xgb

        Y = np.asarray(Y, dtype=float)
        n_out = Y.shape[1]
        tau = (np.asarray(tau, dtype=float) if tau is not None
              else np.full(Y.shape[0], 0.5))
        con_val = X_val is not None and Y_val is not None
        if con_val:
            Yv = np.asarray(Y_val, dtype=float)
            tau_val = (np.asarray(tau_val, dtype=float) if tau_val is not None
                      else np.full(Yv.shape[0], 0.5))

        self.boosters, self.history = [], []
        best_epochs = []
        for j in range(n_out):
            yj = Y[:, j]
            mj = np.isfinite(yj) if mask is None else (np.asarray(mask, bool)[:, j] & np.isfinite(yj))
            dtr = xgb.DMatrix(X[mj], label=yj[mj])
            tau_tr_j = tau[mj]

            dva, tau_va_j, watch = None, None, [(dtr, "train")]
            if con_val:
                yvj = Yv[:, j]
                mvj = (np.isfinite(yvj) if mask_val is None
                      else (np.asarray(mask_val, bool)[:, j] & np.isfinite(yvj)))
                dva = xgb.DMatrix(X_val[mvj], label=yvj[mvj])
                tau_va_j = tau_val[mvj]
                watch.append((dva, "val"))

            evals_result: dict = {}
            booster = xgb.train(
                self._params(), dtr, num_boost_round=self.epochs,
                obj=self._objective(tau_tr_j),
                custom_metric=self._custom_metric(dtr, tau_tr_j, dva, tau_va_j),
                evals=watch, evals_result=evals_result,
                early_stopping_rounds=self.patience if dva is not None else None,
                verbose_eval=self.verbose)

            self.boosters.append(booster)
            best_it = getattr(booster, "best_iteration", None)
            best_epochs.append(int(best_it) + 1 if best_it is not None
                               else booster.num_boosted_rounds())
            self.history.append(evals_result)

        self.best_epoch = best_epochs[0] if n_out == 1 else best_epochs
        return self

    def predict(self, X) -> np.ndarray:
        import xgboost as xgb
        d = xgb.DMatrix(X)
        cols = [b.predict(d, iteration_range=(0, b.best_iteration + 1))
               if hasattr(b, "best_iteration") else b.predict(d)
               for b in self.boosters]
        return np.column_stack(cols)


def _expectile_loss_torch(yhat, y, tau, mask):
    """La misma pérdida expectil que `ExpectileLoss`, en torch — compartida por
    `LSTMCore` y `TCNCore` para que no puedan divergir en dos copias."""
    import torch
    e = torch.where(mask, y - yhat, torch.zeros_like(y))
    w = torch.where(e < 0.0, 1.0 - tau, tau)
    denom = mask.sum().clamp(min=1)
    return (2.0 * w * e ** 2 * mask).sum() / denom


class LSTMCore:
    """Adaptador de torch a un LSTM, mismo contrato que `MLPCore`/`XGBoostCore` (B4.14).

    Kratzert et al. 2018/2019: el LSTM es el estado del arte en rainfall-runoff y
    la referencia contra la que la tesis se mide. Consume el tensor aplanado
    `(N, L·F)` que `with_lookback` ya arma para B2.17 y lo reconstruye a
    `(N, L, F)` — mismo patrón de reconstrucción que `DLinearCore`, mismo L que
    esa celda usó (declarado, no tuneado acá).

    No hereda de `_GradientModel`: ese backprop a mano tiene sentido para MLP
    tanh/lineal, no para una recurrencia — acá se entrena con autograd de torch,
    mismo bucle de Adam + early stopping que el resto del arnés (mismo criterio
    de parada, mismos pesos "mejores" restaurados al final).

    Sólo entrena con `ExpectileLoss` (igual que `XGBoostCore` y por la misma
    razón: es la pérdida asimétrica que el catálogo pide entrenar acá — gral o
    expectile_raw —, no una aproximación cuadrática). `bidirectional` es el
    parámetro que B4.15 (BiLSTM) necesita reusando esta misma clase: "igual que
    B4.14" según su propia spec en la matriz.
    """

    name = "lstm"

    def __init__(self, *, loss, lookback: int, n_features: int,
                 hidden_size: int = 32, num_layers: int = 1, dropout: float = 0.0,
                 bidirectional: bool = False, epochs: int = 600, lr: float = 0.01,
                 l2: float = 1e-4, patience: int = 60, seed: int = 20260828,
                 verbose: bool = False):
        if not isinstance(loss, ExpectileLoss):
            raise NotImplementedError(
                "LSTMCore sólo tiene entrenamiento para ExpectileLoss (gral / "
                f"expectile_raw); pérdida recibida = {loss.name!r}")
        if lookback < 1 or n_features < 1:
            raise ValueError(f"lookback y n_features deben ser >= 1: {lookback}, {n_features}")
        self.loss = loss
        self.lookback = lookback
        self.n_features = n_features
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.bidirectional = bidirectional
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2
        self.patience = patience
        self.seed = seed
        self.verbose = verbose
        self.history: list[dict] = []
        self.best_epoch: int | None = None
        self.pruned = False
        self.device = None
        self._net = None

    def hp(self) -> dict:
        return {"hidden_size": self.hidden_size, "num_layers": self.num_layers,
                "dropout": self.dropout, "bidirectional": self.bidirectional,
                "lookback": self.lookback, "n_features": self.n_features,
                "device": str(self.device)}

    def _build_net(self, n_out: int):
        import torch.nn as nn

        class _Net(nn.Module):
            def __init__(self, n_in, hidden, layers, out, dropout, bidir):
                super().__init__()
                self.rnn = nn.LSTM(n_in, hidden, num_layers=layers, batch_first=True,
                                   dropout=dropout if layers > 1 else 0.0,
                                   bidirectional=bidir)
                self.head = nn.Linear(hidden * (2 if bidir else 1), out)

            def forward(self, x):
                seq, _ = self.rnn(x)
                return self.head(seq[:, -1, :])          # último paso = el día t

        return _Net(self.n_features, self.hidden_size, self.num_layers, n_out,
                   self.dropout, self.bidirectional)

    _expectile = staticmethod(_expectile_loss_torch)

    def _to_seq(self, X):
        n = X.shape[0]
        return np.asarray(X, dtype=np.float32).reshape(n, self.lookback, self.n_features)

    def fit(self, X, Y, tau=None, *, mask=None, X_val=None, Y_val=None,
            tau_val=None, mask_val=None, on_epoch=None):
        import torch

        if on_epoch is not None:
            raise NotImplementedError("LSTMCore no soporta podado por época (on_epoch)")
        if tau is None:
            raise ValueError("LSTMCore necesita tau: sólo entrena con ExpectileLoss")
        torch.manual_seed(self.seed)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        def prep(Xs, Ys, m, t):
            Y_ = np.asarray(Ys, dtype=np.float32)
            m_ = np.isfinite(Y_) if m is None else (np.asarray(m, bool) & np.isfinite(Y_))
            Yz = np.where(m_, Y_, 0.0)
            t_ = np.broadcast_to(np.asarray(t, np.float32).reshape(-1, 1), Yz.shape)
            return (torch.tensor(self._to_seq(Xs), device=self.device),
                    torch.tensor(Yz, device=self.device),
                    torch.tensor(m_, device=self.device),
                    torch.tensor(t_, device=self.device))

        Xtr_t, Ytr_t, Mtr_t, Taut_t = prep(X, Y, mask, tau)
        con_val = X_val is not None and Y_val is not None
        if con_val:
            Xva_t, Yva_t, Mva_t, Tauva_t = prep(X_val, Y_val, mask_val, tau_val)

        net = self._build_net(Y.shape[1]).to(self.device)
        opt = torch.optim.Adam(net.parameters(), lr=self.lr, weight_decay=self.l2)

        best = float("inf")
        best_state = None
        stale = 0
        self.history = []

        for epoch in range(1, self.epochs + 1):
            net.train()
            opt.zero_grad()
            loss_val = self._expectile(net(Xtr_t), Ytr_t, Taut_t, Mtr_t)
            loss_val.backward()
            opt.step()

            row = {"epoch": epoch, "train_loss": float(loss_val.detach().cpu())}
            if con_val:
                net.eval()
                with torch.no_grad():
                    monitor = float(self._expectile(net(Xva_t), Yva_t, Tauva_t, Mva_t)
                                    .detach().cpu())
                row["val_loss"] = monitor
            else:
                monitor = row["train_loss"]
            self.history.append(row)

            if monitor < best - 1e-9:
                best, stale = monitor, 0
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
                self.best_epoch = epoch
            else:
                stale += 1
                if stale >= self.patience:
                    break
            if self.verbose and epoch % 50 == 0:
                print(f"  epoch {epoch:4d}  {row}")

        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        self._net = net
        return self

    def predict(self, X) -> np.ndarray:
        import torch
        with torch.no_grad():
            Xt = torch.tensor(self._to_seq(X), device=self.device)
            yhat = self._net(Xt).detach().cpu().numpy()
        return yhat.astype(np.float64)


class TCNCore:
    """Adaptador de torch a una TCN (Bai, Kolter & Koltun 2018), mismo contrato
    que `LSTMCore`/`DLinearCore` (B4.18).

    La causalidad acá es **estructural**, no una convención de entrenamiento
    (a diferencia del LSTM, que es causal porque nadie le da a leer el futuro,
    no porque la arquitectura lo impida): cada bloque aplica `nn.functional.pad`
    únicamente del lado izquierdo, `(kernel_size - 1) · dilatación` ceros, antes
    de una `nn.Conv1d` sin padding propio — la salida en el paso t queda, por
    construcción del tensor, en función sólo de entradas en pasos <= t. No hay
    padding del lado derecho que después haya que recortar (el `Chomp1d` del
    paper original), así que no hay nada que se pueda desalinear.

    Dilatación creciente por bloque (1, 2, 4, ...) para un campo receptivo
    largo con pocos parámetros; conexión residual por bloque (proyección 1×1
    si cambian los canales), como en el paper. Reconstruye `(N, L, F)` desde
    el tensor aplanado de `with_lookback`, igual que `LSTMCore`, y comparte con
    esa clase la misma pérdida expectil en torch (`_expectile_loss_torch`) y el
    mismo bucle de Adam + early stopping — se repite acá en vez de heredar
    porque no hay una base torch común todavía y esfuerzo declarado es medio,
    no una refactorización del arnés.
    """

    name = "tcn"

    def __init__(self, *, loss, lookback: int, n_features: int,
                 channels: int = 32, n_blocks: int = 4, kernel_size: int = 3,
                 dropout: float = 0.0, epochs: int = 600, lr: float = 0.01,
                 l2: float = 1e-4, patience: int = 60, seed: int = 20260828,
                 verbose: bool = False):
        if not isinstance(loss, ExpectileLoss):
            raise NotImplementedError(
                "TCNCore sólo tiene entrenamiento para ExpectileLoss (gral / "
                f"expectile_raw); pérdida recibida = {loss.name!r}")
        if lookback < 1 or n_features < 1:
            raise ValueError(f"lookback y n_features deben ser >= 1: {lookback}, {n_features}")
        if kernel_size < 2:
            raise ValueError(f"kernel_size debe ser >= 2: {kernel_size}")
        self.loss = loss
        self.lookback = lookback
        self.n_features = n_features
        self.channels = channels
        self.n_blocks = n_blocks
        self.kernel_size = kernel_size
        self.dropout = dropout
        self.epochs = epochs
        self.lr = lr
        self.l2 = l2
        self.patience = patience
        self.seed = seed
        self.verbose = verbose
        self.history: list[dict] = []
        self.best_epoch: int | None = None
        self.pruned = False
        self.device = None
        self._net = None

    def hp(self) -> dict:
        campo_receptivo = 1 + 2 * (self.kernel_size - 1) * (2 ** self.n_blocks - 1)
        return {"channels": self.channels, "n_blocks": self.n_blocks,
                "kernel_size": self.kernel_size, "dropout": self.dropout,
                "campo_receptivo": campo_receptivo, "lookback": self.lookback,
                "n_features": self.n_features, "device": str(self.device)}

    def _build_net(self, n_out: int):
        import torch.nn as nn
        import torch.nn.functional as tf

        class _BloqueCausal(nn.Module):
            def __init__(self, in_ch, out_ch, kernel_size, dilation, dropout):
                super().__init__()
                self.pad = (kernel_size - 1) * dilation
                self.conv1 = nn.Conv1d(in_ch, out_ch, kernel_size, dilation=dilation)
                self.conv2 = nn.Conv1d(out_ch, out_ch, kernel_size, dilation=dilation)
                self.relu = nn.ReLU()
                self.drop = nn.Dropout(dropout)
                self.ajuste = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else None

            def _causal(self, conv, x):
                return conv(tf.pad(x, (self.pad, 0)))   # sólo a la izquierda

            def forward(self, x):
                out = self.drop(self.relu(self._causal(self.conv1, x)))
                out = self.drop(self.relu(self._causal(self.conv2, out)))
                res = x if self.ajuste is None else self.ajuste(x)
                return self.relu(out + res)

        class _Net(nn.Module):
            def __init__(self, n_in, channels, n_blocks, kernel_size, dropout, n_out):
                super().__init__()
                bloques, in_ch = [], n_in
                for i in range(n_blocks):
                    bloques.append(_BloqueCausal(in_ch, channels, kernel_size, 2 ** i, dropout))
                    in_ch = channels
                self.bloques = nn.Sequential(*bloques)
                self.head = nn.Linear(channels, n_out)

            def forward(self, x):
                x = x.transpose(1, 2)              # (N, L, F) -> (N, F, L)
                out = self.bloques(x)               # (N, channels, L)
                return self.head(out[:, :, -1])     # último paso = el día t

        return _Net(self.n_features, self.channels, self.n_blocks, self.kernel_size,
                   self.dropout, n_out)

    def _to_seq(self, X):
        n = X.shape[0]
        return np.asarray(X, dtype=np.float32).reshape(n, self.lookback, self.n_features)

    def fit(self, X, Y, tau=None, *, mask=None, X_val=None, Y_val=None,
            tau_val=None, mask_val=None, on_epoch=None):
        import torch

        if on_epoch is not None:
            raise NotImplementedError("TCNCore no soporta podado por época (on_epoch)")
        if tau is None:
            raise ValueError("TCNCore necesita tau: sólo entrena con ExpectileLoss")
        torch.manual_seed(self.seed)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        def prep(Xs, Ys, m, t):
            Y_ = np.asarray(Ys, dtype=np.float32)
            m_ = np.isfinite(Y_) if m is None else (np.asarray(m, bool) & np.isfinite(Y_))
            Yz = np.where(m_, Y_, 0.0)
            t_ = np.broadcast_to(np.asarray(t, np.float32).reshape(-1, 1), Yz.shape)
            return (torch.tensor(self._to_seq(Xs), device=self.device),
                    torch.tensor(Yz, device=self.device),
                    torch.tensor(m_, device=self.device),
                    torch.tensor(t_, device=self.device))

        Xtr_t, Ytr_t, Mtr_t, Taut_t = prep(X, Y, mask, tau)
        con_val = X_val is not None and Y_val is not None
        if con_val:
            Xva_t, Yva_t, Mva_t, Tauva_t = prep(X_val, Y_val, mask_val, tau_val)

        net = self._build_net(Y.shape[1]).to(self.device)
        opt = torch.optim.Adam(net.parameters(), lr=self.lr, weight_decay=self.l2)

        best = float("inf")
        best_state = None
        stale = 0
        self.history = []

        for epoch in range(1, self.epochs + 1):
            net.train()
            opt.zero_grad()
            loss_val = _expectile_loss_torch(net(Xtr_t), Ytr_t, Taut_t, Mtr_t)
            loss_val.backward()
            opt.step()

            row = {"epoch": epoch, "train_loss": float(loss_val.detach().cpu())}
            if con_val:
                net.eval()
                with torch.no_grad():
                    monitor = float(_expectile_loss_torch(net(Xva_t), Yva_t, Tauva_t, Mva_t)
                                    .detach().cpu())
                row["val_loss"] = monitor
            else:
                monitor = row["train_loss"]
            self.history.append(row)

            if monitor < best - 1e-9:
                best, stale = monitor, 0
                best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
                self.best_epoch = epoch
            else:
                stale += 1
                if stale >= self.patience:
                    break
            if self.verbose and epoch % 50 == 0:
                print(f"  epoch {epoch:4d}  {row}")

        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        self._net = net
        return self

    def predict(self, X) -> np.ndarray:
        import torch
        with torch.no_grad():
            Xt = torch.tensor(self._to_seq(X), device=self.device)
            yhat = self._net(Xt).detach().cpu().numpy()
        return yhat.astype(np.float64)


# --------------------------------------------------------------------------
# Baselines (no se entrenan; son la referencia del skill score)
# --------------------------------------------------------------------------

class PersistenceBaseline:
    """ŷ(t+h) = Q(t) para todo h. La referencia estándar en hidrología."""

    name = "persistencia"

    def predict(self, q_actual, n_horizons: int) -> np.ndarray:
        return np.repeat(np.asarray(q_actual, float).reshape(-1, 1), n_horizons, axis=1)


class DampedPersistence:
    """ŷ(t+h) = Q(t) · factor. Sirve para exhibir el sesgo que RMSE no ve."""

    def __init__(self, factor: float = 0.9):
        self.factor = factor
        self.name = f"persistencia x {factor:g}"

    def predict(self, q_actual, n_horizons: int) -> np.ndarray:
        return self.factor * np.repeat(
            np.asarray(q_actual, float).reshape(-1, 1), n_horizons, axis=1)


class ClimatologyBaseline:
    """ŷ(t+h) = media móvil de los últimos `window` días de caudal observado."""

    def __init__(self, window: int = 30):
        self.window = window
        self.name = f"climatología {window} d"

    def predict(self, q_series, n_horizons: int) -> np.ndarray:
        import pandas as pd
        m = pd.Series(np.asarray(q_series, float)).rolling(
            self.window, min_periods=max(1, int(0.7 * self.window))).mean().to_numpy()
        return np.repeat(m.reshape(-1, 1), n_horizons, axis=1)


class SeasonalNaive:
    """ŷ(t+h) = media histórica del caudal en el mismo día del año que t+h.

    Se ajusta con TRAIN únicamente: para cada día del año, la media del caudal en
    una ventana circular de ±window días sobre los años de TRAIN. Es el único
    baseline que captura el ciclo anual sin mirar el estado actual del río:
    separa "el modelo aprendió la estacionalidad" de "aprendió la persistencia".
    """

    def __init__(self, window: int = 7):
        self.window = window
        self.name = f"estacional doy ±{window}d"
        self._por_doy: np.ndarray | None = None       # (366,) media circular
        self._global = float("nan")

    def fit(self, fecha, q_series) -> "SeasonalNaive":
        import pandas as pd
        fecha = pd.DatetimeIndex(fecha)
        q = np.asarray(q_series, dtype=float)
        ok = np.isfinite(q)
        doy = fecha.dayofyear.to_numpy()[ok]
        q = q[ok]
        suma = np.bincount(doy - 1, weights=q, minlength=366)
        cnt = np.bincount(doy - 1, minlength=366).astype(float)
        k = self.window
        idx = (np.arange(366)[:, None] + np.arange(-k, k + 1)[None, :]) % 366
        with np.errstate(invalid="ignore"):
            media = suma[idx].sum(axis=1) / cnt[idx].sum(axis=1)
        self._global = float(q.mean()) if q.size else float("nan")
        self._por_doy = np.where(np.isfinite(media), media, self._global)
        return self

    def predict(self, fecha, horizons) -> np.ndarray:
        """`(n, n_horizontes)`: la media del doy de **t+h**, no la del doy de t."""
        import pandas as pd
        if self._por_doy is None:
            raise RuntimeError("SeasonalNaive.predict antes de fit")
        fecha = pd.DatetimeIndex(fecha)
        out = np.empty((len(fecha), len(horizons)), dtype=float)
        for j, h in enumerate(horizons):
            doy = (fecha + pd.Timedelta(days=int(h))).dayofyear.to_numpy()
            out[:, j] = self._por_doy[doy - 1]
        return out
