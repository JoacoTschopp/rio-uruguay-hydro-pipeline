"""`UpdateNote` (Fase 7, docs/rio_search_plan.md §3.10, §5: "editar ... notas por seccion,
vincular a Decision y run"). Reemplaza la `Note` completa de un documento -- el formulario de la
UI manda las 6 secciones y los links en cada guardado (mismo patron que `TagDocument`: la UI edita
el estado completo, no un patch parcial)."""

from __future__ import annotations

from rio_search.application.ports.document_store import DocumentStorePort
from rio_search.domain.research.link import Link
from rio_search.domain.research.note import Note


class UpdateNote:
    def __init__(self, store: DocumentStorePort) -> None:
        self._store = store

    def execute(self, slug: str, sections: dict[str, str], links: tuple[Link, ...] = ()) -> Note:
        document = self._store.get_document(slug)
        if document is None:
            raise ValueError(f"documento {slug!r} no existe en el catalogo")

        note = Note(slug=slug, sections=dict(sections), links=links)
        self._store.save_note(note, title=document.title)
        return note
