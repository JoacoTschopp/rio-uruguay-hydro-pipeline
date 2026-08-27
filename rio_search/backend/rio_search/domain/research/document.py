"""`Document`: agregado raiz del contexto Research (docs/rio_search_plan.md §3.2, §3.10).

Invariante que protege (§3.2): "Todo documento tiene `BibEntry` valida antes de exportarse a
`references.bib`" -- `to_bib_entry()` es la unica forma de obtener una `BibEntry` a partir de un
`Document`, y falla explicitamente (no con un `.bib` corrupto) si falta algo que BibTeX necesita.

Campos (§3.10): `slug`, `title`, `authors`, `year`, `venue`, `doi_url`, `type`, `tags`, `file`
(ruta relativa en `rio_search/research/documents/`, o `None` si todavia no se subio un PDF),
`added_at`. Sin dependencias del proyecto (regla de `domain`): quien lo persiste es
`infrastructure.research.filesystem_document_store.FileSystemDocumentStore` (+ `yaml_catalog`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rio_search.domain.research.bib_entry import BibEntry
from rio_search.domain.research.document_type import DocumentType
from rio_search.domain.research.tag import Tag

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def slugify(title: str, year: int | None = None) -> str:
    """Genera un slug a partir del titulo (y opcionalmente el anio) cuando el usuario no da uno
    explicito (§3.10, README de `research/`: "convencion de slugs"). Determinista y solo depende
    de sus argumentos -- no toca el catalogo (la unicidad la valida
    `application.research.add_document.AddDocument` contra el `DocumentStore`)."""
    base = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    if not base:
        raise ValueError(f"no se pudo derivar un slug del titulo {title!r}")
    if year is not None:
        base = f"{base}-{year}"
    return base


@dataclass(frozen=True, slots=True)
class Document:
    slug: str
    title: str
    authors: tuple[str, ...]
    year: int
    type: DocumentType
    venue: str | None = None
    doi_url: str | None = None
    tags: tuple[Tag, ...] = ()
    file: str | None = None
    added_at: str = ""  # ISO 8601 UTC, fijado por AddDocument

    def __post_init__(self) -> None:
        if not _SLUG_RE.match(self.slug):
            raise ValueError(
                f"slug invalido {self.slug!r}: solo minusculas, digitos, '-'/'_', "
                "empezando por minuscula o digito"
            )
        if not self.title.strip():
            raise ValueError(f"Document {self.slug!r}: title no puede ser vacio")
        if not self.authors:
            raise ValueError(f"Document {self.slug!r}: authors no puede ser vacio")
        if self.year <= 0:
            raise ValueError(f"Document {self.slug!r}: year invalido ({self.year!r})")

    def with_tags(self, tags: tuple[Tag, ...]) -> "Document":
        """Nuevo `Document` (frozen) con los tags reemplazados -- usado por
        `application.research.tag_document.TagDocument`."""
        return Document(
            slug=self.slug,
            title=self.title,
            authors=self.authors,
            year=self.year,
            type=self.type,
            venue=self.venue,
            doi_url=self.doi_url,
            tags=tags,
            file=self.file,
            added_at=self.added_at,
        )

    def with_file(self, file: str) -> "Document":
        """Nuevo `Document` con `file` fijado tras subir el PDF (§3.10)."""
        return Document(
            slug=self.slug,
            title=self.title,
            authors=self.authors,
            year=self.year,
            type=self.type,
            venue=self.venue,
            doi_url=self.doi_url,
            tags=self.tags,
            file=file,
            added_at=self.added_at,
        )

    def to_bib_entry(self) -> BibEntry:
        """`BibEntry` valida (invariante del agregado, §3.2) -- las validaciones de campos
        obligatorios ya las hace `BibEntry.__post_init__`, esto solo traduce la forma."""
        return BibEntry(
            key=self.slug,
            entry_type=self.type.bibtex_entry_type,
            title=self.title,
            authors=self.authors,
            year=self.year,
            venue=self.venue,
            doi_url=self.doi_url,
        )
