"""Tests de `BuildFeatureMatrix` (Fase 1, docs/rio_search_plan.md §3.2, §3.6): seleccion de
columnas por grupo, transforms experimentales, imputacion y escalado -- todo ajustado **solo**
con TRAIN. Es el test central de "el escalador no ve VAL/TEST" sobre el pipeline completo."""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from rio_search.application.datasets.build_feature_matrix import BuildFeatureMatrix
from rio_search.application.datasets.build_split import BuildSplit
from rio_search.domain.datasets.feature_catalog import FeatureCatalog
from rio_search.domain.datasets.feature_transform import ExperimentalTransformSpec
from rio_search.domain.datasets.split_policy import SplitPolicy, TrainWindow

HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)


def _synthetic_df(n_days: int = 1200, start: date = date(2015, 1, 1)) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(n_days)]
    ramp = [float(i) for i in range(n_days)]
    data: dict[str, list] = {"fecha": dates, "caudal_actual_m3s": ramp, "caudal_lag_1d": ramp}
    for h in HORIZONS:
        data[f"caudal_t_mas_{h}d"] = [ramp[i + h] if i + h < n_days else None for i in range(n_days)]
    return pl.DataFrame(data)


def _catalog() -> FeatureCatalog:
    return FeatureCatalog.from_dict(
        {
            "groups": {
                "caudal_estado": {
                    "default_on": True,
                    "columns": ["caudal_actual_m3s", "caudal_lag_1d"],
                }
            }
        }
    )


def _split_dfs():
    df = _synthetic_df()
    policy = SplitPolicy(
        policy="rolling_365", embargo_days=14, train_window=TrainWindow(start=date(2015, 1, 1))
    )
    return BuildSplit().execute(df, policy, HORIZONS)


def test_feature_columns_come_from_requested_groups() -> None:
    result = BuildFeatureMatrix(_catalog()).execute(_split_dfs(), ["caudal_estado"])
    assert result.feature_columns == ("caudal_actual_m3s", "caudal_lag_1d")


def test_scaler_is_fit_only_on_train_partition() -> None:
    split_dfs = _split_dfs()
    result = BuildFeatureMatrix(_catalog()).execute(split_dfs, ["caudal_estado"], scaling_method="standard")

    expected_train_mean = split_dfs.train["caudal_actual_m3s"].mean()
    assert result.scaler_stats.center["caudal_actual_m3s"] == pytest.approx(expected_train_mean)

    # El dataset es una rampa continua: la media de TODO el dataframe es muy distinta de la
    # media de TRAIN (que es solo el primer tramo, valores bajos). Si el escalador hubiera
    # visto VAL/TEST, el centro se acercaria a la media global.
    full_mean = split_dfs.train.vstack(split_dfs.val).vstack(split_dfs.test)["caudal_actual_m3s"].mean()
    assert result.scaler_stats.center["caudal_actual_m3s"] != pytest.approx(full_mean, rel=0.05)


def test_scaled_train_has_zero_mean() -> None:
    result = BuildFeatureMatrix(_catalog()).execute(
        _split_dfs(), ["caudal_estado"], scaling_method="standard"
    )
    assert result.train["caudal_actual_m3s"].mean() == pytest.approx(0.0, abs=1e-6)


def test_imputer_is_fit_only_on_train_partition() -> None:
    split_dfs = _split_dfs()
    result = BuildFeatureMatrix(_catalog()).execute(split_dfs, ["caudal_estado"], scaling_method="none")
    expected_median = split_dfs.train["caudal_actual_m3s"].median()
    assert result.imputer_stats.medians["caudal_actual_m3s"] == pytest.approx(expected_median)


def test_imputation_reports_cover_all_three_splits() -> None:
    result = BuildFeatureMatrix(_catalog()).execute(_split_dfs(), ["caudal_estado"])
    names = {r.split for r in result.imputation_reports}
    assert names == {"train", "val", "test"}


def test_experimental_transform_adds_column_to_all_splits() -> None:
    spec = ExperimentalTransformSpec(name="log1p", version=1, columns=["caudal_actual_m3s"])
    result = BuildFeatureMatrix(_catalog()).execute(
        _split_dfs(), ["caudal_estado"], experimental_transforms=[spec]
    )
    assert "caudal_actual_m3s_log1p" in result.feature_columns
    assert "caudal_actual_m3s_log1p" in result.train.columns
    assert "caudal_actual_m3s_log1p" in result.val.columns
    assert "caudal_actual_m3s_log1p" in result.test.columns


def test_output_dataframes_keep_same_row_counts_as_split() -> None:
    split_dfs = _split_dfs()
    result = BuildFeatureMatrix(_catalog()).execute(split_dfs, ["caudal_estado"])
    assert result.train.height == split_dfs.train.height
    assert result.val.height == split_dfs.val.height
    assert result.test.height == split_dfs.test.height


def test_glob_pattern_in_transform_columns_expands_against_selected_features() -> None:
    """Decision 041: `"caudal_*"` no es un nombre de columna literal de Polars -- se expande
    contra las columnas ya seleccionadas de `features.groups` antes de construir expresiones."""
    spec = ExperimentalTransformSpec(name="log1p", version=1, columns=["caudal_*"])
    result = BuildFeatureMatrix(_catalog()).execute(
        _split_dfs(), ["caudal_estado"], experimental_transforms=[spec]
    )
    assert "caudal_actual_m3s_log1p" in result.feature_columns
    assert "caudal_lag_1d_log1p" in result.feature_columns
    # No debe alcanzar columnas de target (no seleccionadas via features.groups).
    assert "caudal_t_mas_1d_log1p" not in result.feature_columns


def test_glob_pattern_deduplicates_against_explicit_column_in_same_transform() -> None:
    """El YAML de ejemplo (§4.1) declara `["caudal_*", "caudal_agregado_alta_frontera_m3s"]` a
    proposito: si el glob ya matchea esa columna, expandir no debe aplicar el transform dos
    veces (Polars fallaria con `DuplicateError` al `with_columns` un alias repetido)."""
    spec = ExperimentalTransformSpec(name="log1p", version=1, columns=["caudal_*", "caudal_actual_m3s"])
    result = BuildFeatureMatrix(_catalog()).execute(
        _split_dfs(), ["caudal_estado"], experimental_transforms=[spec]
    )
    assert result.train.columns.count("caudal_actual_m3s_log1p") == 1


def test_exclude_drops_a_column_from_the_selected_group() -> None:
    """Decision 043: `features.exclude` (§4.1) descarta columnas casi constantes en TRAIN
    (p. ej. `caudal_registros_validos`) que un escalador `standard` convertiria en z-scores
    extremos y desestabilizarian el entrenamiento de un modelo torch."""
    result = BuildFeatureMatrix(_catalog()).execute(
        _split_dfs(), ["caudal_estado"], exclude=["caudal_lag_1d"]
    )
    assert result.feature_columns == ("caudal_actual_m3s",)
    # La columna excluida no se ajusta/escala como feature, pero sigue en el dataframe base
    # (BuildFeatureMatrix no elimina columnas del dataframe, solo del contrato de features).
    assert "caudal_lag_1d" not in result.imputer_stats.medians
    assert "caudal_lag_1d" not in result.scaler_stats.center


def test_glob_pattern_with_no_matches_raises() -> None:
    spec = ExperimentalTransformSpec(name="log1p", version=1, columns=["nivel_*"])
    with pytest.raises(ValueError, match="no matchea ninguna columna"):
        BuildFeatureMatrix(_catalog()).execute(
            _split_dfs(), ["caudal_estado"], experimental_transforms=[spec]
        )
