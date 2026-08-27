"""Tests offline de `BaseTorchAdapter`/`BiLSTMAdapter` (Fase 3, docs/rio_search_plan.md §3.3,
§3.4, §3.12): arquitectura, early stopping por paciencia (nunca por tiempo, Decision #13),
checkpoint/reload y reproducibilidad en CPU con el mismo seed -- todo con tensores sinteticos,
sin tocar Databricks/MLflow."""

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
from rio_search.infrastructure.models.torch.bilstm import BiLSTMAdapter

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
    # y correlaciona con la ultima fila de X (seniales aprendibles, no ruido puro) para que
    # val_loss efectivamente mejore con el entrenamiento.
    base = seq.X[:, -1, 0]
    noise = rng.normal(scale=0.05, size=(len(base), n_outputs)).astype(np.float32)
    return (base.reshape(-1, 1) + noise).astype(np.float64)


def _build_adapter(n_features: int, n_outputs: int, horizons: tuple[int, ...] = HORIZONS) -> BiLSTMAdapter:
    adapter = BiLSTMAdapter()
    spec = ModelSpec(
        name="bilstm",
        horizon_strategy=HorizonStrategy.MULTI_OUTPUT,
        params={"hidden_size": 8, "num_layers": 1, "dropout": 0.0, "horizons": list(horizons)},
    )
    adapter.build(spec, n_features=n_features, n_outputs=n_outputs, device=CPU)
    return adapter


def _training(max_epochs: int = 20, patience: int = 5, seed: int = 42) -> TrainingSpec:
    return TrainingSpec(
        max_epochs=max_epochs,
        batch_size=16,
        optimizer_name="adam",
        optimizer_lr=0.01,
        optimizer_weight_decay=0.0,
        loss="mse",
        early_stopping_monitor="val/loss",
        early_stopping_patience=patience,
        grad_clip=1.0,
        seed=seed,
        device="cpu",
    )


def test_build_and_fit_produces_decreasing_loss_and_full_fit_result() -> None:
    train_seq = _synthetic_sequences(n=200, lookback=10, n_features=3, seed=0)
    val_seq = _synthetic_sequences(n=60, lookback=10, n_features=3, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS), seed=10)
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS), seed=11)

    adapter = _build_adapter(n_features=3, n_outputs=len(HORIZONS))
    training = _training(max_epochs=15, patience=15)
    result = adapter.fit(train_seq, val_seq, training, train_y=train_y, val_y=val_y)

    assert result.epochs >= 1
    assert 1 <= result.best_epoch <= result.epochs
    assert len(result.train_losses) == result.epochs
    assert len(result.val_losses) == result.epochs
    assert len(result.epoch_seconds) == result.epochs
    assert all(s >= 0.0 for s in result.epoch_seconds)
    assert result.train_to_best_epoch_s <= sum(result.epoch_seconds) + 1e-9
    assert result.train_samples_per_s > 0.0
    # Con una señal aprendible y suficientes epochs, la loss de train debe bajar.
    assert result.train_losses[-1] < result.train_losses[0]


def test_fit_requires_targets() -> None:
    train_seq = _synthetic_sequences(n=50, lookback=5, n_features=2, seed=0)
    val_seq = _synthetic_sequences(n=20, lookback=5, n_features=2, seed=1)
    adapter = _build_adapter(n_features=2, n_outputs=len(HORIZONS))
    with pytest.raises(ValueError, match="train_y/val_y"):
        adapter.fit(train_seq, val_seq, _training())


def test_early_stopping_by_patience_stops_before_max_epochs_never_by_time() -> None:
    """Decision #13: el techo `max_epochs` es de seguridad, no un presupuesto. Con targets que
    no correlacionan con las features (ruido puro) y poca paciencia, val_loss deja de mejorar
    rapido y el entrenamiento corta bien antes de `max_epochs`."""
    n_features = 3
    train_seq = _synthetic_sequences(n=120, lookback=8, n_features=n_features, seed=5)
    val_seq = _synthetic_sequences(n=40, lookback=8, n_features=n_features, seed=6)
    rng = np.random.default_rng(99)
    train_y = rng.normal(size=(120, len(HORIZONS))).astype(np.float64)
    val_y = rng.normal(size=(40, len(HORIZONS))).astype(np.float64)

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    result = adapter.fit(
        train_seq, val_seq, _training(max_epochs=1000, patience=3), train_y=train_y, val_y=val_y
    )

    assert result.epochs < 1000


def test_predict_shape_matches_horizons() -> None:
    n_features = 2
    seq = _synthetic_sequences(n=30, lookback=6, n_features=n_features, seed=2)
    train_seq = _synthetic_sequences(n=80, lookback=6, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=6, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    adapter.fit(train_seq, val_seq, _training(max_epochs=3, patience=3), train_y=train_y, val_y=val_y)
    predictions = adapter.predict(seq)

    assert predictions.y_pred.shape == (30, len(HORIZONS))
    assert predictions.horizons == HORIZONS
    assert predictions.anchor_dates == seq.anchor_dates


def test_save_and_load_roundtrip_reproduces_predictions(tmp_path: Path) -> None:
    n_features = 3
    train_seq = _synthetic_sequences(n=100, lookback=7, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=7, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    adapter.fit(train_seq, val_seq, _training(max_epochs=5, patience=5), train_y=train_y, val_y=val_y)
    before = adapter.predict(val_seq).y_pred

    adapter.save(tmp_path / "model_state.json")
    assert (tmp_path / "model_state_dict.pth").exists()
    assert (tmp_path / "architecture.json").exists()

    loaded = BiLSTMAdapter.load(tmp_path / "model_state.json", device=CPU)
    after = loaded.predict(val_seq).y_pred

    np.testing.assert_allclose(before, after, rtol=1e-6, atol=1e-6)


def test_same_seed_on_cpu_reproduces_fit_result() -> None:
    """Criterio de cierre de la Fase 3 (§5): "re-corrida con el mismo seed en CPU reproduce
    las metricas". Dos adaptadores frescos, mismos datos, mismo seed, device=cpu -> mismas
    curvas de loss bit a bit (o dentro de una tolerancia muy chica de punto flotante)."""
    n_features = 3
    train_seq = _synthetic_sequences(n=100, lookback=7, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=7, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    training = _training(max_epochs=6, patience=6, seed=123)

    adapter_a = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    result_a = adapter_a.fit(train_seq, val_seq, training, train_y=train_y, val_y=val_y)

    adapter_b = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    result_b = adapter_b.fit(train_seq, val_seq, training, train_y=train_y, val_y=val_y)

    np.testing.assert_allclose(result_a.train_losses, result_b.train_losses, rtol=1e-5, atol=1e-8)
    np.testing.assert_allclose(result_a.val_losses, result_b.val_losses, rtol=1e-5, atol=1e-8)

    pred_a = adapter_a.predict(val_seq).y_pred
    pred_b = adapter_b.predict(val_seq).y_pred
    np.testing.assert_allclose(pred_a, pred_b, rtol=1e-5, atol=1e-8)


def test_per_horizon_n_outputs_one_is_supported_by_the_same_adapter() -> None:
    """§3.3: "un adaptador que soporte n_outputs=1 ya soporta per_horizon gratis" -- no hace
    falta una clase distinta, solo construirlo con n_outputs=1 y horizons=(h,)."""
    n_features = 2
    train_seq = _synthetic_sequences(n=80, lookback=5, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=30, lookback=5, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=1)
    val_y = _synthetic_targets(val_seq, n_outputs=1)

    adapter = _build_adapter(n_features=n_features, n_outputs=1, horizons=(3,))
    training = _training(max_epochs=3, patience=3)
    result = adapter.fit(train_seq, val_seq, training, train_y=train_y, val_y=val_y)
    predictions = adapter.predict(val_seq)

    assert result.epochs >= 1
    assert predictions.y_pred.shape == (30, 1)
    assert predictions.horizons == (3,)


def test_fit_masks_nan_targets_and_does_not_diverge() -> None:
    """Decision 043: `Targets.y` (Fase 1) trae `NaN` por huecos reales de calendario en el
    target (§2.1); sin enmascarar antes de la funcion de perdida, un unico `NaN` en un batch
    contamina la reduccion `mean()` de PyTorch y el `train/val loss` diverge a `NaN` desde el
    primer epoch (hallazgo real contra el dataset de Gold, no hipotetico)."""
    n_features = 3
    train_seq = _synthetic_sequences(n=150, lookback=8, n_features=n_features, seed=0)
    val_seq = _synthetic_sequences(n=50, lookback=8, n_features=n_features, seed=1)
    train_y = _synthetic_targets(train_seq, n_outputs=len(HORIZONS))
    val_y = _synthetic_targets(val_seq, n_outputs=len(HORIZONS))

    # ~15% de las filas de TRAIN sin ningun target valido (simula una cola de huecos de
    # calendario, §2.1) + algunas celdas sueltas de VAL en NaN.
    rng = np.random.default_rng(7)
    train_y = train_y.copy()
    holes = rng.choice(len(train_y), size=int(0.15 * len(train_y)), replace=False)
    train_y[holes, :] = np.nan
    val_y = val_y.copy()
    val_y[0, 0] = np.nan
    val_y[1, 3] = np.nan

    adapter = _build_adapter(n_features=n_features, n_outputs=len(HORIZONS))
    training = _training(max_epochs=10, patience=10)
    result = adapter.fit(train_seq, val_seq, training, train_y=train_y, val_y=val_y)

    assert not any(np.isnan(v) for v in result.train_losses)
    assert not any(np.isnan(v) for v in result.val_losses)
    assert result.train_losses[-1] < result.train_losses[0]

    predictions = adapter.predict(val_seq)
    assert not np.isnan(predictions.y_pred).any()


def test_bilstm_registered_with_torch_family_and_both_horizon_strategies() -> None:
    adapter = BiLSTMAdapter()
    assert adapter.name == "bilstm"
    assert adapter.family == ModelFamily.TORCH
    assert adapter.supports == {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}
