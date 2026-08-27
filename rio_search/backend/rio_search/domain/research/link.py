"""`Link`: vinculo de una `Note` a una `Decision NNN` (`docs/decisions.md`) o a un `run_id` de
MLflow (docs/rio_search_plan.md §3.10: "`Note` ... con `links` a `Decision NNN` y a `run_id`").
Sin dependencias del proyecto (regla de `domain`).

Las notas se persisten como Markdown (§3.10) -- `Link` es la representacion estructurada que usa
la API/UI para que "vincular a Decision y run" sea un formulario con dos campos, no texto libre; se
renderiza dentro de la seccion "## Enlaces" de la nota (`Note.to_markdown`) y se reconstruye al
leerla (`Note.from_markdown`) via `Link.parse_markdown_line`, en vez de guardarse en un archivo
aparte -- el repo (el propio `.md`) sigue siendo la base, sin una tabla de vinculos extra.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class LinkKind(str, Enum):
    DECISION = "decision"
    RUN = "run"


_DECISION_LINE = re.compile(r"^-\s*Decisi[oó]n:\s*Decisi[oó]n\s+(\d+)\s*$", re.IGNORECASE)
_RUN_LINE = re.compile(r"^-\s*Run:\s*`([^`]+)`\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Link:
    kind: LinkKind
    ref: str  # numero de decision como texto ("041") o run_id de MLflow

    def __post_init__(self) -> None:
        ref = self.ref.strip()
        if not ref:
            raise ValueError("Link.ref no puede ser vacio")
        if self.kind is LinkKind.DECISION and not ref.isdigit():
            raise ValueError(f"Link a Decision debe ser numerico, recibido {ref!r}")
        object.__setattr__(self, "ref", ref)

    @staticmethod
    def to_decision(number: int) -> "Link":
        return Link(kind=LinkKind.DECISION, ref=str(number).zfill(3))

    @staticmethod
    def to_run(run_id: str) -> "Link":
        return Link(kind=LinkKind.RUN, ref=run_id)

    def to_markdown_line(self) -> str:
        if self.kind is LinkKind.DECISION:
            return f"- Decisión: Decisión {self.ref}"
        return f"- Run: `{self.ref}`"

    @staticmethod
    def parse_markdown_line(line: str) -> "Link | None":
        """Inverso de `to_markdown_line`; `None` si la linea no matchea (texto libre que el
        usuario haya agregado a mano en la seccion "## Enlaces")."""
        match = _DECISION_LINE.match(line.strip())
        if match:
            return Link(kind=LinkKind.DECISION, ref=match.group(1))
        match = _RUN_LINE.match(line.strip())
        if match:
            return Link(kind=LinkKind.RUN, ref=match.group(1))
        return None
