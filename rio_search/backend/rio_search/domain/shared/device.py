"""Value object de hardware de computo (Decision #6, docs/rio_search_plan.md §3.4).

Sin dependencias del proyecto (regla de `domain`, §3.2): no importa `torch` ni nada de
`infrastructure`. Quien resuelve el device real es `infrastructure.device.torch_device_resolver`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DeviceType = Literal["cuda", "mps", "cpu"]


@dataclass(frozen=True, slots=True)
class Device:
    """Hardware sobre el que corre un experimento o una prediccion.

    Se loguea como tag `rio_search.device` (+ hardware, §3.12) y se persiste en cada `Forecast`.
    """

    type: DeviceType
    name: str | None = None
    vram_gb: float | None = None
    cuda_version: str | None = None
    torch_version: str | None = None
    cpu: str | None = None
    ram_gb: float | None = None
    hostname: str | None = None

    @property
    def is_gpu(self) -> bool:
        return self.type in ("cuda", "mps")

    def as_tags(self) -> dict[str, str]:
        """Tags de hardware (§3.12): sin esto un tiempo no se puede comparar entre maquinas."""
        tags: dict[str, str] = {"device": self.type}
        if self.name is not None:
            tags["device_name"] = self.name
        if self.cuda_version is not None:
            tags["cuda_version"] = self.cuda_version
        if self.torch_version is not None:
            tags["torch_version"] = self.torch_version
        if self.cpu is not None:
            tags["cpu"] = self.cpu
        if self.ram_gb is not None:
            tags["ram_gb"] = f"{self.ram_gb:.1f}"
        if self.hostname is not None:
            tags["hostname"] = self.hostname
        return tags
