"""`BibEntry` (docs/rio_search_plan.md §3.10): "Todo documento tiene `BibEntry` valida antes de
exportarse a `references.bib`" -- "`ExportBibtex` escribe ... una entrada por documento, clave =
`slug`. La tesis cita con `\\cite{slug}`". Sin dependencias del proyecto (regla de `domain`): quien
la construye es `Document.to_bib_entry()`, quien la escribe a disco es
`infrastructure.research.bibtex_exporter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BibEntry:
    key: str  # = Document.slug (§3.10)
    entry_type: str  # article | phdthesis | techreport | misc (DocumentType.bibtex_entry_type)
    title: str
    authors: tuple[str, ...]
    year: int
    venue: str | None = None
    doi_url: str | None = None
    note: str | None = None
    extra_fields: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("BibEntry.key (slug) no puede ser vacio")
        if not self.title.strip():
            raise ValueError(f"BibEntry {self.key!r}: title no puede ser vacio")
        if not self.authors:
            raise ValueError(f"BibEntry {self.key!r}: authors no puede ser vacio")
        if self.year <= 0:
            raise ValueError(f"BibEntry {self.key!r}: year invalido ({self.year!r})")

    def _venue_field(self) -> tuple[str, str] | None:
        """El nombre del campo BibTeX para `venue` depende del tipo de entrada: `journal` para un
        articulo, `booktitle` para unas actas de congreso, `school` para una tesis, `institution`
        para un informe tecnico. Sin `venue` (misc/plantilla) no se agrega el campo."""
        if not self.venue:
            return None
        by_type = {
            "article": "journal",
            "inproceedings": "booktitle",
            "phdthesis": "school",
            "mastersthesis": "school",
            "techreport": "institution",
        }
        return by_type.get(self.entry_type, "howpublished"), self.venue

    def to_bibtex(self) -> str:
        """Formato BibTeX estandar, un campo por linea, orden estable (facilita el diff en git de
        `references.bib`, versionado, §3.10)."""
        author_field = " and ".join(self.authors)
        fields: list[tuple[str, str]] = [
            ("title", self.title),
            ("author", author_field),
            ("year", str(self.year)),
        ]
        venue_field = self._venue_field()
        if venue_field is not None:
            fields.append(venue_field)
        if self.doi_url:
            fields.append(("url", self.doi_url))
        if self.note:
            fields.append(("note", self.note))
        for name, value in self.extra_fields.items():
            fields.append((name, value))

        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
        return f"@{self.entry_type}{{{self.key},\n{body}\n}}"
