"""Tests de `TorchDeviceResolver` (Decision #6, docs/rio_search_plan.md §3.4): CUDA -> MPS ->
CPU, sin abortar nunca. CUDA real se ejercita si esta disponible en la maquina; MPS se simula
con monkeypatch (no hay Apple Silicon en CI/Windows)."""

from __future__ import annotations

import types

import pytest
import torch

from rio_search.infrastructure.device.torch_device_resolver import TorchDeviceResolver


def test_resolve_cpu_explicit() -> None:
    device = TorchDeviceResolver().resolve(preferred="cpu")
    assert device.type == "cpu"
    assert device.torch_version == torch.__version__


def test_resolve_auto_prefers_cuda_when_available() -> None:
    if not torch.cuda.is_available():
        pytest.skip(
            "No hay CUDA en esta maquina; cubierto por "
            "test_resolve_cuda_explicit_raises_without_cuda con monkeypatch."
        )
    device = TorchDeviceResolver().resolve(preferred="auto")
    assert device.type == "cuda"
    assert device.name  # nombre de GPU no vacio
    assert device.cuda_version is not None
    assert device.is_gpu


def test_resolve_cuda_explicit_raises_without_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError):
        TorchDeviceResolver().resolve(preferred="cuda")


def test_resolve_mps_simulated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    fake_mps = types.SimpleNamespace(is_available=lambda: True)
    monkeypatch.setattr(torch.backends, "mps", fake_mps, raising=False)

    device = TorchDeviceResolver().resolve(preferred="auto")

    assert device.type == "mps"
    assert device.is_gpu


def test_resolve_mps_explicit_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_mps = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setattr(torch.backends, "mps", fake_mps, raising=False)
    with pytest.raises(RuntimeError):
        TorchDeviceResolver().resolve(preferred="mps")


def test_resolve_auto_falls_back_to_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    fake_mps = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setattr(torch.backends, "mps", fake_mps, raising=False)

    device = TorchDeviceResolver().resolve(preferred="auto")

    assert device.type == "cpu"
    assert not device.is_gpu


def test_device_as_tags_has_fixed_keys() -> None:
    device = TorchDeviceResolver().resolve(preferred="cpu")
    tags = device.as_tags()
    assert tags["device"] == "cpu"
    assert "torch_version" in tags
