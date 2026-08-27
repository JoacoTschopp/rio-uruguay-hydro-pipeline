"""`FeatureCatalog`: agregado sobre los `FeatureGroup` cargados de
`configs/feature_groups.yaml` (docs/rio_search_plan.md §3.6, Fase 1). Valida contra las
columnas reales del parquet descargado -- falla explicito y claro si Gold cambio de esquema
(riesgo de §6). Sin dependencias del proyecto (regla de `domain`): quien lee el YAML de disco
es `infrastructure.datasets.feature_catalog_loader`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from rio_search.domain.datasets.feature_group import FeatureGroup


@dataclass(frozen=True, slots=True)
class FeatureCatalog:
    groups: tuple[FeatureGroup, ...]

    def group(self, name: str) -> FeatureGroup:
        for group in self.groups:
            if group.name == name:
                return group
        raise KeyError(
            f"Grupo de features desconocido: {name!r}. Disponibles: "
            f"{sorted(g.name for g in self.groups)}"
        )

    def default_on_groups(self) -> tuple[str, ...]:
        return tuple(g.name for g in self.groups if g.default_on)

    def columns_for(self, group_names: Iterable[str]) -> tuple[str, ...]:
        """Columnas de los grupos pedidos, en orden de aparicion y sin duplicados (un grupo
        puede repetirse por error en el YAML de experimento sin que eso duplique columnas)."""
        seen: set[str] = set()
        ordered: list[str] = []
        for name in group_names:
            for column in self.group(name).columns:
                if column not in seen:
                    seen.add(column)
                    ordered.append(column)
        return tuple(ordered)

    def all_columns(self) -> tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for group in self.groups:
            for column in group.columns:
                if column not in seen:
                    seen.add(column)
                    ordered.append(column)
        return tuple(ordered)

    def validate_against(self, available_columns: Iterable[str]) -> None:
        """Falla explicito si el catalogo referencia columnas que ya no existen en el
        dataset descargado (Gold cambio de esquema). No falla por columnas nuevas en el
        dataset que el catalogo todavia no conoce -- eso lo reporta `unassigned_columns`."""
        available = set(available_columns)
        missing = [
            f"{group.name}.{column}"
            for group in self.groups
            for column in group.columns
            if column not in available
        ]
        if missing:
            raise ValueError(
                "El catalogo de features (configs/feature_groups.yaml) referencia columnas "
                f"que no existen en el dataset descargado (¿Gold cambio de esquema?): "
                f"{'; '.join(missing)}"
            )

    def unassigned_columns(self, available_columns: Iterable[str]) -> tuple[str, ...]:
        """Columnas del dataset que ningun grupo del catalogo cubre todavia (informativo,
        no falla: alimenta `DescribeDataset` para que la Fase 1 vea que Gold crecio)."""
        catalogued = set(self.all_columns())
        return tuple(c for c in available_columns if c not in catalogued)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureCatalog:
        groups = tuple(
            FeatureGroup(
                name=str(name),
                columns=tuple(spec.get("columns", []) or []),
                default_on=bool(spec.get("default_on", False)),
                description=str(spec.get("description", "")),
            )
            for name, spec in data.get("groups", {}).items()
        )
        return cls(groups=groups)
