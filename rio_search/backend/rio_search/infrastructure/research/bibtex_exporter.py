"""`FileBibtexExporter` (Fase 7, docs/rio_search_plan.md §3.10): implementa
`application.ports.bibliography_export.BibliographyExportPort`. Formatea cada `BibEntry` con
`BibEntry.to_bibtex()` (dominio, sin dependencias) y escribe `rio_search/thesis/common/
references.bib`, ordenado por `key` (= slug) para que el diff en git sea estable entre
exportaciones sucesivas."""

from __future__ import annotations

from pathlib import Path

from rio_search.domain.research.bib_entry import BibEntry

# ASCII puro a proposito (nunca UTF-8 no-ASCII, ni siquiera en el comentario): el `bibtex` clasico
# (no `bibtex8`/`biber`) que trae MiKTeX no es Unicode-aware -- un byte multi-byte UTF-8 antes del
# primer `@entry` (probado real con "§", 0xC2 0xA7) descoloca su lexer y hace que reporte "0
# entries" sin ningun error visible, aunque el archivo tenga las entradas bien formadas (hallazgo
# real del criterio de cierre de la Fase 7, ver docs/decisions.md). Titulos/autores con acentos
# (que si pueden venir de `Document`) quedan como limitacion conocida, documentada en la Decision
# de cierre de esta fase -- no se resuelve acá (requeriria biber/bibtex8 o escapar a secuencias
# LaTeX, fuera de alcance).
_HEADER = (
    "% Generado por `rio-search research export-bib` (ExportBibtex, docs/rio_search_plan.md "
    "3.10). No editar a mano: correr el comando de nuevo despues de tocar el catalogo en "
    "rio_search/research/catalog/.\n"
)


class FileBibtexExporter:
    def write(self, entries: tuple[BibEntry, ...], output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(entries, key=lambda e: e.key)
        body = "\n\n".join(entry.to_bibtex() for entry in ordered)
        content = _HEADER + ("\n" + body + "\n" if body else "\n")
        # `newline="\n"` a proposito (nunca CRLF): mismo criterio de diff estable que el orden por
        # `key` de arriba, y evita otra fuente de bytes no-ASCII/inusuales antes de las entradas.
        output_path.write_text(content, encoding="utf-8", newline="\n")
        return output_path
