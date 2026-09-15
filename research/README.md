# `research/` — biblioteca de investigación

Los documentos que sostienen las decisiones metodológicas de la tesis, en formato
versionable y legible. Sin base de datos: **el repo es la base**.

Es la Fase 7 de `docs/rio_search_plan.md` §3.10, arrancada por adelantado porque la
función de ganancia (`docs/funcion_ganancia_regimen.html` §09) necesitaba su fundamento
escrito. Cuando la app de Rio_Search implemente el módulo Research, lee de acá sin
cambios: el formato es el que define el plan.

## Estructura

```
research/
  catalog/<slug>.yaml     # metadatos de cada documento — versionado
  notes/<slug>.md         # notas de lectura por sección — versionado
  documents/              # los PDF — FUERA de git
  templates/              # el trabajo con formato validado (lo aporta el usuario, Fase 8)
  export_bib.py           # catálogo → thesis/common/references.bib
```

`documents/` está en `.gitignore`: los PDF no se versionan por licencia. El catálogo sí,
y con el DOI cualquiera recupera el documento.

## Convención de slug

`<primer-autor>-<año>-<dos o tres palabras del título>`, todo en minúsculas y con guiones.
El slug es **la clave de cita en LaTeX**: `\cite{lerch-2017-forecasters-dilemma}`. Una vez
creado no se cambia, porque la tesis ya lo cita.

## Campos del catálogo

| Campo | Qué es |
| --- | --- |
| `slug` | Clave de cita. Igual al nombre del archivo. |
| `title`, `authors`, `year`, `venue`, `volume`, `number`, `pages` | Metadatos bibliográficos. |
| `doi`, `url` | `doi` siempre que exista; `url` para el preprint abierto cuando lo haya. |
| `bibtype` | Tipo de entrada BibTeX (`article`, `book`, `phdthesis`, `misc`). |
| `tipo` | `paper` · `tesis` · `informe` · `plantilla`. |
| `tags` | Para agrupar por tema al escribir un capítulo. |
| `file` | Ruta del PDF en `documents/`, o `null` si no está bajado. |
| `verificado` | **`true` sólo si los metadatos se confirmaron contra la fuente.** Un `false` significa que hay que chequearlos antes de citar. |
| `rol` | Por qué está en esta biblioteca: qué decisión del proyecto sostiene o discute. Es lo que distingue este catálogo de una lista de referencias. |

El campo `rol` es el que hace útil el catálogo. Una entrada sin `rol` es una cita suelta;
con `rol`, la trazabilidad **paper → decisión → experimento → capítulo** queda cerrada.

## Notas

`notes/<slug>.md` con las secciones que fija el plan: *metodología*, *modelos*,
*ventanas/splits*, *métricas*, *resultados*, *qué me llevo*. No hace falta completarlas
todas — se escribe la que aplica. Las notas enlazan a `Decisión NNN` de `docs/decisions.md`
y, cuando exista MLflow, al `run_id` del experimento que las usó.

Hoy hay nota para los cinco documentos que sostienen directamente el diseño de la función
de ganancia. Los otros diez tienen catálogo y esperan lectura.

## Exportar la bibliografía

```bash
.venv/Scripts/python.exe research/export_bib.py
```

Escribe `thesis/common/references.bib` con una entrada por documento, clave = `slug`.
Es un exportador provisorio de ~60 líneas; la Fase 7 lo reemplaza por el `BibtexExporter`
de la app. El archivo generado **no se edita a mano**: se regenera.

## Cómo agregar un documento

1. `research/catalog/<slug>.yaml` con los campos de arriba.
2. **Verificar los metadatos contra la fuente** y poner `verificado: true`. Un DOI mal
   copiado sobrevive hasta la defensa.
3. `research/notes/<slug>.md` cuando se lo lea.
4. Regenerar el `.bib`.
