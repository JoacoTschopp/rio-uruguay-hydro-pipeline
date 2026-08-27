"""Transformaciones experimentales como expresiones Polars (Decision #5,
docs/rio_search_plan.md §3.6): funciones puras con nombre y version que devuelven `pl.Expr`
(o una tupla de `pl.Expr` cuando el transform genera mas de una columna), aplicadas en un
solo `with_columns` despues de cargar Gold y antes de ajustar el escalador (§3.6,
"Preparacion dependiente del modelo").

Cada funcion documenta en su docstring como se promoveria a Gold (columna equivalente en
PySpark, §3.6): ese es el criterio para "graduar" un transform via notebook + Decision
(Fase 9) una vez que un experimento demuestra que aporta.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import polars as pl

from rio_search.domain.datasets.feature_transform import ExperimentalTransformSpec


def log1p(column: str, **_: Any) -> pl.Expr:
    """`log(1+x)` para columnas de caudal/lluvia con cola pesada (§2.1: distribuciones no
    estacionarias / con outliers grandes se comprimen antes de escalar).

    Promocion a Gold (PySpark): `F.log1p(F.col("<column>")).alias("<column>_log1p")`.
    """
    return pl.col(column).log1p().alias(f"{column}_log1p")


def doy_cyclic(date_column: str = "fecha", **_: Any) -> tuple[pl.Expr, pl.Expr]:
    """Dia del año como par seno/coseno (evita la discontinuidad 365 -> 1 de usar el entero
    crudo como feature).

    Promocion a Gold (PySpark):
    `F.sin(2*F.pi()*F.dayofyear("fecha")/365.25).alias("doy_sin")`,
    `F.cos(2*F.pi()*F.dayofyear("fecha")/365.25).alias("doy_cos")`.
    """
    angle = pl.col(date_column).dt.ordinal_day() * (2 * math.pi / 365.25)
    return angle.sin().alias("doy_sin"), angle.cos().alias("doy_cos")


def clip(column: str, max: float | None = None, min: float | None = None, **_: Any) -> pl.Expr:
    """Winsoriza una columna a `[min, max]` -- p. ej. el outlier de 823.897 m3/s del agregado
    de alta frontera (§2.1).

    Promocion a Gold (PySpark):
    `F.when(F.col("<column>") > max, F.lit(max)).when(F.col("<column>") < min, F.lit(min))
    .otherwise(F.col("<column>")).alias("<column>_clip")`.
    """
    if max is None and min is None:
        raise ValueError("clip requiere al menos uno de 'max'/'min'")
    expr = pl.col(column)
    if max is not None:
        expr = expr.clip(upper_bound=max)
    if min is not None:
        expr = expr.clip(lower_bound=min)
    return expr.alias(f"{column}_clip")


def ratio(numerator: str, denominator: str, **_: Any) -> pl.Expr:
    """Cociente `numerator / denominator` -- p. ej. `lluvia_acumulada_mm / station_count`
    para normalizar la suma no estacionaria sobre N estaciones variables (§2.1). Devuelve
    null en vez de dividir por cero.

    Promocion a Gold (PySpark):
    `F.when(F.col("<denominator>") != 0, F.col("<numerator>") / F.col("<denominator>"))
    .alias("<numerator>_ratio_<denominator>")`.
    """
    denom = pl.col(denominator)
    return (
        pl.when(denom != 0)
        .then(pl.col(numerator) / denom)
        .otherwise(None)
        .alias(f"{numerator}_ratio_{denominator}")
    )


def diff(column: str, periods: int = 1, **_: Any) -> pl.Expr:
    """Diferencia de `periods` dias (generaliza `*_delta_1d`, ya presente en Gold solo para
    N=1, a otras N experimentales).

    Promocion a Gold (PySpark):
    `F.col("<column>") - F.lag("<column>", periods).over(Window.orderBy("fecha"))`.
    """
    return (pl.col(column) - pl.col(column).shift(periods)).alias(f"{column}_diff_{periods}d")


def rolling(column: str, window: int = 7, stat: str = "mean", **_: Any) -> pl.Expr:
    """Estadistico movil (`mean`/`std`/`min`/`max`) de `window` dias sobre la serie ya
    ordenada por fecha (generaliza `*_media_3d`/`*_media_7d`, ya presentes en Gold, a otras
    ventanas/estadisticos experimentales).

    Promocion a Gold (PySpark): `F.avg("<column>").over(Window.orderBy("fecha")
    .rowsBetween(-window+1, 0))` (u otro agregado segun `stat`).
    """
    base = pl.col(column)
    stats: dict[str, Callable[[], pl.Expr]] = {
        "mean": lambda: base.rolling_mean(window_size=window, min_samples=1),
        "std": lambda: base.rolling_std(window_size=window, min_samples=1),
        "min": lambda: base.rolling_min(window_size=window, min_samples=1),
        "max": lambda: base.rolling_max(window_size=window, min_samples=1),
    }
    if stat not in stats:
        raise ValueError(f"stat desconocido para 'rolling': {stat!r}. Disponibles: {sorted(stats)}")
    return stats[stat]().alias(f"{column}_rolling_{stat}_{window}d")


TransformFn = Callable[..., "pl.Expr | tuple[pl.Expr, ...]"]

TRANSFORMS: dict[str, TransformFn] = {
    "log1p": log1p,
    "doy_cyclic": doy_cyclic,
    "clip": clip,
    "ratio": ratio,
    "diff": diff,
    "rolling": rolling,
}

# Transforms que no iteran sobre `spec.columns` (una sola invocacion con los params tal cual).
_COLUMN_LESS = {"doy_cyclic", "ratio"}


def build_expressions(spec: ExperimentalTransformSpec) -> list[pl.Expr]:
    """Construye la lista de `pl.Expr` para un `ExperimentalTransformSpec` del dominio: una
    expresion por columna declarada para los transforms que iteran columnas (`log1p`, `clip`,
    `diff`, `rolling`), o una unica invocacion con los params del YAML para los que no
    (`doy_cyclic`, `ratio`)."""
    fn = TRANSFORMS.get(spec.name)
    if fn is None:
        raise ValueError(
            f"Transform experimental desconocido: {spec.name!r}. Disponibles: {sorted(TRANSFORMS)}"
        )

    if spec.name in _COLUMN_LESS:
        result = fn(**spec.params)
        return list(result) if isinstance(result, tuple) else [result]

    if not spec.columns:
        raise ValueError(f"Transform {spec.name!r} requiere 'columns' en el YAML del experimento")
    return [fn(column=c, **spec.params) for c in spec.columns]
