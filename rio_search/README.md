# rio_search

Aplicación Rio_Search: banco de pruebas reproducible para la metodología que mejor proyecta el caudal
del Río Uruguay en `ana_74100000`, más el espacio de investigación (`research/`) y de escritura
(`thesis/`) de la Tesis de Maestría en Ciencia de Datos. Plan completo en `docs/rio_search_plan.md`
(raíz del repo); estado de las fases en la tabla de ese archivo.

Todo lo nuevo del plan vive dentro de este directorio, nada afuera (§3.1 del plan).

```
rio_search/
├── backend/    # API + dominio + CLI (uv, Python 3.12) — ver backend/README.md
├── frontend/   # UI React (Vite + TS) — ver frontend/README.md
├── research/   # biblioteca de investigación (catálogo, notas, BibTeX) — Fase 7
└── thesis/     # proyecto de tesis y tesis en LaTeX — Fase 8
```
