"""Puerto de resolucion de device (§3.2, §3.4 de docs/rio_search_plan.md)."""

from __future__ import annotations

from typing import Literal, Protocol

from rio_search.domain.shared.device import Device

PreferredDevice = Literal["auto", "cuda", "mps", "cpu"]


class DeviceResolver(Protocol):
    def resolve(self, preferred: PreferredDevice = "auto") -> Device:
        """CUDA -> MPS -> CPU (Decision #6). Nunca aborta: cae a CPU y lo loguea."""
        ...
