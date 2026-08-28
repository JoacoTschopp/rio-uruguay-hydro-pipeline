"""Tests offline de `RidgeAdapter` (Fase 9, docs/rio_search_plan.md §3.3, §5): segundo modelo
enchufable, mismo contrato `ModelAdapterPort` que `BiLSTMAdapter` (Fase 3) y los baselines naive
(Fase 2) -- arquitectura (aplanado de la ventana), ajuste con NaN reales enmascarados por
columna, prediccion, roundtrip de serializacion y ambas estrategias de horizonte. Todo con
tensores sinteticos, sin tocar Databricks/MLflow."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from rio_search.domain.experiments.horizon_strategy import HorizonStrategy
from rio_search.domain.experiments.training_spec import TrainingSpec
from rio_search.domain.models.model_family import ModelFamily
from rio_search.domain.models.model_spec import ModelSpec
from rio_search.domain.shared.device import Device
from rio_search.infrastructure.datasets.sequence_builder import Sequences
from rio_search.infrastructure.models.sklearn.ridge import RidgeAdapter

CPU = Device(type="cpu", name="test-cpu")
HORIZONS = (1, 2, 3, 4, 5, 6, 7, 14)


def _synthetic_sequences(n: int, lookback: int, n_features: int, seed: int = 0) -> Sequences:
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, lookback, n_features)).astype(np.float32)
    start = date(2015, 1, 1)
    anchor_dates = tuple(start + timedelta(days=i) for i in range(n))
    feature_columns = tuple(f"f{i}" for i in range(n_features))
    return Sequences(X=X, anchor_dates=anchor_dates, feature_columns=feature_columns)


def _synthetic_targets(seq: Sequences, n_outputs: int, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    # y correlaciona linealmente con la ultima fila de X (senial aprendible por una regresion
    # lineal, a diferencia de ruido puro) para que la loss de train efectivamente baje con
    # respecto a predecir la media.
    base = seq.X[:, -1, 0]
    noise = rng.normal(scale=0.05, size=(len(base), n_outputs)).astype(np.float32)
    return (base.reshape(-1, 1) + noise).astype(np.float64)


def _build_adapter(
    n_features: int, n_outputs: int, horizons: tuple[int, ...] = HORIZONS, alpha: float = 1.0
) -> RidgeAdapter:
    adapter = RidgeAdapter()
    spec = ModelSpec(
        name="ridge",
        horizon_strategy=HorizonStrategy.MULTI_OUTPUT,
        params={"alpha": alpha, "horizons": list(horizons)},
    )
    adapter.build(spec, n_features=n_features, n_outputs=n_outputs, device=CPU)
    return adapter


def _training() -> TrainingSpec:
    # Ridge no itera por epoch (fit() se resuelve en forma cerrada) -- TrainingSpec solo se pasa
    # por contrato comun (§4.1), no lo usa.
    return TrainingSpec(seed=42, device="cpu")


def test_build_registers_sklearn_family_and_both_horizon_strategies() -> None:
    adapter = RidgeAdapter()
    assert adapter.name == "ridge"
    assert adapter.family == ModelFamily.SKLEARN
    assert adapter.supports == {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}


def test_fit_requires_targets() -> None:
    train_seq = _synthetic_sequences(n=50, lookback=5, n_features=2, seed=0)
    val_seq = _synthetic_sequences(n=20, lookback=5, n_features=2, seed=1)
    adapter = _build_adapter(n_features=2, n_outputs=len(HORIZONS))
    with pytest.raises(ValueError, match="train_y/val_y"):
        adapter.fit(train_seq, val_seq, _training())


def test_fit_produces_single_shot_fit_result_with_finite_losses() -> None:
    train_seq = _synthetic_sequences(n=200, lookback=10, n_features=3, seed=0)
    val_seq = _synthetic_sequences(n=60, lookback=10, n_features=3, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS), seed=10)
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS), seed=11)

    adapter = _build_adapter(n_features=3, n_outputs=len(HORIZONS))
    result = adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)

    # Ridge se resuelve en forma cerrada, no itera epochs (Decision #13 no aplica) -- se
    # reporta como un unico "epoch" con una loss real (a diferencia de los baselines naive,
    # que reportan epochs=0 por no ajustar ningun parametro, Fase 2).
    assert result.epochs == 1
    assert result.best_epoch == 1
    assert len(result.train_losses) == 1
    assert len(result.val_losses) == 1
    assert np.isfinite(result.train_losses[0])
    assert np.isfinite(result.val_losses[0])
    assert result.train_to_best_epoch_s >= 0.0
    assert result.train_samples_per_s > 0.0


def test_predict_shape_matches_horizons() -> None:
    n_features = 2
    seq = _synthetic_sequences(n=30, lookback=6, n_features=n_features, seed=2)
    train_seq = _synthetic_sequences(n=80, lookback=6, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=6, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)
    predictions = adapter.predict(seq)

    assert predictions.y_pred.shape == (30, len(HORIZONS))
    assert predictions.horizons == HORIZONS
    assert predictions.anchor_dates == seq.anchor_dates


def test_fit_learns_a_real_linear_relationship_better_than_predicting_the_mean() -> None:
    n_features = 3
    train_seq = _synthetic_sequences(n=300, lookback=5, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=80, lookback=5, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=1, seed=10)
    val_y = _synthetic_targets(val_seq, n_outputs=1, seed=11)

    adapter = _build_adapter(n_features=n_features, n_outputs=1, horizons=(1,))
    adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)
    val_pred = adapter.predict(val_seq).y_pred

    mse_model = float(np.mean((val_pred - val_y) ** 2))
    mse_mean_baseline = float(np.mean((val_y - train_y.mean()) ** 2))
    assert mse_model < mse_mean_baseline


def test_save_and_load_roundtrip_reproduces_predictions(tmp_path: Path) -> None:
    n_features = 3
    train_seq = _synthetic_sequences(n=100, lookback=7, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=7, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)
    before = adapter.predict(val_seq).y_pred

    adapter.save(tmp_path / "model_state.json")
    assert (tmp_path / "ridge_models.pkl").exists()
    assert (tmp_path / "architecture.json").exists()

    loaded = RidgeAdapter.load(tmp_path / "model_state.json", device=CPU)
    after = loaded.predict(val_seq).y_pred

    np.testing.assert_allclose(before, after, rtol=1e-10, atol=1e-10)


def test_per_horizon_n_outputs_one_is_supported_by_the_same_adapter() -> None:
    """§3.3: "un adaptador que soporte n_outputs=1 ya soporta per_horizon gratis" -- vale tanto
    para BaseTorchAdapter (Fase 3) como para este adaptador (Fase 9)."""
    n_features = 2
    train_seq = _synthetic_sequences(n=80, lookback=5, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=5, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=1)
    val_y = _synthetic_targets(val_seq, n_outputs=1)

    adapter = _build_adapter(n_features=n_features, n_outputs=1, horizons=(3,))
    result = adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)
    predictions = adapter.predict(val_seq)

    assert result.epochs == 1
    assert predictions.y_pred.shape == (30, 1)
    assert predictions.horizons == (3,)


def test_fit_masks_nan_targets_per_column_and_does_not_crash() -> None:
    """Mismo problema real que Decision 043 (huecos de calendario en el target, §2.1), resuelto
    distinto que `BaseTorchAdapter` (que enmascara por batch): `Ridge.fit()` no acepta NaN en
    absoluto, asi que `RidgeAdapter` enmascara por fila antes de llamar a `.fit()` por columna
    de horizonte."""
    n_features = 3
    train_seq = _synthetic_sequences(n=150, lookback=8, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=50, lookback=8, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    rng = np.random.default_rng(7)
    train_y = train_y.copy()
    holes = rng.choice(len(train_y), size=int(0.15 * len(train_y)), replace=False)
    train_y[holes, :] = np.nan
    val_y = val_y.copy()
    val_y[0, 0] = np.nan
    val_y[1, 3] = np.nan

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    result = adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)

    assert np.isfinite(result.train_losses[0])
    assert np.isfinite(result.val_losses[0])

    predictions = adapter.predict(val_seq)
    assert not np.isnan(predictions.y_pred).any()


def test_fit_handles_a_horizon_column_with_no_valid_target_at_all() -> None:
    """Caso extremo de §2.1 (huecos de calendario): una columna de horizonte entera en NaN en
    TRAIN no debe romper el resto del trial (multi-output con los otros 7 horizontes)."""
    n_features = 2
    train_seq = _synthetic_sequences(n=60, lookback=5, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=20, lookback=5, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=2)
    val_y = _synthetic_targets(val_seq, n_outputs=2)
    train_y[:, 1] = np.nan

    adapter = _build_adapter(n_features=n_features, n_outputs=2, horizons=(1, 2))
    adapter.fit(train_seq, val_seq, _training(), train_y=train_y, val_y=val_y)
    predictions = adapter.predict(val_seq)

    assert predictions.y_pred.shape == (20, 2)
    assert np.isfinite(predictions.y_pred).all()
