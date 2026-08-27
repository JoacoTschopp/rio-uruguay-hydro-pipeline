"""`AddDocument` (Fase 7, docs/rio_search_plan.md §3.10, §4.2: "rio-search research add <pdf>
--title ... --authors ... --year ..."; §3.9/§5: "subir PDF" desde la UI). Crea el `Document` en el
catalogo (y, si se subio un archivo, lo guarda via el `DocumentStorePort`) y una `Note` vacia para
que la pagina Research pueda abrir "editar notas" sin un 404 -- la nota real la llena
`UpdateNote` despues.
"""

from __future__ import annotations

from datetime import datetime, timezone

from rio_search.application.ports.document_store import DocumentStorePort
from rio_search.domain.research.document import Document, slugify
from rio_search.domain.research.document_type import DocumentType
from rio_search.domain.research.note import Note
from rio_search.domain.research.tag import Tag


class AddDocument:
    def __init__(self, store: DocumentStorePort) -> None:
        self._store = store

    def execute(
        self,
        title: str,
        authors: tuple[str, ...],
        year: int,
        type: DocumentType,
        venue: str | None = None,
        doi_url: str | None = None,
        tags: tuple[Tag, ...] = (),
        slug: str | None = None,
        file_content: bytes | None = None,
        file_name: str | None = None,
    ) -> Document:
        resolved_slug = slug.strip() if slug else slugify(title, year)
        if self._store.get_document(resolved_slug) is not None:
            raise ValueError(f"ya existe un documento con slug {resolved_slug!r}")

        document = Document(
            slug=resolved_slug,
            title=title,
            authors=authors,
            year=year,
            type=type,
            venue=venue,
            doi_url=doi_url,
            tags=tags,
            file=None,
            added_at=datetime.now(timezone.utc).isoformat(),
        )

        if file_content is not None:
            if not file_name:
                raise ValueError("file_name es obligatorio cuando se sube file_content")
            relative_path = self._store.save_file(resolved_slug, file_name, file_content)
            document = document.with_file(relative_path)

        self._store.save_document(document)
        self._store.save_note(Note.empty(resolved_slug), title=document.title)
        return document
