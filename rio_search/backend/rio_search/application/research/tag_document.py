"""`TagDocument` (Fase 7, docs/rio_search_plan.md §3.10, §5: "editar ... tags"). Reemplaza el
conjunto de tags de un documento existente y persiste el `Document` actualizado -- mismo patron
`with_tags` (frozen dataclass, Fase 6) que `Champion`/`Forecast`."""

from __future__ import annotations

from rio_search.application.ports.document_store import DocumentStorePort
from rio_search.domain.research.document import Document
from rio_search.domain.research.tag import Tag


class TagDocument:
    def __init__(self, store: DocumentStorePort) -> None:
        self._store = store

    def execute(self, slug: str, tags: tuple[Tag, ...]) -> Document:
        document = self._store.get_document(slug)
        if document is None:
            raise ValueError(f"documento {slug!r} no existe en el catalogo")

        updated = document.with_tags(tags)
        self._store.save_document(updated)
        return updated
