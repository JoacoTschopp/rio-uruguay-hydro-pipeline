"""Puerto de persistencia de la biblioteca de investigacion (Fase 7, docs/rio_search_plan.md
§3.10: "Persistencia versionable y legible: `research/catalog/<slug>.yaml` + `research/notes/
<slug>.md`; los PDF en `research/documents/` quedan fuera de git"). Implementado por
`infrastructure.research.filesystem_document_store.FileSystemDocumentStore`.
"""

from __future__ import annotations

from typing import Protocol

from rio_search.domain.research.document import Document
from rio_search.domain.research.note import Note


class DocumentStorePort(Protocol):
    def save_document(self, document: Document) -> None:
        """Escribe/sobrescribe `research/catalog/<slug>.yaml`."""
        ...

    def get_document(self, slug: str) -> Document | None:
        ...

    def list_documents(self) -> tuple[Document, ...]:
        """Todos los documentos del catalogo, orden estable (por `slug`)."""
        ...

    def save_note(self, note: Note, title: str) -> None:
        """Escribe/sobrescribe `research/notes/<slug>.md` (`title` va en el encabezado `# ...`,
        Document.title en el momento de guardar -- la nota no repite metadatos del documento)."""
        ...

    def get_note(self, slug: str) -> Note | None:
        ...

    def save_file(self, slug: str, filename: str, content: bytes) -> str:
        """Guarda el PDF bajo `research/documents/` (fuera de git, §3.10) y devuelve la ruta
        relativa a `rio_search/research/` que va en `Document.file`."""
        ...

    def read_file(self, slug: str) -> tuple[bytes, str] | None:
        """Bytes + nombre de archivo del PDF subido para `slug`, o `None` si no hay ninguno."""
        ...
