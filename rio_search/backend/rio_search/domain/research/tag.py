"""`Tag`: etiqueta libre de un `Document` (docs/rio_search_plan.md §3.10, §3.2: "Research: `Document`
... `tags` ..."). Sin dependencias del proyecto (regla de `domain`).

Normaliza a minusculas y sin espacios en los bordes para que "LSTM" y "lstm " sean el mismo tag al
filtrar/agrupar en la UI -- el texto visible en la UI puede seguir escribiendose como quiera el
usuario (la normalizacion no toca mayusculas internas de siglas si no hay espacios, p. ej. "LSTM"
se guarda como "lstm"; es una decision deliberada de simplicidad, no un requisito del plan).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Tag:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not normalized:
            raise ValueError("Tag no puede ser vacio")
        if normalized != self.value:
            object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value

    @staticmethod
    def parse_many(raw: str) -> tuple["Tag", ...]:
        """`"lstm, hidrologia , LSTM"` -> `(Tag("lstm"), Tag("hidrologia"))` (separador `,`,
        duplicados descartados preservando el primer orden de aparicion)."""
        seen: dict[str, Tag] = {}
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            tag = Tag(chunk)
            seen.setdefault(tag.value, tag)
        return tuple(seen.values())
