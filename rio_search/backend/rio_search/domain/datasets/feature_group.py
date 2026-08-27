"""`FeatureGroup`: catalogo de columnas de Gold agrupadas por familia (docs/rio_search_plan.md
§3.6). Sin dependencias del proyecto (regla de `domain`)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeatureGroup:
    name: str
    columns: tuple[str, ...]
    default_on: bool
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FeatureGroup requiere 'name'")
