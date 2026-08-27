"""`ExportBibtex` (Fase 7, docs/rio_search_plan.md §3.10: "`ExportBibtex` escribe
`rio_search/thesis/common/references.bib` (una entrada por documento, clave = `slug`). La tesis
cita con `\\cite{slug}`"). Lee todo el catalogo, valida cada `Document` como `BibEntry` (invariante
del agregado, §3.2) y delega el formateo/escritura al `BibliographyExportPort`
(`infrastructure.research.bibtex_exporter.FileBibtexExporter`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rio_search.application.ports.bibliography_export import BibliographyExportPort
from rio_search.application.ports.document_store import DocumentStorePort


@dataclass(frozen=True, slots=True)
class ExportBibtexResult:
    output_path: Path
    entry_count: int
    keys: tuple[str, ...]


class ExportBibtex:
    def __init__(self, store: DocumentStorePort, exporter: BibliographyExportPort) -> None:
        self._store = store
        self._exporter = exporter

    def execute(self, output_path: Path) -> ExportBibtexResult:
        documents = self._store.list_documents()
        entries = tuple(d.to_bib_entry() for d in documents)
        written = self._exporter.write(entries, output_path)
        return ExportBibtexResult(
            output_path=written,
            entry_count=len(entries),
            keys=tuple(e.key for e in entries),
        )
