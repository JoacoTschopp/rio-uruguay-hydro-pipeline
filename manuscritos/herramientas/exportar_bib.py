"""Catálogo `research/catalog/*.yaml` → `manuscritos/comun/referencias.bib`.

    uv run --no-project --with pyyaml python manuscritos/herramientas/exportar_bib.py

La fuente de la bibliografía es la biblioteca compartida `research/catalog/` (no se duplica acá).
Este script escribe un `.bib` propio de los manuscritos para no regenerar
`thesis/common/references.bib`, que pertenece a la herramienta de `research/` y se regenera
desde otras ramas: así un merge nunca choca en un archivo generado.

La forma de cada entrada la da `research/export_bib.py::entrada` (se importa, no se copia).
Solo cambian tres cosas, por precaución con el `bibtex` clásico de MiKTeX y con babel:

* la cabecera va en ASCII puro. La Decisión 049 de `feature/rio-search` registró que un `§` antes
  de la primera entrada hacía leer 0 entradas. Con la cabecera actual de `research/export_bib.py`
  no se reprodujo (probado el 2026-09-16), pero no cuesta nada evitarlo;
* los saltos de línea son LF;
* las comillas rectas se convierten a comillas tipográficas (ver `_comillas`);
* el `venue` cambia de campo según el tipo de entrada (ver `_venue`);
* los caracteres no ASCII del campo `author` pasan a comandos de acento (ver `_autores`).

Las tres son limitaciones reales del `bibtex` 0.99 + `apacite` + `babel`, verificadas compilando.

El `.bib` generado **no se edita a mano**.
"""

from __future__ import annotations

import importlib.util
import sys
import unicodedata
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CATALOGO = RAIZ / "research" / "catalog"
SALIDA = RAIZ / "manuscritos" / "comun" / "referencias.bib"


def _comillas(texto: str) -> str:
    """Reemplaza las comillas rectas por comillas tipográficas de LaTeX.

    `babel` con la opción `spanish` hace activo el carácter `"` para sus atajos (`"a`, `"u`,
    `"-`...). Un título como `Smart "Predict, then Optimize"` llega al `.bbl` con las comillas
    rectas y pdflatex muere con

        ! Argument of \\language@active@arg" has an extra }.

    Se convierten a `` y '' , que es la forma de escribirlas en LaTeX y la que usa el estilo.
    Las comillas van de a pares: la de apertura es la de índice par.
    """
    partes = texto.split('"')
    if len(partes) == 1:
        return texto
    salida = partes[0]
    for i, parte in enumerate(partes[1:]):
        salida += ("``" if i % 2 == 0 else "''") + parte
    return salida


#: Marca combinante Unicode -> comando de acento de LaTeX.
_ACENTOS = {
    "̀": "`", "́": "'", "̂": "^", "̃": "~", "̄": "=",
    "̆": "u", "̇": ".", "̈": '"', "̊": "r", "̋": "H",
    "̌": "v", "̧": "c", "̨": "k", "̱": "b",
}

#: Caracteres que no se descomponen en base + acento.
_ESPECIALES = {
    "ı": r"\i", "ȷ": r"\j", "ł": r"\l", "Ł": r"\L",
    "ø": r"\o", "Ø": r"\O", "ß": r"\ss",
    "æ": r"\ae", "Æ": r"\AE", "œ": r"\oe", "Œ": r"\OE",
    "đ": r"\dj", "Đ": r"\DJ",
}

_sin_mapear: set[str] = set()


def _a_latex(c: str) -> str:
    if c.isascii():
        return c
    descompuesto = unicodedata.normalize("NFD", c)
    if len(descompuesto) == 2 and descompuesto[1] in _ACENTOS:
        base, marca = descompuesto
        base = _ESPECIALES.get(base, base)
        return "{\\%s%s}" % (_ACENTOS[marca], base)
    if c in _ESPECIALES:
        return "{%s}" % _ESPECIALES[c]
    _sin_mapear.add(c)
    return c


def _autores(texto: str) -> str:
    """Pasa los caracteres no ASCII del campo `author` a comandos de acento de LaTeX.

    `bibtex` 0.99 trabaja a nivel de byte, no de carácter. Al abreviar un nombre de pila se queda
    con el primer byte, y si ese byte abre una secuencia UTF-8 multibyte, el `.bbl` sale con media
    secuencia y pdflatex muere con

        ! LaTeX Error: Invalid UTF-8 byte sequence.

    Pasó con `Arık, Sercan Ö.` de `lim-2021-tft`, que apacite abrevia a `Ö.`. Encerrarlo en llaves
    NO alcanza: `bibtex` sólo trata un grupo como carácter atómico si empieza con un comando, o
    sea `{\\"O}`. Verificado compilando: con `{Ö}` falla igual, con `{\\"O}` sale bien.

    Sólo se toca `author`: es el único campo que el estilo abrevia.
    """
    salida = []
    for linea in texto.split("\n"):
        if linea.startswith("  author  "):
            linea = "".join(_a_latex(c) for c in linea)
        salida.append(linea)
    return "\n".join(salida)


#: Adonde va el `venue` del catalogo segun el tipo de entrada. `research/export_bib.py::entrada`
#: siempre lo escribe como `journal`, que es correcto para un articulo de revista y erroneo para
#: los demas: apacite ignora `journal` en @inproceedings y @techreport, y la referencia sale sin
#: el nombre del congreso o del organismo.
_CAMPO_VENUE = {
    "inproceedings": "booktitle",
    "incollection": "booktitle",
    "conference": "booktitle",
    "techreport": "institution",
    "misc": "howpublished",
}


def _venue(texto: str, bibtype: str) -> str:
    """Mueve el `venue` al campo que corresponde al tipo de entrada.

    En `booktitle` va ademas entre llaves dobles: apacite escribe el nombre del congreso en
    minusculas y sin las llaves sale "Xxiv simposio brasileiro de recursos hidricos".
    """
    campo = _CAMPO_VENUE.get(bibtype)
    if campo is None:
        return texto
    salida = []
    for linea in texto.split("\n"):
        if linea.startswith("  journal  = {"):
            valor = linea[len("  journal  = {"):].rstrip(",").rstrip("}")
            if campo == "booktitle":
                valor = "{%s}" % valor
            linea = f"  {campo:8s} = {{{valor}}},"
        salida.append(linea)
    return "\n".join(salida)


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
    cuerpo = "\n\n".join(
        _autores(_venue(_comillas(entrada(d)), d.get("bibtype", "article"))) for d in docs
    )
    with SALIDA.open("w", encoding="utf-8", newline="\n") as f:
        f.write(cabecera + cuerpo + "\n")

    print(f"  {len(docs)} entradas -> {SALIDA.relative_to(RAIZ).as_posix()}")
    if sin_verificar:
        print(f"  ATENCION, sin verificar contra la fuente: {', '.join(sin_verificar)}")
    if _sin_mapear:
        # Un caracter no ASCII sin equivalente LaTeX en un autor es una bomba de tiempo:
        # bibtex lo va a partir si le toca abreviar ese nombre.
        print(f"  ATENCION, caracteres de autor sin mapear: {', '.join(sorted(_sin_mapear))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
