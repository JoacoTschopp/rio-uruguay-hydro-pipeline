"""Catálogo `research/catalog/*.yaml` → `manuscritos/comun/referencias.bib`.

    uv run --no-project --with pyyaml python manuscritos/herramientas/exportar_bib.py

La fuente de la bibliografía es la biblioteca compartida `research/catalog/` (no se duplica acá).
Este script escribe un `.bib` propio de los manuscritos para no regenerar
`thesis/common/references.bib`, que pertenece a la herramienta de `research/` y se regenera
desde otras ramas: así un merge nunca choca en un archivo generado.

La forma de cada entrada la da `research/export_bib.py::entrada` (se importa, no se copia).
Solo cambian dos cosas, por precaución con el `bibtex` clásico de MiKTeX:

* la cabecera va en ASCII puro. La Decisión 049 de `feature/rio-search` registró que un `§` antes
  de la primera entrada hacía leer 0 entradas. Con la cabecera actual de `research/export_bib.py`
  no se reprodujo (probado el 2026-09-16), pero no cuesta nada evitarlo;
* los saltos de línea son LF.

El `.bib` generado **no se edita a mano**.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CATALOGO = RAIZ / "research" / "catalog"
SALIDA = RAIZ / "manuscritos" / "comun" / "referencias.bib"


def _cargar_entrada():
    ruta = RAIZ / "research" / "export_bib.py"
    spec = importlib.util.spec_from_file_location("research_export_bib", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.entrada


def main() -> int:
    entrada = _cargar_entrada()
    docs, sin_verificar = [], []
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
        "% Generado por manuscritos/herramientas/exportar_bib.py -- NO EDITAR A MANO.\n"
        "% Fuente: research/catalog/*.yaml. Una entrada por documento, clave = slug.\n"
        f"% {len(docs)} entradas.\n\n"
    )
    assert cabecera.isascii()
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA.open("w", encoding="utf-8", newline="\n") as f:
        f.write(cabecera + "\n\n".join(entrada(d) for d in docs) + "\n")

    print(f"  {len(docs)} entradas -> {SALIDA.relative_to(RAIZ).as_posix()}")
    if sin_verificar:
        print(f"  ATENCION, sin verificar contra la fuente: {', '.join(sin_verificar)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
