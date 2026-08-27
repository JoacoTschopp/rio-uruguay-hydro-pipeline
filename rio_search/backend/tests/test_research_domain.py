"""Tests offline del dominio Research (Fase 7, docs/rio_search_plan.md §3.10): `Tag`, `Document`,
`slugify`, `Link`, `BibEntry`, `Note` (incluido el round-trip Markdown)."""

from __future__ import annotations

import pytest

from rio_search.domain.research.bib_entry import BibEntry
from rio_search.domain.research.document import Document, slugify
from rio_search.domain.research.document_type import DocumentType
from rio_search.domain.research.link import Link, LinkKind
from rio_search.domain.research.note import Note
from rio_search.domain.research.tag import Tag


def test_tag_normalizes_case_and_whitespace() -> None:
    assert Tag("  LSTM ").value == "lstm"


def test_tag_rejects_empty() -> None:
    with pytest.raises(ValueError):
        Tag("   ")


def test_tag_parse_many_dedupes_preserving_order() -> None:
    tags = Tag.parse_many("lstm, hidrologia , LSTM, caudal")
    assert [t.value for t in tags] == ["lstm", "hidrologia", "caudal"]


def test_slugify_basic() -> None:
    assert slugify("Long Short-Term Memory Networks", 2015) == "long-short-term-memory-networks-2015"


def test_slugify_without_year() -> None:
    assert slugify("LSTM: A Search Space Odyssey") == "lstm-a-search-space-odyssey"


def _sample_document(**overrides) -> Document:
    kwargs = dict(
        slug="hochreiter-1997-lstm",
        title="Long Short-Term Memory",
        authors=("Hochreiter, S.", "Schmidhuber, J."),
        year=1997,
        type=DocumentType.PAPER,
        venue="Neural Computation",
        doi_url="https://doi.org/10.1162/neco.1997.9.8.1735",
        tags=(Tag("lstm"), Tag("deep-learning")),
    )
    kwargs.update(overrides)
    return Document(**kwargs)


def test_document_rejects_invalid_slug() -> None:
    with pytest.raises(ValueError):
        _sample_document(slug="Not A Valid Slug!")


def test_document_rejects_empty_authors() -> None:
    with pytest.raises(ValueError):
        _sample_document(authors=())


def test_document_with_tags_returns_new_instance() -> None:
    doc = _sample_document()
    updated = doc.with_tags((Tag("nuevo"),))
    assert doc.tags == (Tag("lstm"), Tag("deep-learning"))
    assert updated.tags == (Tag("nuevo"),)
    assert updated.slug == doc.slug


def test_document_with_file_returns_new_instance() -> None:
    doc = _sample_document()
    updated = doc.with_file("documents/hochreiter-1997-lstm.pdf")
    assert doc.file is None
    assert updated.file == "documents/hochreiter-1997-lstm.pdf"


def test_document_to_bib_entry() -> None:
    entry = _sample_document().to_bib_entry()
    assert isinstance(entry, BibEntry)
    assert entry.key == "hochreiter-1997-lstm"
    assert entry.entry_type == "article"
    assert entry.year == 1997


def test_bib_entry_requires_authors() -> None:
    with pytest.raises(ValueError):
        BibEntry(key="x", entry_type="article", title="t", authors=(), year=2020)


def test_bib_entry_to_bibtex_contains_key_and_fields() -> None:
    entry = BibEntry(
        key="hochreiter-1997-lstm",
        entry_type="article",
        title="Long Short-Term Memory",
        authors=("Hochreiter, S.", "Schmidhuber, J."),
        year=1997,
        venue="Neural Computation",
        doi_url="https://doi.org/10.1162/neco.1997.9.8.1735",
    )
    text = entry.to_bibtex()
    assert text.startswith("@article{hochreiter-1997-lstm,")
    assert "title = {Long Short-Term Memory}" in text
    assert "author = {Hochreiter, S. and Schmidhuber, J.}" in text
    assert "year = {1997}" in text
    assert "journal = {Neural Computation}" in text
    assert "url = {https://doi.org/10.1162/neco.1997.9.8.1735}" in text


def test_bib_entry_venue_field_by_entry_type() -> None:
    thesis = BibEntry(
        key="k", entry_type="phdthesis", title="t", authors=("A",), year=2020, venue="UBA"
    )
    assert "school = {UBA}" in thesis.to_bibtex()

    report = BibEntry(
        key="k2", entry_type="techreport", title="t", authors=("A",), year=2020, venue="INA"
    )
    assert "institution = {INA}" in report.to_bibtex()


def test_link_to_decision_zero_pads() -> None:
    link = Link.to_decision(41)
    assert link.kind is LinkKind.DECISION
    assert link.ref == "041"


def test_link_decision_requires_numeric_ref() -> None:
    with pytest.raises(ValueError):
        Link(kind=LinkKind.DECISION, ref="not-a-number")


def test_link_markdown_round_trip() -> None:
    decision = Link.to_decision(41)
    run = Link.to_run("bilstm-v9")
    assert Link.parse_markdown_line(decision.to_markdown_line()) == decision
    assert Link.parse_markdown_line(run.to_markdown_line()) == run


def test_link_parse_markdown_line_ignores_free_text() -> None:
    assert Link.parse_markdown_line("- esto es texto libre del usuario") is None


def test_note_empty_has_no_sections_or_links() -> None:
    note = Note.empty("slug-x")
    assert note.section("methodology") == ""
    assert note.links == ()


def test_note_rejects_unknown_section() -> None:
    with pytest.raises(ValueError):
        Note(slug="x", sections={"not_a_real_section": "..."})


def test_note_to_markdown_contains_all_section_labels() -> None:
    note = Note(slug="x", sections={"methodology": "Se usa BiLSTM."}, links=(Link.to_decision(41),))
    md = note.to_markdown("Título del documento")
    assert "# Título del documento" in md
    assert "## Metodología" in md
    assert "Se usa BiLSTM." in md
    assert "## Modelos" in md
    assert "## Enlaces" in md
    assert "Decisión 041" in md


def test_note_markdown_round_trip() -> None:
    original = Note(
        slug="x",
        sections={
            "methodology": "Ventana rolling_365, embargo 14 días.",
            "results": "BiLSTM supera persistencia en 7/8 horizontes.",
        },
        links=(Link.to_decision(41), Link.to_run("bilstm-v9")),
    )
    md = original.to_markdown("Título")
    restored = Note.from_markdown("x", md)
    assert restored.section("methodology") == original.section("methodology")
    assert restored.section("results") == original.section("results")
    assert restored.section("models") == ""
    assert restored.links == original.links


def test_note_from_markdown_ignores_placeholder_sections() -> None:
    note = Note.empty("x")
    md = note.to_markdown("Título")
    restored = Note.from_markdown("x", md)
    assert restored.sections == {}
    assert restored.links == ()
