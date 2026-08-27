"""`BuildFeatureMatrix` (Fase 1, docs/rio_search_plan.md §3.2, §3.6): "Preparacion dependiente
del modelo" -- selecciona columnas de los grupos de features -> aplica transforms
experimentales -> imputa (ajustado solo con TRAIN) -> escala (ajustado solo con TRAIN).

Recibe un `SplitDataFrames` ya particionado por `BuildSplit`: el imputador y el escalador se
ajustan **una sola vez** sobre `split_dfs.train` y se reaplican tal cual sobre VAL/TEST -- es
la invariante que protege el contexto Datasets (§3.2: "El escalador se ajusta solo con TRAIN").

Decision 041 (docs/decisions.md): `transforms.build_expressions` no resuelve globs (columnas
como `"caudal_*"` en el YAML de ejemplo, §4.1) -- `pl.col("caudal_*")` no es un glob para
Polars, es un nombre de columna literal que no existe, y `build_expressions` fallaria con
`ColumnNotFoundError`. Este modulo resuelve el glob **antes** de llamar a `build_expressions`,
expandiendolo contra `base_columns` (las columnas ya seleccionadas de `features.groups`, no
contra *todas* las columnas del dataset): asi un patron como `"caudal_*"` nunca alcanza
columnas de target (`caudal_t_mas_7d`) ni de metadata, solo features que el experimento ya
pidio explicitamente via sus grupos.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, replace

import polars as pl

from rio_search.application.datasets.build_split import SplitDataFrames
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.datasets.feature_transform import ExperimentalTransformSpec
from rio_search.infrastructure.preprocess import transforms as transform_fns
from rio_search.infrastructure.preprocess.imputers import (
    ImputationReport,
    ImputerStats,
    apply_imputer,
    fit_imputer,
)
from rio_search.infrastructure.preprocess.scalers import ScalerStats, ScalingMethod, apply_scaler, fit_scaler


@dataclass(frozen=True, slots=True)
class FeatureMatrices:
    train: pl.DataFrame
    val: pl.DataFrame
    test: pl.DataFrame
    feature_columns: tuple[str, ...]
    imputer_stats: ImputerStats
    scaler_stats: ScalerStats
    imputation_reports: tuple[ImputationReport, ImputationReport, ImputationReport]


class BuildFeatureMatrix:
    def __init__(self, feature_catalog: FeatureCatalog) -> None:
        self._feature_catalog = feature_catalog

    def execute(
        self,
        split_dfs: SplitDataFrames,
        group_names: list[str],
        experimental_transforms: list[ExperimentalTransformSpec] | None = None,
        imputation_max_ffill_days: int = 3,
        scaling_method: ScalingMethod = "standard",
        exclude: list[str] | None = None,
    ) -> FeatureMatrices:
        """`exclude` (§4.1, bloque `features:`): columnas de los grupos seleccionados que se
        descartan igual (p. ej. `caudal_registros_validos` -- casi constante en TRAIN, `std`
        ~0.013: un escalador `standard` la convierte en z-scores extremos (~-77) que
        desestabilizan el entrenamiento de un modelo torch, Decision 043). Se filtra **antes**
        de expandir globs de `experimental_transforms` para que un patron como `"caudal_*"`
        tampoco alcance las columnas excluidas."""
        base_columns = [c for c in self._feature_catalog.columns_for(group_names) if c not in (exclude or [])]
        specs = _expand_glob_columns(experimental_transforms or [], base_columns)
        transform_columns = _transform_output_columns(specs)
        feature_columns = base_columns + [c for c in transform_columns if c not in base_columns]

        train = _with_transforms(split_dfs.train, specs)
        val = _with_transforms(split_dfs.val, specs)
        test = _with_transforms(split_dfs.test, specs)

        imputer_stats = fit_imputer(train, feature_columns, max_ffill_days=imputation_max_ffill_days)
        train, train_report = apply_imputer(train, feature_columns, imputer_stats, split="train")
        val, val_report = apply_imputer(val, feature_columns, imputer_stats, split="val")
        test, test_report = apply_imputer(test, feature_columns, imputer_stats, split="test")

        scaler_stats = fit_scaler(train, feature_columns, scaling_method)
        train = apply_scaler(train, feature_columns, scaler_stats)
        val = apply_scaler(val, feature_columns, scaler_stats)
        test = apply_scaler(test, feature_columns, scaler_stats)

        return FeatureMatrices(
            train=train,
            val=val,
            test=test,
            feature_columns=tuple(feature_columns),
            imputer_stats=imputer_stats,
            scaler_stats=scaler_stats,
            imputation_reports=(train_report, val_report, test_report),
        )


def _expand_glob_columns(
    specs: list[ExperimentalTransformSpec], available_columns: list[str]
) -> list[ExperimentalTransformSpec]:
    """Resuelve patrones glob (`"caudal_*"`) en `spec.columns` contra `available_columns`
    (Decision 041). Columnas sin `*`/`?` se dejan tal cual (no se valida que existan aca --
    eso lo hace Polars/`build_expressions` al aplicarlas, igual que antes). Dedup preservando
    orden: el YAML de ejemplo (§4.1) declara `["caudal_*", "caudal_agregado_alta_frontera_m3s"]`
    a proposito -- la segunda columna ya matchea el glob, expandir no debe duplicarla."""
    expanded: list[ExperimentalTransformSpec] = []
    for spec in specs:
        if not spec.columns:
            expanded.append(spec)
            continue
        resolved: list[str] = []
        for pattern in spec.columns:
            if "*" in pattern or "?" in pattern:
                matches = [c for c in available_columns if fnmatch.fnmatch(c, pattern)]
                if not matches:
                    raise ValueError(
                        f"Transform {spec.name!r}: el patron {pattern!r} no matchea ninguna "
                        f"columna de features.groups seleccionados ({available_columns})"
                    )
                resolved.extend(matches)
            else:
                resolved.append(pattern)
        seen: set[str] = set()
        deduped = [c for c in resolved if not (c in seen or seen.add(c))]
        expanded.append(replace(spec, columns=tuple(deduped)))
    return expanded


def _with_transforms(df: pl.DataFrame, specs: list[ExperimentalTransformSpec]) -> pl.DataFrame:
    if not specs:
        return df
    exprs: list[pl.Expr] = []
    for spec in specs:
        exprs.extend(transform_fns.build_expressions(spec))
    return df.with_columns(exprs)


def _transform_output_columns(specs: list[ExperimentalTransformSpec]) -> list[str]:
    names: list[str] = []
    for spec in specs:
        for expr in transform_fns.build_expressions(spec):
            names.append(expr.meta.output_name())
    return names
