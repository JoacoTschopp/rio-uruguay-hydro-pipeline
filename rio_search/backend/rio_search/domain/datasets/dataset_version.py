"""`DatasetVersion`: agregado raiz del contexto Datasets (docs/rio_search_plan.md §3.2).

Invariante que protege: toda corrida referencia `delta_version` + `sha256` del parquet
(Decision #10). Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    delta_version: int
    sha256: str
    rows: int
    fecha_min: str
    fecha_max: str
    columns: tuple[str, ...]
    punto_prediccion: str | None = None
    exported_at: str | None = None

    def as_tags(self) -> dict[str, str]:
        """Tags `rio_search.dataset_delta_version` / `dataset_sha256` (§3.5)."""
        return {
            "dataset_delta_version": str(self.delta_version),
            "dataset_sha256": self.sha256,
        }

    def has_column(self, name: str) -> bool:
        return name in self.columns

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> DatasetVersion:
        """Construye desde `manifest.json` (mismo formato que exporta
        `notebooks/05_Gold/Export_Gold_Snapshot`, portado en Decision #10)."""
        return cls(
            delta_version=int(manifest["delta_version"]),
            sha256=str(manifest["file_sha256"]),
            rows=int(manifest.get("rows", 0)),
            fecha_min=str(manifest.get("fecha_min", "")),
            fecha_max=str(manifest.get("fecha_max", "")),
            columns=tuple(manifest.get("columns", [])),
            punto_prediccion=manifest.get("punto_prediccion"),
            exported_at=manifest.get("exported_at"),
        )
