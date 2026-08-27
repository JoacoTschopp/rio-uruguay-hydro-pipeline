"""`YamlCatalog` (Fase 7, docs/rio_search_plan.md §3.10: "`rio_search/research/catalog/<slug>.yaml`").
Un archivo YAML por documento -- legible y diffable en git (§3.10: "persistencia versionable y
legible... el repo es la base, sin base de datos"). Usa `pyyaml` (ya dependencia del backend,
`configs/experiments/*.yaml`); Polars no aplica aca (no es tabular, Decision #9 no lo pide).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from rio_search.domain.research.document import Document
from rio_search.domain.research.document_type import DocumentType
from rio_search.domain.research.tag import Tag


class YamlCatalog:
    def __init__(self, catalog_dir: Path) -> None:
        self._dir = catalog_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        return self._dir / f"{slug}.yaml"

    def save(self, document: Document) -> None:
        payload = _to_dict(document)
        self._path(document.slug).write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    def load(self, slug: str) -> Document | None:
        path = self._path(slug)
        if not path.is_file():
            return None
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return _from_dict(payload)

    def list_all(self) -> tuple[Document, ...]:
        documents = []
        for path in sorted(self._dir.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if payload:
                documents.append(_from_dict(payload))
        return tuple(documents)


def _to_dict(document: Document) -> dict:
    return {
        "slug": document.slug,
        "title": document.title,
        "authors": list(document.authors),
        "year": document.year,
        "type": document.type.value,
        "venue": document.venue,
        "doi_url": document.doi_url,
        "tags": [t.value for t in document.tags],
        "file": document.file,
        "added_at": document.added_at,
    }


def _from_dict(payload: dict) -> Document:
    return Document(
        slug=payload["slug"],
        title=payload["title"],
        authors=tuple(payload.get("authors") or ()),
        year=int(payload["year"]),
        type=DocumentType(payload["type"]),
        venue=payload.get("venue"),
        doi_url=payload.get("doi_url"),
        tags=tuple(Tag(t) for t in (payload.get("tags") or ())),
        file=payload.get("file"),
        added_at=payload.get("added_at", ""),
    )
