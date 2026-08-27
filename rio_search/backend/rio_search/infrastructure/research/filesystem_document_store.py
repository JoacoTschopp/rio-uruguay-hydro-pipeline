"""`FileSystemDocumentStore` (Fase 7, docs/rio_search_plan.md §3.10): implementa
`application.ports.document_store.DocumentStorePort` sobre tres carpetas del repo --
`research/catalog/*.yaml` (via `YamlCatalog`), `research/notes/*.md` (texto plano, `Note.
to_markdown`/`from_markdown`) y `research/documents/*` (PDFs, gitignored). Sin base de datos: el
repo es la base (§3.10).
"""

from __future__ import annotations

from pathlib import Path

from rio_search.domain.research.document import Document
from rio_search.domain.research.note import Note
from rio_search.infrastructure.research.yaml_catalog import YamlCatalog

# Extensiones que se aceptan para el material subido -- PDF es lo esperado (§3.10: "subir PDF"),
# pero no hay motivo de dominio para rechazar un `.txt`/`.md` de notas sueltas u otro material de
# referencia liviano; se valida solo para evitar subir algo claramente equivocado por accidente.
_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}


class FileSystemDocumentStore:
    def __init__(self, catalog_dir: Path, notes_dir: Path, documents_dir: Path) -> None:
        self._catalog = YamlCatalog(catalog_dir)
        self._notes_dir = notes_dir
        self._documents_dir = documents_dir
        self._notes_dir.mkdir(parents=True, exist_ok=True)
        self._documents_dir.mkdir(parents=True, exist_ok=True)

    # -- Document (catalog/*.yaml) -----------------------------------------------------------
    def save_document(self, document: Document) -> None:
        self._catalog.save(document)

    def get_document(self, slug: str) -> Document | None:
        return self._catalog.load(slug)

    def list_documents(self) -> tuple[Document, ...]:
        return self._catalog.list_all()

    # -- Note (notes/*.md) ---------------------------------------------------------------------
    def _note_path(self, slug: str) -> Path:
        return self._notes_dir / f"{slug}.md"

    def save_note(self, note: Note, title: str) -> None:
        self._note_path(note.slug).write_text(note.to_markdown(title), encoding="utf-8")

    def get_note(self, slug: str) -> Note | None:
        path = self._note_path(slug)
        if not path.is_file():
            return None
        return Note.from_markdown(slug, path.read_text(encoding="utf-8"))

    # -- Archivo (documents/*) -----------------------------------------------------------------
    def save_file(self, slug: str, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower() or ".pdf"
        if suffix not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                f"extension {suffix!r} no permitida para {filename!r}; validas: "
                f"{sorted(_ALLOWED_EXTENSIONS)}"
            )
        target = self._documents_dir / f"{slug}{suffix}"
        target.write_bytes(content)
        # Ruta relativa a `rio_search/research/` (Document.file, §3.10) -- no la ruta absoluta de
        # esta maquina, para que el YAML del catalogo sea portable entre clones del repo.
        return f"documents/{target.name}"

    def read_file(self, slug: str) -> tuple[bytes, str] | None:
        for candidate in self._documents_dir.glob(f"{slug}.*"):
            if candidate.is_file():
                return candidate.read_bytes(), candidate.name
        return None
