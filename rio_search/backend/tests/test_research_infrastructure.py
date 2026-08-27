"""Tests offline de `infrastructure/research/*` (Fase 7): `YamlCatalog`,
`FileSystemDocumentStore`, `FileBibtexExporter` -- todos sobre `tmp_path`, sin tocar el repo
real."""

from __future__ import annotations

from pathlib import Path

from rio_search.domain.research.bib_entry import BibEntry
from rio_search.domain.research.document import Document
from rio_search.domain.research.document_type import DocumentType
from rio_search.domain.research.link import Link
from rio_search.domain.research.note import Note
from rio_search.domain.research.tag import Tag
from rio_search.infrastructure.research.bibtex_exporter import FileBibtexExporter
from rio_search.infrastructure.research.filesystem_document_store import FileSystemDocumentStore
from rio_search.infrastructure.research.yaml_catalog import YamlCatalog


def _document(**overrides) -> Document:
    kwargs = dict(
        slug="hochreiter-1997-lstm",
        title="Long Short-Term Memory",
        authors=("Hochreiter, S.", "Schmidhuber, J."),
        year=1997,
        type=DocumentType.PAPER,
        venue="Neural Computation",
        doi_url="https://doi.org/10.1162/neco.1997.9.8.1735",
        tags=(Tag("lstm"), Tag("deep-learning")),
        added_at="2026-08-27T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return Document(**kwargs)


# ---------------------------------------------------------------------- YamlCatalog


def test_yaml_catalog_round_trip(tmp_path: Path) -> None:
    catalog = YamlCatalog(tmp_path / "catalog")
    document = _document()
    catalog.save(document)

    loaded = catalog.load(document.slug)
    assert loaded == document


def test_yaml_catalog_load_missing_returns_none(tmp_path: Path) -> None:
    catalog = YamlCatalog(tmp_path / "catalog")
    assert catalog.load("no-existe") is None


def test_yaml_catalog_writes_readable_yaml_file(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "catalog"
    catalog = YamlCatalog(catalog_dir)
    catalog.save(_document())
    path = catalog_dir / "hochreiter-1997-lstm.yaml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "title:" in text
    assert "Hochreiter" in text


def test_yaml_catalog_list_all_sorted_by_slug(tmp_path: Path) -> None:
    catalog = YamlCatalog(tmp_path / "catalog")
    catalog.save(_document(slug="zzz-doc", title="Z"))
    catalog.save(_document(slug="aaa-doc", title="A"))
    slugs = [d.slug for d in catalog.list_all()]
    assert slugs == ["aaa-doc", "zzz-doc"]


# ---------------------------------------------------------------------- FileSystemDocumentStore


def _store(tmp_path: Path) -> FileSystemDocumentStore:
    return FileSystemDocumentStore(
        catalog_dir=tmp_path / "catalog",
        notes_dir=tmp_path / "notes",
        documents_dir=tmp_path / "documents",
    )


def test_filesystem_store_document_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    document = _document()
    store.save_document(document)
    assert store.get_document(document.slug) == document
    assert store.list_documents() == (document,)


def test_filesystem_store_note_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    note = Note(
        slug="hochreiter-1997-lstm",
        sections={"methodology": "Puertas de entrada/olvido/salida."},
        links=(Link.to_decision(41),),
    )
    store.save_note(note, title="Long Short-Term Memory")

    loaded = store.get_note("hochreiter-1997-lstm")
    assert loaded.section("methodology") == "Puertas de entrada/olvido/salida."
    assert loaded.links == (Link.to_decision(41),)

    md_path = tmp_path / "notes" / "hochreiter-1997-lstm.md"
    assert md_path.is_file()
    assert "# Long Short-Term Memory" in md_path.read_text(encoding="utf-8")


def test_filesystem_store_get_note_missing_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.get_note("no-existe") is None


def test_filesystem_store_save_and_read_file(tmp_path: Path) -> None:
    store = _store(tmp_path)
    relative = store.save_file("s1", "paper.pdf", b"%PDF-1.4 contenido")
    assert relative == "documents/s1.pdf"

    content, filename = store.read_file("s1")
    assert content == b"%PDF-1.4 contenido"
    assert filename == "s1.pdf"


def test_filesystem_store_read_file_missing_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.read_file("no-existe") is None


def test_filesystem_store_rejects_disallowed_extension(tmp_path: Path) -> None:
    store = _store(tmp_path)
    import pytest

    with pytest.raises(ValueError):
        store.save_file("s1", "malware.exe", b"x")


# ---------------------------------------------------------------------- FileBibtexExporter


def test_file_bibtex_exporter_writes_sorted_entries(tmp_path: Path) -> None:
    entries = (
        BibEntry(key="zzz", entry_type="article", title="Z", authors=("A",), year=2020),
        BibEntry(key="aaa", entry_type="article", title="A", authors=("A",), year=2020),
    )
    exporter = FileBibtexExporter()
    output_path = tmp_path / "thesis" / "common" / "references.bib"

    result = exporter.write(entries, output_path)

    assert result == output_path
    text = output_path.read_text(encoding="utf-8")
    assert text.index("@article{aaa,") < text.index("@article{zzz,")


def test_file_bibtex_exporter_empty_entries_still_writes_header(tmp_path: Path) -> None:
    exporter = FileBibtexExporter()
    output_path = tmp_path / "references.bib"
    exporter.write((), output_path)
    assert output_path.exists()
