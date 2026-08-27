"""Puerto de exportacion de bibliografia (Fase 7, docs/rio_search_plan.md §3.10: "`ExportBibtex`
escribe `rio_search/thesis/common/references.bib`"). Implementado por
`infrastructure.research.bibtex_exporter.FileBibtexExporter`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from rio_search.domain.research.bib_entry import BibEntry


class BibliographyExportPort(Protocol):
    def write(self, entries: tuple[BibEntry, ...], output_path: Path) -> Path:
        """Formatea `entries` como `.bib` (una entrada por documento, §3.10) y las escribe en
        `output_path` (crea los directorios padres si hace falta). Devuelve `output_path`."""
        ...
