"""`BuildFeatureMatrix` (Fase 1, docs/rio_search_plan.md §3.2, §3.6): "Preparacion dependiente
del modelo" -- selecciona columnas de los grupos de features -> aplica transforms
experimentales -> imputa (ajustado solo con TRAIN) -> escala (ajustado solo con TRAIN).

Recibe un `SplitDataFrames` ya particionado por `BuildSplit`: el imputador y el escalador se
ajustan **una sola vez** sobre `split_dfs.train` y se reaplican tal cual sobre VAL/TEST -- es
la invariante que protege el contexto Datasets (§3.2: "El escalador se ajusta solo con TRAIN").
"""

from __future__ import annotations

from dataclasses import dataclass

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
    ) -> FeatureMatrices:
        specs = experimental_transforms or []
        base_columns = list(self._feature_catalog.columns_for(group_names))
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
