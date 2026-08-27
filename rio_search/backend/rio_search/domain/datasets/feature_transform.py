"""`ExperimentalTransformSpec`: metadata versionada de una transformacion experimental
declarada en el YAML de un experimento (Decision #5, docs/rio_search_plan.md §3.6, §4.1).

Es solo la especificacion (nombre, version, columnas, params) para loguear en
`features/spec.json` y en el tag `experimental_transforms` (§3.5); la expresion Polars real
(`pl.Expr`) que la implementa vive en `infrastructure.preprocess.transforms` -- el dominio no
importa Polars. Sin dependencias del proyecto (regla de `domain`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ExperimentalTransformSpec:
    name: str
    version: int
    columns: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Identificador versionado para tags/artefactos, p. ej. `"clip@1"`."""
        return f"{self.name}@{self.version}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentalTransformSpec:
        remaining = dict(data)
        name = str(remaining.pop("name"))
        version = int(remaining.pop("version", 1))
        columns = tuple(remaining.pop("columns", []) or [])
        return cls(name=name, version=version, columns=columns, params=remaining)
