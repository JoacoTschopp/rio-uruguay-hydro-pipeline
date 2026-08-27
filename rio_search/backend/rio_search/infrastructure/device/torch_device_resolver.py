"""Resolucion de device con PyTorch (Decision #6, docs/rio_search_plan.md §3.4).

`resolve()` se invoca al inicio de `RunSearch` y de `IssueDailyForecast` (tambien en cada
re-ejecucion de prediccion): 1) CUDA, 2) Apple MPS, 3) CPU. Nunca aborta.
"""

from __future__ import annotations

import os
import platform

import torch

from rio_search.application.ports.device_resolver import PreferredDevice
from rio_search.domain.shared.device import Device

_BYTES_PER_GIB = 1024**3


class TorchDeviceResolver:
    """Implementa `application.ports.device_resolver.DeviceResolver`."""

    def resolve(self, preferred: PreferredDevice = "auto") -> Device:
        if preferred == "cpu":
            return self._cpu_device()
        if preferred == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("device=cuda pedido explicitamente pero CUDA no esta disponible.")
            return self._cuda_device()
        if preferred == "mps":
            if not self._mps_available():
                raise RuntimeError("device=mps pedido explicitamente pero MPS no esta disponible.")
            return self._mps_device()

        # auto: CUDA -> MPS -> CPU (Decision #6)
        if torch.cuda.is_available():
            return self._cuda_device()
        if self._mps_available():
            return self._mps_device()
        return self._cpu_device()

    @staticmethod
    def _mps_available() -> bool:
        backends = getattr(torch, "backends", None)
        mps = getattr(backends, "mps", None) if backends is not None else None
        return bool(mps is not None and mps.is_available())

    def _cuda_device(self) -> Device:
        index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(index)
        return Device(
            type="cuda",
            name=props.name,
            vram_gb=round(props.total_memory / _BYTES_PER_GIB, 2),
            cuda_version=torch.version.cuda,
            torch_version=torch.__version__,
            cpu=platform.processor() or platform.machine(),
            ram_gb=self._ram_gb(),
            hostname=platform.node(),
        )

    def _mps_device(self) -> Device:
        # PYTORCH_ENABLE_MPS_FALLBACK=1 para los kernels de Apple Silicon aun no soportados.
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        return Device(
            type="mps",
            name="Apple Silicon (MPS)",
            torch_version=torch.__version__,
            cpu=platform.processor() or platform.machine(),
            ram_gb=self._ram_gb(),
            hostname=platform.node(),
        )

    def _cpu_device(self) -> Device:
        return Device(
            type="cpu",
            name=platform.processor() or platform.machine(),
            torch_version=torch.__version__,
            cpu=platform.processor() or platform.machine(),
            ram_gb=self._ram_gb(),
            hostname=platform.node(),
        )

    @staticmethod
    def _ram_gb() -> float | None:
        try:
            import psutil  # type: ignore[import-not-found]

            return round(psutil.virtual_memory().total / _BYTES_PER_GIB, 1)
        except ImportError:
            return None
