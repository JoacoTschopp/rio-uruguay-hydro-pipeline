"""Tests de `domain.models.model_registry` (Fase 2, docs/rio_search_plan.md §3.3): plugins por
decorador. Usa nombres unicos (`test_dummy_*`) para no interferir con los adaptadores naive
reales registrados por `infrastructure.models` en otros tests del mismo proceso (registro
global de modulo)."""

from __future__ import annotations

import pytest

from rio_search.domain.models.model_registry import ModelRegistry, register_model


def test_register_and_get_roundtrip() -> None:
    @register_model("test_dummy_a")
    class DummyA:
        pass

    registry = ModelRegistry()
    assert registry.get("test_dummy_a") is DummyA
    assert "test_dummy_a" in registry.names()


def test_get_unknown_model_raises_key_error_with_available_names() -> None:
    registry = ModelRegistry()
    with pytest.raises(KeyError, match="no_existe_este_modelo"):
        registry.get("no_existe_este_modelo")


def test_registering_same_name_with_different_class_raises() -> None:
    @register_model("test_dummy_b")
    class DummyB1:
        pass

    with pytest.raises(ValueError, match="test_dummy_b"):

        @register_model("test_dummy_b")
        class DummyB2:
            pass


def test_registering_same_class_twice_under_same_name_is_idempotent() -> None:
    @register_model("test_dummy_c")
    class DummyC:
        pass

    # re-decorar la misma clase con el mismo nombre (p. ej. reimport de modulo) no debe fallar
    register_model("test_dummy_c")(DummyC)
    assert ModelRegistry().get("test_dummy_c") is DummyC


def test_naive_adapters_are_registered_after_importing_infrastructure_models() -> None:
    import rio_search.infrastructure.models  # noqa: F401 - efecto secundario

    registry = ModelRegistry()
    assert {"persistence", "climatology", "seasonal_naive"}.issubset(set(registry.names()))
