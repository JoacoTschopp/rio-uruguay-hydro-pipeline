"""Tests offline de `application/research/*` (Fase 7): `AddDocument`, `UpdateNote`,
`TagDocument`, `ExportBibtex` contra un `DocumentStorePort` falso en memoria (mismo patron que
`test_promote_champion.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rio_search.application.research.add_document import AddDocument
from rio_search.application.research.export_bibtex import ExportBibtex
from rio_search.application.research.tag_document import TagDocument
from rio_search.application.research.update_note import UpdateNote
from rio_search.domain.research.document import Document
from rio_search.domain.research.document_type import DocumentType
from rio_search.domain.research.link import Link
from rio_search.domain.research.note import Note
from rio_search.domain.research.tag import Tag


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}
        self.notes: dict[str, Note] = {}
        self.files: dict[str, tuple[bytes, str]] = {}
        self.saved_note_titles: dict[str, str] = {}

    def save_document(self, document: Document) -> None:
        self.documents[document.slug] = document

    def get_document(self, slug: str) -> Document | None:
        return self.documents.get(slug)

    def list_documents(self) -> tuple[Document, ...]:
        return tuple(sorted(self.documents.values(), key=lambda d: d.slug))

    def save_note(self, note: Note, title: str) -> None:
        self.notes[note.slug] = note
        self.saved_note_titles[note.slug] = title

    def get_note(self, slug: str) -> Note | None:
        return self.notes.get(slug)

    def save_file(self, slug: str, filename: str, content: bytes) -> str:
        self.files[slug] = (content, filename)
        return f"documents/{slug}.pdf"

    def read_file(self, slug: str):
        return self.files.get(slug)


class RecordingBibliographyExporter:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, Path]] = []

    def write(self, entries, output_path: Path) -> Path:
        self.calls.append((entries, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n\n".join(e.to_bibtex() for e in entries), encoding="utf-8")
        return output_path


# ---------------------------------------------------------------------- AddDocument


def test_add_document_creates_catalog_entry_and_empty_note() -> None:
    store = InMemoryDocumentStore()
    add_document = AddDocument(store)

    document = add_document.execute(
        title="Long Short-Term Memory",
        authors=("Hochreiter, S.", "Schmidhuber, J."),
        year=1997,
        type=DocumentType.PAPER,
        venue="Neural Computation",
        tags=(Tag("lstm"),),
    )

    assert document.slug == "long-short-term-memory-1997"
    assert store.get_document(document.slug) is document
    assert store.get_note(document.slug) is not None
    assert store.saved_note_titles[document.slug] == "Long Short-Term Memory"


def test_add_document_with_explicit_slug() -> None:
    store = InMemoryDocumentStore()
    add_document = AddDocument(store)
    document = add_document.execute(
        title="Título", authors=("A",), year=2020, type=DocumentType.INFORME, slug="mi-slug"
    )
    assert document.slug == "mi-slug"


def test_add_document_rejects_duplicate_slug() -> None:
    store = InMemoryDocumentStore()
    add_document = AddDocument(store)
    add_document.execute(title="T", authors=("A",), year=2020, type=DocumentType.PAPER, slug="dup")
    with pytest.raises(ValueError):
        add_document.execute(title="Otro", authors=("B",), year=2021, type=DocumentType.PAPER, slug="dup")


def test_add_document_saves_uploaded_file() -> None:
    store = InMemoryDocumentStore()
    add_document = AddDocument(store)
    document = add_document.execute(
        title="Con PDF",
        authors=("A",),
        year=2020,
        type=DocumentType.PAPER,
        slug="con-pdf",
        file_content=b"%PDF-1.4 contenido de prueba",
        file_name="paper.pdf",
    )
    assert document.file == "documents/con-pdf.pdf"
    assert store.files["con-pdf"] == (b"%PDF-1.4 contenido de prueba", "paper.pdf")


def test_add_document_requires_file_name_with_file_content() -> None:
    store = InMemoryDocumentStore()
    add_document = AddDocument(store)
    with pytest.raises(ValueError):
        add_document.execute(
            title="T", authors=("A",), year=2020, type=DocumentType.PAPER, file_content=b"abc"
        )


# ---------------------------------------------------------------------- UpdateNote


def test_update_note_persists_sections_and_links() -> None:
    store = InMemoryDocumentStore()
    AddDocument(store).execute(title="T", authors=("A",), year=2020, type=DocumentType.PAPER, slug="s1")
    update_note = UpdateNote(store)

    note = update_note.execute(
        "s1",
        sections={"methodology": "Se usa BiLSTM.", "results": "Supera persistencia."},
        links=(Link.to_decision(41),),
    )

    assert note.section("methodology") == "Se usa BiLSTM."
    assert store.get_note("s1").section("results") == "Supera persistencia."
    assert store.get_note("s1").links == (Link.to_decision(41),)


def test_update_note_rejects_unknown_document() -> None:
    store = InMemoryDocumentStore()
    update_note = UpdateNote(store)
    with pytest.raises(ValueError):
        update_note.execute("no-existe", sections={})


# ---------------------------------------------------------------------- TagDocument


def test_tag_document_replaces_tags() -> None:
    store = InMemoryDocumentStore()
    AddDocument(store).execute(
        title="T", authors=("A",), year=2020, type=DocumentType.PAPER, slug="s1", tags=(Tag("viejo"),)
    )
    tag_document = TagDocument(store)

    updated = tag_document.execute("s1", (Tag("nuevo"), Tag("otro")))

    assert updated.tags == (Tag("nuevo"), Tag("otro"))
    assert store.get_document("s1").tags == (Tag("nuevo"), Tag("otro"))


def test_tag_document_rejects_unknown_document() -> None:
    store = InMemoryDocumentStore()
    tag_document = TagDocument(store)
    with pytest.raises(ValueError):
        tag_document.execute("no-existe", (Tag("x"),))


# ---------------------------------------------------------------------- ExportBibtex


def test_export_bibtex_writes_one_entry_per_document(tmp_path: Path) -> None:
    store = InMemoryDocumentStore()
    add_document = AddDocument(store)
    add_document.execute(
        title="Long Short-Term Memory",
        authors=("Hochreiter, S.",),
        year=1997,
        type=DocumentType.PAPER,
        venue="Neural Computation",
        slug="hochreiter-1997",
    )
    add_document.execute(
        title="Otro paper",
        authors=("B",),
        year=2020,
        type=DocumentType.INFORME,
        slug="otro-2020",
    )
    exporter = RecordingBibliographyExporter()
    export_bibtex = ExportBibtex(store=store, exporter=exporter)
    output_path = tmp_path / "references.bib"

    result = export_bibtex.execute(output_path)

    assert result.entry_count == 2
    assert set(result.keys) == {"hochreiter-1997", "otro-2020"}
    assert output_path.exists()
    text = output_path.read_text(encoding="utf-8")
    assert "@article{hochreiter-1997," in text
    assert "@techreport{otro-2020," in text


def test_export_bibtex_empty_catalog(tmp_path: Path) -> None:
    store = InMemoryDocumentStore()
    exporter = RecordingBibliographyExporter()
    export_bibtex = ExportBibtex(store=store, exporter=exporter)
    result = export_bibtex.execute(tmp_path / "references.bib")
    assert result.entry_count == 0
    assert result.keys == ()
