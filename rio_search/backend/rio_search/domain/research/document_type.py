"""`DocumentType` (docs/rio_search_plan.md §3.10): "`type` (paper | tesis | informe | plantilla)".
Sin dependencias del proyecto (regla de `domain`). Valores en espanol -- vocabulario de dominio de
la biblioteca de investigacion, no columnas de Gold, pero igual de "propios de la tesis" que
`TargetVariable` (caudal/nivel): se preservan tal como los escribio el plan.
"""

from __future__ import annotations

from enum import Enum


class DocumentType(str, Enum):
    PAPER = "paper"
    TESIS = "tesis"
    INFORME = "informe"
    PLANTILLA = "plantilla"

    @property
    def bibtex_entry_type(self) -> str:
        """Tipo de entrada BibTeX por defecto para este `DocumentType` (§3.10: "`ExportBibtex`
        escribe ... una entrada por documento"). El usuario puede seguir citando con `\\cite{slug}`
        sin que le importe el tipo exacto de entrada."""
        return {
            DocumentType.PAPER: "article",
            DocumentType.TESIS: "phdthesis",
            DocumentType.INFORME: "techreport",
            DocumentType.PLANTILLA: "misc",
        }[self]
