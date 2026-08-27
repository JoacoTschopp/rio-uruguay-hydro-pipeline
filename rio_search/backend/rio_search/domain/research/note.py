"""`Note`: notas de lectura de un `Document`, por seccion fija (docs/rio_search_plan.md §3.10):
"por seccion -- metodologia, modelos, ventanas/splits, metricas, resultados, que me llevo -- en
Markdown, con `links` a `Decision NNN` y a `run_id` de MLflow". Sin dependencias del proyecto
(regla de `domain`): `to_markdown`/`from_markdown` son el (de)serializador hacia
`rio_search/research/notes/<slug>.md` (§3.10: "persistencia versionable y legible"), usado por
`infrastructure.research.filesystem_document_store.FileSystemDocumentStore` -- viven aca y no en
`infrastructure` porque son texto puro (sin I/O, sin dependencias externas), la misma regla que ya
sigue `Forecast.as_tags()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rio_search.domain.research.link import Link

# Claves en ingles (convencion del repo, §7: "codigo en ingles"); las etiquetas visibles en el
# Markdown (y en la UI) son las del plan, en espanol.
SECTION_ORDER: tuple[str, ...] = (
    "methodology",
    "models",
    "windows_splits",
    "metrics",
    "results",
    "takeaways",
)

SECTION_LABELS: dict[str, str] = {
    "methodology": "Metodología",
    "models": "Modelos",
    "windows_splits": "Ventanas / splits",
    "metrics": "Métricas",
    "results": "Resultados",
    "takeaways": "Qué me llevo",
}

_LABEL_TO_KEY = {label: key for key, label in SECTION_LABELS.items()}
_LINKS_HEADER = "Enlaces"
_EMPTY_PLACEHOLDER = "_(sin notas todavía)_"


@dataclass(frozen=True, slots=True)
class Note:
    slug: str
    sections: dict[str, str] = field(default_factory=dict)
    links: tuple[Link, ...] = ()

    def __post_init__(self) -> None:
        if not self.slug.strip():
            raise ValueError("Note.slug no puede ser vacio")
        unknown = set(self.sections) - set(SECTION_ORDER)
        if unknown:
            raise ValueError(f"Note {self.slug!r}: secciones desconocidas {sorted(unknown)}")

    def section(self, key: str) -> str:
        if key not in SECTION_ORDER:
            raise KeyError(f"seccion desconocida {key!r}; validas: {SECTION_ORDER}")
        return self.sections.get(key, "")

    @staticmethod
    def empty(slug: str) -> "Note":
        return Note(slug=slug, sections={}, links=())

    def to_markdown(self, title: str) -> str:
        lines = [f"# {title}", ""]
        for key in SECTION_ORDER:
            content = self.sections.get(key, "").strip()
            lines.append(f"## {SECTION_LABELS[key]}")
            lines.append("")
            lines.append(content if content else _EMPTY_PLACEHOLDER)
            lines.append("")
        lines.append(f"## {_LINKS_HEADER}")
        lines.append("")
        if self.links:
            for link in self.links:
                lines.append(link.to_markdown_line())
        else:
            lines.append(_EMPTY_PLACEHOLDER)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def from_markdown(slug: str, text: str) -> "Note":
        """Inverso de `to_markdown` (round-trip exacto para texto producido por esta clase; texto
        editado a mano por el usuario que respete los encabezados `## <Seccion>` tambien se lee
        bien, linea por linea, sin exigir el resto del formato)."""
        sections: dict[str, str] = {}
        links: list[Link] = []
        current_key: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            nonlocal current_lines
            if current_key is None:
                current_lines = []
                return
            body = "\n".join(current_lines).strip()
            if body and body != _EMPTY_PLACEHOLDER:
                if current_key == "__links__":
                    for line in body.splitlines():
                        parsed = Link.parse_markdown_line(line)
                        if parsed is not None:
                            links.append(parsed)
                else:
                    sections[current_key] = body
            current_lines = []

        for raw_line in text.splitlines():
            if raw_line.startswith("## "):
                flush()
                label = raw_line[3:].strip()
                if label == _LINKS_HEADER:
                    current_key = "__links__"
                else:
                    current_key = _LABEL_TO_KEY.get(label)
            elif raw_line.startswith("# "):
                continue
            else:
                current_lines.append(raw_line)
        flush()

        return Note(slug=slug, sections=sections, links=tuple(links))
