"""Catálogo YAML → `thesis/common/references.bib`.

    .venv/Scripts/python.exe research/export_bib.py

Exportador provisorio: la Fase 7 de `docs/rio_search_plan.md` lo reemplaza por el
`BibtexExporter` de la app. Mientras tanto hace lo único que hace falta — una entrada
BibTeX por documento del catálogo, con la clave = `slug`, para que la tesis pueda citar
con `\\cite{slug}` desde ya.

El `.bib` generado **no se edita a mano**: se regenera.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = RAIZ / "research" / "catalog"
SALIDA = RAIZ / "thesis" / "common" / "references.bib"

#: Campos del YAML que van al .bib, en el orden en que se escriben.
CAMPOS = ("title", "author", "journal", "volume", "number", "pages", "year", "doi", "url")


def _escapar(valor: str) -> str:
    """Protege las mayúsculas de un título con llaves.

    BibTeX baja a minúscula los títulos según el estilo, y eso rompe siglas y nombres
    propios: `NSE` quedaría `nse` y `Uruguay` quedaría `uruguay`. Envolver el título
    entero en llaves lo deja tal cual está escrito.
    """
    return valor.replace("&", r"\&").replace("_", r"\_")


def entrada(doc: dict) -> str:
    campos = {
        "title": "{%s}" % _escapar(str(doc["title"]).strip()),
        "author": _escapar(" and ".join(doc["authors"])),
        "journal": _escapar(str(doc.get("venue", ""))),
        "volume": doc.get("volume"),
        "number": doc.get("number"),
        "pages": doc.get("pages"),
        "year": doc.get("year"),
        "doi": doc.get("doi"),
        "url": doc.get("url"),
    }
    lineas = [f"@{doc.get('bibtype', 'article')}{{{doc['slug']},"]
    for k in CAMPOS:
        v = campos.get(k)
        if v not in (None, ""):
            lineas.append(f"  {k:8s} = {{{v}}},")
    lineas.append("}")
    return "\n".join(lineas)


def main() -> int:
    docs = []
    sin_verificar = []
    for ruta in sorted(CATALOGO.glob("*.yaml")):
        doc = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        faltan = [c for c in ("slug", "title", "authors", "year") if not doc.get(c)]
        if faltan:
            print(f"  ERROR {ruta.name}: faltan {faltan}", file=sys.stderr)
            return 1
        if doc["slug"] != ruta.stem:
            print(f"  ERROR {ruta.name}: slug '{doc['slug']}' != nombre de archivo",
                  file=sys.stderr)
            return 1
        if not doc.get("verificado"):
            sin_verificar.append(doc["slug"])
        docs.append(doc)

    cabecera = (
        "% Generado por research/export_bib.py — NO EDITAR A MANO.\n"
        "% Fuente: research/catalog/*.yaml   ·   una entrada por documento, clave = slug.\n"
        f"% {len(docs)} entradas.\n\n"
    )
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(cabecera + "\n\n".join(entrada(d) for d in docs) + "\n",
                      encoding="utf-8")

    print(f"  {len(docs)} entradas → {SALIDA.relative_to(RAIZ)}")
    if sin_verificar:
        # No es un error: es una deuda que hay que saldar antes de la defensa.
        print(f"  ATENCIÓN, sin verificar contra la fuente: {', '.join(sin_verificar)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
