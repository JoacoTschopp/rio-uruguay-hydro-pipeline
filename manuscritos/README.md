# `manuscritos/`: plan de tesis y tesis

Acá viven los dos documentos de la Maestría en Explotación de Datos y Descubrimiento de Conocimiento (UBA, FCEN):

- **plan de tesis** → `plan-de-tesis/`
- **tesis** → `tesis/`

Los dos usan el mismo formato: el del Trabajo Final Integrador de la Especialización, que la carrera ya aceptó.

Se trabaja en la rama `feature/tesis-latex`, que nace de `main-predic`, con el worktree `rio-uruguay-tesis`. El plan de trabajo, las dependencias y los pendientes están en [`PLAN.md`](PLAN.md).

## Estructura

```
manuscritos/
├── README.md                 este archivo
├── PLAN.md                   plan de trabajo, dependencias, riesgos y pendientes del autor
├── comun/
│   ├── tesisuba.cls          clase común: formato del TFI validado, con portada parametrizable
│   ├── referencias.bib       GENERADO desde research/catalog/ (no editar a mano)
│   └── img/escudo_uba.png
├── plan-de-tesis/
│   ├── main.tex              portada, índice, resumen y capítulos
│   ├── capitulos/            un .tex por capítulo
│   └── figuras/
├── tesis/
│   ├── main.tex
│   ├── capitulos/
│   ├── figuras/
│   └── tablas/
├── herramientas/
│   ├── compilar.ps1          regenera la bibliografía y compila con latexmk
│   └── exportar_bib.py       research/catalog/*.yaml → comun/referencias.bib
└── referencia/               material traído de otras ramas; se consulta, no se compila
    ├── tfi-especializacion-2025/
    └── borradores-rio-search-2026-08/
```

`build/` y los archivos auxiliares de LaTeX quedan fuera de git (ver `.gitignore`).

## Compilar

Hace falta:

- **MiKTeX**, que trae `pdflatex`, `bibtex` y `latexmk`;
- **perl**, que usa `latexmk` (alcanza el de Git for Windows: el script lo busca solo);
- **uv**, para regenerar la bibliografía.

Desde la raíz del repo, en **PowerShell**:

```powershell
.\manuscritos\herramientas\compilar.ps1                          # los dos documentos
.\manuscritos\herramientas\compilar.ps1 -Documento plan-de-tesis
.\manuscritos\herramientas\compilar.ps1 -Documento tesis -SinBib  # sin regenerar el .bib
.\manuscritos\herramientas\compilar.ps1 -Limpiar                  # borra build/
```

Los PDF salen en `plan-de-tesis/build/main.pdf` y `tesis/build/main.pdf`.

**No compilar desde Git Bash.** MSYS convierte `BIBINPUTS` a rutas `/c/...` que el `bibtex` de MiKTeX no entiende, y todas las citas quedan sin resolver. Está documentado en la Decisión 049 de la rama `feature/rio-search`.

Si se compila desde un editor (por ejemplo LaTeX Workshop), la variable `BIBINPUTS` tiene que incluir `manuscritos/comun`. Si no, `bibtex` no encuentra `referencias.bib`.

## Bibliografía

La fuente única es la biblioteca compartida de la raíz: `research/catalog/<slug>.yaml` para los metadatos y `research/notes/<slug>.md` para las notas de lectura. Sus reglas están en `research/README.md`.

1. Se agrega o corrige la entrada en `research/catalog/`, y se pone `verificado: true` después de comparar los metadatos con la fuente.
2. Se regenera el `.bib`. Lo hace `compilar.ps1`, o se puede correr aparte: `uv run --no-project --with pyyaml python manuscritos/herramientas/exportar_bib.py`.
3. Se cita con la clave igual al slug: `\cite{gupta-2009-kge}`, `\citep{...}` o `\citet{...}`. El estilo es APA (`apacite`), como en el TFI.

`comun/referencias.bib` es propio de los manuscritos. No se usa `thesis/common/references.bib`: ese archivo lo regenera `research/export_bib.py` desde otras ramas, y compartirlo generaría conflictos en cada merge.

La UI de Rio_Search (rama `feature/rio-search`) también lista y edita una biblioteca, pero lee otro directorio (`rio_search/research/`) con otro esquema YAML. Hoy **no puede leer** `research/catalog/`. Ver `PLAN.md` §6.

## Cómo convive esta rama con las demás

- Esta rama **solo escribe en `manuscritos/`**. La única excepción es sumar entradas nuevas a `research/catalog/` y `research/notes/`, y solo con acuerdo del autor.
- **Nunca borra ni modifica** archivos de otras carpetas ni de otras ramas.
- El material de otra rama se trae **copiándolo** (`git show` o `git archive`) y se anota de dónde salió: rama y commit. No se mergean ramas de feature.
- Para traer lo nuevo de `main-predic` se hace `git merge main-predic`. No hay conflictos, porque `manuscritos/` no existe en ninguna otra rama.
- Un resultado que se cita se identifica por **campaña, celda y commit** (por ejemplo `d303 / B0.06 @ 79b0cd7`). No se cita un número sin fuente.

## Convenciones de escritura

- Los capítulos van en UTF-8 con acentos directos, como el TFI. La clase va en ASCII.
- **Una oración por línea** en los `.tex`, para que los diffs y las revisiones queden legibles.
- Etiquetas con prefijo: `cap:`, `sec:`, `fig:`, `tab:`, `ec:`.
- Cada figura o tabla generada lleva, en su primera línea, un comentario con su fuente (archivo de resultados, celda, commit) y el script que la produjo.
- En el texto no se cita "Decisión NNN": la numeración de `docs/decisions.md` se repite con otro contenido entre ramas. Si hace falta, se cita el documento del repositorio en un anexo.

## Material de referencia (`referencia/`)

| Carpeta | Origen | Para qué sirve |
| --- | --- | --- |
| `tfi-especializacion-2025/` | `feature/rio-search:rio_search/research/templates/` @ `01b0b66` | Es el formato validado: `.tex`, el PDF presentado, `.bbl` e imágenes. No trae `.bib`; el original está en el respaldo de Overleaf, fuera del repo. |
| `borradores-rio-search-2026-08/` | `feature/rio-search:rio_search/thesis/` @ `01b0b66` | Borradores de proyecto y tesis de la Fase 8 de la app, más `riosearch.cls`, de donde se derivó `tesisuba.cls`. |

Los borradores de `borradores-rio-search-2026-08/` están **superados** y no se usan como fuente de resultados:

- se escribieron con enfoque BiLSTM y campeón por KGE, sobre el dataset delta 268 (anterior al cambio de telemetría);
- citan "Decisión NNN" con la numeración de esa rama;
- tienen un error conocido. `tesis/chapters/04_resultados.tex` dice que el KGE del BiLSTM iguala o supera al de la persistencia desde t+2, pero su propia tabla (`tables/compare_6e086068c9ef.tex`) muestra KGE de 0,01 a 0,11 contra 0,34 a 0,77 en todos los horizontes.
