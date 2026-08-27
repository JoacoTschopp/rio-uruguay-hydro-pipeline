# research/

Biblioteca de investigación de Rio_Search (Fase 7, `docs/rio_search_plan.md` §3.10). Sin LLM
(Decisión #3 del plan): es catálogo + notas + BibTeX, sin extracción asistida de texto — eso queda
como adaptador opcional para el futuro.

```
research/
├── catalog/      # <slug>.yaml por documento — metadatos (versionado en git)
├── notes/        # <slug>.md por documento — notas de lectura por sección (versionado en git)
├── documents/    # <slug>.<ext> — el PDF/material subido (gitignored, nunca en git)
└── templates/    # trabajo con formato LaTeX validado (lo aporta el usuario, Fase 8)
```

Sin base de datos: el propio repo es la base (`catalog/*.yaml` + `notes/*.md`), legible y
diffable. Los archivos de `documents/` quedan fuera de git a propósito (pueden pesar, y muchos
tienen licencias que no conviene commitear) — el catálogo referencia el PDF por `file` pero el
repo por sí solo no lo trae; cada quien vuelve a subirlo si clona el repo.

## Convención de slugs

El slug es la clave primaria del documento: nombre del archivo YAML/Markdown, clave de la entrada
BibTeX (`\cite{slug}` en la tesis) y nombre del PDF en `documents/`.

- Minúsculas, dígitos, `-`/`_`; sin espacios ni acentos.
- Formato por defecto (lo genera `AddDocument` si no se pasa `--slug`/`slug` explícito):
  `<título-normalizado>-<año>`, p. ej. *"Long Short-Term Memory"* (1997) → `long-short-term-memory-1997`.
- Se puede pasar un slug propio (recomendado cuando el título es muy largo o hay ambigüedad),
  p. ej. `hochreiter-1997-lstm`. Una vez creado, **no se cambia**: es la clave que ya puede estar
  citada en notas, en `\cite{}` o en un `run_id` vinculado.
- Nunca se reutiliza un slug para un documento distinto (mismo criterio que "nunca se edita un
  YAML de experimento ya corrido" del plan, §7): si hace falta corregir el documento equivocado,
  se borra y se vuelve a cargar.

## Secciones de la nota (`notes/<slug>.md`)

Cada nota es un Markdown con 6 secciones fijas (`domain/research/note.py::SECTION_ORDER`), en este
orden, más una sección final de enlaces:

1. **Metodología** — qué hace el paper/tesis, a alto nivel.
2. **Modelos** — arquitectura(s), hiperparámetros relevantes.
3. **Ventanas / splits** — cómo particiona entrenamiento/validación/test, si aplica embargo.
4. **Métricas** — qué reporta y cómo las calcula.
5. **Resultados** — números concretos, tablas, qué tan bien funcionó.
6. **Qué me llevo** — la síntesis para la tesis: qué de esto se aplica (o se descarta) en
   Rio_Search, y por qué.
7. **Enlaces** — vínculos estructurados a `Decisión NNN` (`docs/decisions.md`) y/o a un `run_id`
   de MLflow que esa lectura motivó o explica. Se editan desde la UI (dos campos: tipo +
   referencia) y se renderizan acá como líneas `- Decisión: Decisión NNN` / `` - Run: `run_id` ``;
   cualquier otro texto libre que se agregue a mano en esta sección se preserva al releer el
   archivo, pero no se reconstruye como enlace estructurado.

Una sección sin contenido se guarda como `_(sin notas todavía)_` — visible en el propio Markdown,
no un campo oculto.

## Cómo se llega hasta acá

- **UI** (`/research` en el frontend): subir PDF, cargar metadatos/tags, editar la nota por
  sección, vincular a Decisión/run, exportar BibTeX — un botón por acción, `POST/PUT
  /api/research/documents...` (ver `docs/rio_search_plan.md` §3.9).
- **CLI**: `rio-search research add <pdf> --title ... --authors "A;B" --year 2024 [--type paper|
  tesis|informe|plantilla] [--venue ...] [--tags a,b]` y `rio-search research export-bib`.

## BibTeX

`rio-search research export-bib` (o el botón "Exportar BibTeX" de la UI) recorre todo
`catalog/*.yaml`, arma una entrada BibTeX por documento (`article`/`phdthesis`/`techreport`/`misc`
según `type`, clave = slug) y sobrescribe `rio_search/thesis/common/references.bib`. La tesis cita
con `\cite{slug}` — no hace falta editar el `.bib` a mano, se regenera completo en cada export.
