# Rio_Search — Plan de implementación

Fecha: **2026-08-27**
Rama de trabajo propuesta: `feature/rio-search`
Decisión que lo respalda: **038** (`decisions.md`)
Entregable final: una aplicación (`rio_search/`) que permite **buscar la metodología** que mejor proyecta el
caudal del Río Uruguay en `ana_74100000` — entrenar, comparar y operar modelos sobre
`weather.gold.training_dataset_v0` con trazabilidad completa en MLflow (Databricks) — más el espacio de
investigación (`rio_search/research/`) y de escritura (`rio_search/thesis/`) de la Tesis de Maestría en
Ciencia de Datos — todo dentro de `rio_search/`, nada afuera.

Este plan **continúa** `roadmap.md` (que cierra en "el modelado es una fase posterior") y no lo reemplaza:
el dataset sigue viviendo en Databricks y su roadmap sigue vigente (Fase 4 pronóstico, Fase 5 cadena
diaria). Rio_Search consume lo que ese roadmap produce.

---

## Estado de implementación

Mantenido por el agente principal (no por los sub-agentes de fase) para poder cortar y retomar en cualquier
momento sin releer todo el plan. Cada fase se implementa en un sub-agente aislado; al terminar (tests +
commit), el agente principal actualiza esta tabla antes de lanzar la siguiente.

| Fase | Estado | Commit(s) | Notas |
| --- | --- | --- | --- |
| 0 — Cimientos | ✅ Cerrada | `4e9f58d`, `df49d05` | Criterio de cierre cumplido contra Databricks/MLflow real (schema `weather.ml`, snapshot 71→83 cols, run `smoke`). Hallazgo: `mlflow.pytorch.log_model` importa pandas incluso en `mlflow-skinny` → Decisión 039 (renumerada desde 034 por colisión con `feature/ana-backfill-automation`, que ya usa 034-038 y no está mergeada a main): modelos PyTorch se loguean como artefacto plano (`torch.save` + JSON), no con el flavor `mlflow.pytorch`. **La Fase 3 debe leer la Decisión 039 antes de diseñar `ModelAdapterPort.save`/`load`.** Desviación menor de tooling: Vite generó `oxlint` en vez de `eslint`+`prettier`. |
| 1 — Contexto Datasets | ✅ Cerrada | `6963534` | 130 tests en verde (incl. suite de no-fuga contra dataset sintético). `rio-search datasets describe` corrido sobre el parquet real (delta 268, 83 cols) para `bilstm_baseline_v1.yaml`: rangos de `rolling_365` coinciden con el ejemplo del plan; cobertura TEST real confirma los huecos de §2.1 (nivel ≈67%, caudal/targets ≈91%). **Aviso para Fase 2/3**: `transforms.build_expressions` no resuelve globs — el YAML de ejemplo usa `"caudal_*"` en `log1p`, hay que resolverlo contra el catálogo de columnas antes de aplicar transforms reales, o reemplazar el wildcard por una lista explícita. |
| 2 — Evaluación, tracking y baselines naïve | ✅ Cerrada | `3626fb4` | 186 tests offline en verde + 1 integration real. 3 búsquedas reales en `/rio_search/baselines` (persistence/climatology/seasonal_naive) con métricas, tiempos, procedencia y hardware; **skill de persistencia = 0.0 exacto** en los 8 horizontes × 2 splits, con test de regresión permanente. `pytest` por defecto ahora excluye `integration` (`addopts` agregado, gap real encontrado: antes un `pytest` normal pegaba contra Databricks). **Decisión 040**: los naive usan `lookback_days=1` + historial inyectado, no pasan por `BuildFeatureMatrix` — no se cruzaron con el bug de globs de la Fase 1, pero la Fase 3 sí se iba a cruzar (avisado). |
| 3 — BiLSTM baseline (PyTorch) | ✅ Cerrada | `8af32c7`, `77307d3` | 208 tests en verde. BiLSTM supera a persistencia en **7/8 horizontes** (t+2…t+14, skill>0 real en TEST); h01 negativo y documentado (Decisión 043, consistente con la literatura: autocorrelación día a día muy alta en caudal fluvial). `multi_output` y `per_horizon` corridos y comparados (per_horizon gana en las 3 métricas resumen a 10.3x el costo). Reproducibilidad CPU verificada **exacta** (200 métricas, 0 discrepancias). Registrado en `weather.ml.rio_search_bilstm`, versiones **9-12** — **pendiente que el usuario revise nombre/alias/política de versiones (§8 del plan)**. Hallazgo central: targets con `NaN` reales (huecos de calendario, §2.1) sin enmascarar divergían el entrenamiento a NaN desde el epoch 1 — corregido con masking + `features.exclude` cableado (antes existía en el YAML pero no se usaba). **Decisión 041**: glob de transforms resuelto. **Decisión 042**: registro UC exige `signature` y el cliente MLflow importa pandas igual al validarla — resuelto con `MLmodel` mínimo + stub temporal. **Aviso operativo**: dos procesos tocando Databricks/MLflow con el mismo perfil CLI al mismo tiempo compiten por el cache de tokens OAuth y uno falla con 401 (Windows) — nunca correr dos procesos de Rio_Search contra Databricks en paralelo; la Fase 4 (`JobRunner`) ya preveía un lock por esto. `test_bilstm_integration.py` existe pero no se corrió a propósito (registraría una versión extra en UC) — correrla es un pendiente liviano, no bloqueante. |
| 4 — Backend API | ✅ Cerrada | `fbd88d8` | 262 tests en verde (54 nuevos). Endpoints reales: `/api/{health,searches,runs,runs/{id},runs/{id}/series/{name},runs/compare,jobs,jobs/{id},jobs/{id}/log(SSE),datasets,features}` — `/api/champions` y `/api/forecasts/research` quedan para Fases 6/7 a propósito. `TrackingReadPort` separado del de escritura, cacheado en SQLite (TTL 10-20s en vivo, 6h runs terminales). `JobRunner` local con lock de un solo proceso (portado, no importado, del patrón de `ana_historic_backfill/lock.py`) — importante por el aviso operativo de la Fase 3 (nunca 2 procesos pegándole a Databricks a la vez). Verificado real: servidor levantado, `curl /api/runs?families=bilstm` devolvió 47 runs reales de la Fase 3; `POST /api/jobs` con `persistence_baseline_v1.yaml` corrió de punta a punta y quedó visible en la API. Bug real encontrado y corregido: `subprocess.Popen` sin `encoding="utf-8"` explícito rompía con `UnicodeDecodeError` en Windows (mismo tipo de problema que el CLI de la Fase 0). **Decisión 044**. **Aviso para Fase 5**: la cola de jobs no sobrevive un reinicio del backend (deliberado); `/api/runs`/`/api/searches` no paginan (tope 2000, no es problema todavía); `/api/datasets` no trae cobertura por columna/año todavía (sigue siendo sólo el CLI) — conectar `DescribeDataset` si la página Datasets de la UI lo necesita. |
| 5 — UI React | ✅ Cerrada | `3ddfdf5` | Páginas Búsquedas/Run/Comparar/Lanzar/Datasets (+Health de Fase 0), servidas estáticas desde FastAPI en `/` (montado después de todas las rutas `/api/*`, con fallback SPA). Verificado con navegador headless real contra el backend real: 6 rutas navegadas, 0 errores de consola, 0 requests fallidos, datos reales de MLflow. Comparación real con 3 trials BiLSTM de la Fase 3. Prueba end-to-end completa desde la UI: lanzó `persistence_baseline_v1.yaml` desde Lanzar, vio el log SSE en vivo, el job terminó y el run quedó navegable. `npm run build` limpio (tsc estricto). 264 tests de backend sin romperse (262+2 nuevas del montaje estático). **Decisión 045**. **Gaps reales documentados (no inventados) para Fase 6+**: no hay endpoint de artefactos (bloquea el hidrograma TEST real, se usó `{split}/coverage/hNN` como sustituto parcial), no hay cobertura por columna/año en `/api/datasets`, no hay endpoint de lectura/escritura de YAMLs de experimento (Lanzar usa una lista estática de las 5 configs reales + override de texto libre). **Para Fase 6**: agregar "Pronóstico de hoy" es un ítem más en `components/Layout.tsx::NAV_ITEMS` + una página nueva; el botón "promover a campeón" en `RunPage.tsx` ya tiene el comentario marcando dónde conectar `POST /api/champions`. |
| 6 — Inferencia diaria | ⬜ No iniciada | — | — |
| 7 — Research | ⬜ No iniciada | — | — |
| 8 — Tesis LaTeX | ⬜ No iniciada | — | — |
| 9 — Extensibilidad y promoción a Gold | ⬜ No iniciada | — | — |

Leyenda: ⬜ No iniciada · 🟨 En curso · ✅ Cerrada (test + commit) · ⛔ Bloqueada (ver Notas).

**Para retomar:** mirar la última fase no ✅, leer su sección en `## 5. Fases` y su fila de Notas acá arriba
(qué quedó a medio hacer o qué bloqueó), y continuar desde ahí — no reiniciar fases ya ✅.

---

## 0. Decisiones cerradas antes de escribir el plan

Preguntas hechas y respondidas el 2026-08-27, en dos rondas (1-8 y 9-14). Ninguna queda abierta.

| # | Pregunta | Decisión |
| --- | --- | --- |
| 1 | ¿Dónde corre el entrenamiento? | **Local** (RTX 3060, 12 GB) con **tracking MLflow en Databricks**. Sigue el patrón del repo: cómputo pesado local, Databricks como almacén de verdad. |
| 2 | ¿Cómo se modelan los 8 horizontes? | **Configurable por experimento**: `multi_output` (un modelo, 8 salidas) o `per_horizon` (8 modelos). Comparar ambas es parte de la tesis. |
| 3 | Módulo Research | **Biblioteca + notas + BibTeX**, sin LLM. Genera el `references.bib` que consume la tesis. |
| 4 | Regla de split temporal | **Configurable por experimento**: `rolling_365` (ventana móvil de 365 días desde el último día con target observable) o `calendar_year`. |
| 5 | Frontera del feature engineering | Gold es la fuente principal, pero **la app puede derivar features experimentales** (versionadas y logueadas en MLflow); lo que funciona se **promueve a Gold** con notebook + Decisión. |
| 6 | Framework DL | **PyTorch**, con **detección automática de device** (CUDA → Apple MPS → CPU) al inicio de cada experimento y en cada re-ejecución de predicción. |
| 7 | Alcance de inferencia | **Experimentación + inferencia diaria en la primera entrega** (CLI/endpoint de predicción y vista "Pronóstico de hoy"). |
| 8 | Tesis LaTeX | Hay un **trabajo ya presentado con formato validado**; el usuario lo colocará en `rio_search/research/templates/` una vez creado el módulo de Research. La fase de tesis va **inmediatamente después** de Research y arranca **pidiendo ese modelo**. |
| 9 | Librería de datos | **Polars, nunca pandas.** pandas queda prohibido como dependencia del backend: `mlflow-skinny` en vez de `mlflow` (el paquete completo arrastra pandas), guardia de `ruff` (`banned-api`) y un test que falla si `import pandas` funciona en el entorno. |
| 10 | Dataset al iniciar una búsqueda | **Cada corrida de búsqueda descarga el dataset actual** antes de tocar nada (protocolo de frescura, §3.6): verifica la versión Delta de Gold, regenera el snapshot del Volume si está atrás, baja el parquet y verifica su `sha256`. La lógica de descarga de `notebooks_local/gold_export/export_gold_dataset.py` se **porta a la app** (sin pandas), no se importa. |
| 11 | Procedencia del código en MLflow | **Sí, es factible y se hace** (§3.13): cada run guarda commit, rama, URL de GitHub y bandera de árbol sucio como tags; y como artefactos el `git diff` no commiteado y un snapshot del paquete `rio_search/` (`code_paths` en el modelo logueado). El **SHA del commit** es la referencia durable; la rama es comodidad. |
| 12 | Registro de modelos | **Se implementa `weather.ml`** (Unity Catalog) desde la Fase 0; se **revisa después de la primera corrida registrada** (Fase 3). |
| 13 | Duración del entrenamiento | **No es una restricción.** Sin presupuesto de tiempo, sin `max_time`, sin recortar grids por reloj: el entrenamiento y la búsqueda de hiperparámetros duran lo que duren (early stopping por paciencia, nunca por tiempo). |
| 14 | Registro de tiempos | **Todo tiempo queda en MLflow** (§3.12): descarga del dataset, preprocesamiento, entrenamiento total y por epoch, búsqueda de HP total y por trial, evaluación, inferencia (carga del modelo + predicción), junto con el hardware que lo produjo. Es un resultado de la tesis, no telemetría. |

Nota de vocabulario: "onion + DDL" del pedido original se interpreta como **arquitectura Onion + Domain-Driven
Design (DDD)**: dominio en el centro sin dependencias, capas de aplicación/infraestructura/interfaces hacia
afuera, y el modelado por contextos acotados (§3.2). **Corrida de búsqueda (search)**: la unidad de trabajo
de Rio_Search — un run padre en MLflow que explora una o más configuraciones (**trials**) sobre **una misma
versión del dataset**; un experimento simple es una búsqueda de un solo trial.

---

## 1. Objetivo y alcance

**Qué es Rio_Search.** Un banco de pruebas reproducible para la pregunta central de la tesis: *¿qué
metodología (modelo × ventana de entrenamiento × conjunto de features × estrategia de horizontes) proyecta
mejor el caudal a t+1…t+7 y t+14?* Cada corrida queda registrada en MLflow con su configuración, su versión
exacta de dataset, sus métricas por horizonte y sus artefactos, de modo que cualquier número de la tesis se
pueda rastrear a un `run_id`.

**Qué produce.**

1. Un backend Python (`rio_search/backend`) con dominio explícito: búsquedas y sus trials, datasets
   versionados, modelos enchufables, predicciones diarias, biblioteca de investigación — con **tiempos y
   procedencia del código** registrados en cada corrida.
2. Una UI React (`rio_search/frontend`) para seguir y comparar lo logrado en MLflow, lanzar experimentos,
   ver el pronóstico del día y gestionar la biblioteca de papers/tesis.
3. Un pronóstico diario operativo (t+1…t+14) emitido por el modelo "campeón", con su trazabilidad.
4. El espacio `rio_search/research/` (documentos, notas, BibTeX) y `rio_search/thesis/` (proyecto de tesis y tesis en LaTeX).

**Qué no es.**

* No reemplaza al pipeline Medallion: no ingesta, no transforma Silver, no escribe en Gold. Las features
  que la app "descubre" se promueven a Gold por el camino de siempre (notebook + `decisions.md`).
* No es multiusuario ni se despliega en la nube: corre en la máquina del tesista (`localhost`), igual que el
  dashboard Gradio del backfill de ANA.
* No usa LLM para leer papers (Decisión #3 arriba). Queda como adaptador opcional para el futuro.

---

## 2. Estado de partida (lo que condiciona el diseño)

Relevado el 2026-08-27 contra el repositorio y contra Databricks real.

### 2.1. Dataset

| Aspecto | Valor | Consecuencia para Rio_Search |
| --- | --- | --- |
| Tabla | `weather.gold.training_dataset_v0` | Única fuente de entrenamiento. |
| Grano | Diario, 1 punto (`ana_74100000`), **9.732 filas sin huecos de calendario**, 2000-01-01 → 2026-08-23 | Series continuas: el ventaneo de secuencias no necesita re-indexar. |
| Targets | `caudal_t_mas_{1..7,14}d` (principal) y `nivel_rio_t_mas_{1..7,14}d` (secundario), **verificados sin fuga** (`gold_quality_report.md` §4) | 16 columnas de target listas; la app no vuelve a calcular `LEAD`. |
| Columnas | **83 en Databricks, 71 en el parquet local** (snapshot delta 263 anterior a MERGE/SAMeT) | **Fase 0 debe regenerar el snapshot** (`Export_Gold_Snapshot` + `export_gold_dataset.py --refresh`). |
| Cobertura temperatura por estación | 0 % en 2000-2005, 100 % 2008-2025 | Experimentos con `temp_estacion` necesitan `train_start ≥ 2007` o usar SAMeT (100 %). Por eso la ventana de entrenamiento es configurable. |
| MERGE / SAMeT (CPTEC) | 100 % todo el período | Grupo de features más limpio; candidato al baseline. |
| `lluvia_acumulada_mm` | Es una **suma sobre N estaciones variables** (hasta 12.241 mm) | No estacionaria. Preferir MERGE o normalizar por `station_count` (feature experimental). |
| `caudal_agregado_alta_frontera_m3s` | Outlier de **823.897 m³/s** (estación 73340000, 2023, curva no confiable) | Transform experimental `clip`/`winsor`, y candidata a promoción a Gold (filtrar por `caudal_confiable`). |
| Pronóstico (TIGGE/GEFS) | **Todavía no está en Gold** (roadmap Fase 4 en curso) | El diseño versiona datasets y agrupa features (`observadas` vs `forecast`) desde el día 1; "con vs sin pronóstico" será un resultado de la tesis. |
| Huecos en el período de TEST | `nivel` nulo 2025-11-01 → 2026-03-27 (93 días); `caudal` nulo 2026-04-07 → 05-04 (26 días) | Métricas sobre targets disponibles + reporte de cobertura por split. Target `nivel` tendrá TEST pobre; `caudal` (principal) está bien. |

### 2.2. Entorno

| Recurso | Estado |
| --- | --- |
| GPU | NVIDIA RTX 3060, 12 GB (CUDA). |
| Python | 3.12 (`.venv` actual sin torch/mlflow/sklearn; tiene cfgrib/eccodes/gradio). `uv 0.11` disponible. |
| Node | 24.15 / npm 11.13. |
| Databricks CLI | v0.299, perfil `joaquintschopp@gmail.com` válido. Warehouse serverless `d8aaafcf1fdb6645`. |
| MLflow en el workspace | **Sin experimentos** todavía. |
| LaTeX | MiKTeX 24.1 + latexmk 4.88. |
| Docker | 28.3 (no requerido por este plan). |

### 2.3. Convenciones del repo que se respetan

* Módulos locales en Python puro, **tests offline con pytest** sin tocar Databricks
  (`notebooks_local/gold_export/test_export_gold_dataset.py`, `forecast_calibration/test_calibration.py`).
  Esos módulos usan pandas; **Rio_Search no lo hereda**: porta la lógica que necesita (descarga del snapshot,
  regla R9) y trabaja con Polars (Decisión #9).
* Acceso a Databricks con el perfil del CLI ya autenticado (`~/.databrickscfg`); la app lo usa a través del
  SDK (`databricks-sdk`) para la Statement API, `jobs submit` y descarga de archivos del Volume. Sin secretos en git.
* Toda decisión técnica se registra en `decisions.md` antes o junto con el código.
* Cada fase cierra con test + entregable versionado ("Criterio de avance", `roadmap.md` §4).

---

## 3. Arquitectura

### 3.1. Ubicación en el repositorio

```
rio-uruguay-hydro-pipeline/
├── notebooks/, notebooks_local/, docs/, SIG/, databricks.yml   # pipeline existente, sin cambios
└── rio_search/                       # TODO lo nuevo de este plan vive acá adentro, nada queda afuera
    ├── README.md
    ├── backend/
    │   ├── pyproject.toml            # proyecto uv independiente (python 3.12, torch, mlflow, fastapi…)
    │   ├── uv.lock
    │   ├── rio_search/               # paquete (ver 3.2)
    │   │   ├── domain/
    │   │   ├── application/
    │   │   ├── infrastructure/
    │   │   └── interfaces/
    │   ├── configs/
    │   │   ├── experiments/*.yaml    # una config por experimento (versionadas)
    │   │   └── feature_groups.yaml   # catálogo de columnas de Gold por grupo
    │   ├── tests/
    │   └── data/                     # gitignored: cache parquet, sqlite, checkpoints
    ├── frontend/                     # Vite + React + TypeScript
    ├── research/                     # biblioteca de investigación (Fase 7)
    │   ├── catalog/*.yaml            # metadatos por documento (versionado)
    │   ├── notes/*.md                # notas por documento (versionado)
    │   ├── documents/                # PDFs (gitignored)
    │   └── templates/                # trabajo con formato validado (lo aporta el usuario, Fase 8)
    └── thesis/                       # LaTeX (Fase 8)
        ├── common/                   # clase, preámbulo, macros, references.bib (generado)
        ├── proyecto/                 # proyecto de tesis
        ├── tesis/                    # tesis
        └── figures/, tables/         # generadas desde MLflow por CLI
```

`rio_search/research/` y `rio_search/thesis/` viven **dentro** de `rio_search/` (decisión del usuario,
2026-08-27): todo lo nuevo de este plan queda contenido en un único directorio del repo, nada afuera. Son
entregables de la tesis y no de la app en el sentido de que la app sólo los gestiona (no los versiona como
código de producción), pero comparten ubicación con el resto de Rio_Search por simplicidad de repo.

### 3.2. Backend: Onion + DDD

**Regla de dependencia**: `domain` no importa nada del proyecto; `application` importa sólo `domain`;
`infrastructure` implementa los puertos de `application`; `interfaces` (API, CLI) sólo orquesta a través
de un *composition root* (`container.py`). Ningún `import torch`, `import mlflow` ni `import pandas` en
`domain`.

```
rio_search/
├── domain/
│   ├── shared/         Horizon, DateRange, TargetVariable (caudal|nivel), Device, Seed
│   ├── datasets/       DatasetVersion, FeatureGroup, FeatureSpec, FeatureTransform, SplitPolicy, Split,
│   │                   SequenceSpec, DatasetCoverage
│   ├── experiments/    ExperimentConfig (VO desde YAML), Search, SearchSpace, SearchStrategy, Trial,
│   │                   RunStatus, HorizonStrategy, TrainingSpec, HorizonMetrics, MetricSet,
│   │                   Timings, CodeProvenance
│   ├── models/         ModelSpec, ModelFamily (naive|sklearn|torch), ModelRegistry (plugins)
│   ├── predictions/    Champion, Forecast, ForecastPoint, AsOfPolicy
│   └── research/       Document, Note, Tag, BibEntry, Link (a Decisión / run_id)
├── application/
│   ├── ports/          TrackingPort, DatasetRepository, SnapshotSyncPort, GoldCatalogPort,
│   │                   ModelAdapterPort, ModelRegistryPort, ForecastRepository, DocumentStore,
│   │                   JobRunner, DeviceResolver, GitProvenancePort, Stopwatch, Clock
│   ├── datasets/       RefreshDataset (protocolo de frescura), DescribeDataset, BuildSplit, BuildFeatureMatrix
│   ├── experiments/    RunSearch (→ RunTrial por cada config), ListRuns, CompareRuns, GetRunDetail
│   ├── predictions/    IssueDailyForecast, PromoteChampion, BacktestRecent
│   └── research/       AddDocument, UpdateNote, TagDocument, ExportBibtex
├── infrastructure/
│   ├── tracking/       mlflow_databricks.py (TrackingPort: runs anidados, tags, tiempos, procedencia, MetaDataset)
│   ├── datasets/       gold_snapshot_sync.py (portado de export_gold_dataset.py, sin pandas),
│   │                   gold_parquet_repository.py (Polars), feature_catalog.py
│   ├── provenance/     git_provenance.py (commit, rama, remote, diff no commiteado, snapshot del paquete)
│   ├── timing/         stopwatch.py (perf_counter + torch.cuda.synchronize)
│   ├── preprocess/     transforms/ (expresiones Polars: log1p, doy_cyclic, clip, ratio, diff, rolling), imputers, scalers
│   ├── models/         naive/ (persistence, climatology, seasonal_naive), sklearn/ (ridge, lightgbm),
│   │                   torch/ (bilstm.py, base_torch_adapter.py, datasets.py, trainer.py)
│   ├── device/         torch_device_resolver.py
│   ├── persistence/    sqlite (runs cache, champions, forecasts, job queue)
│   ├── research/       yaml_catalog.py, filesystem_document_store.py, bibtex_exporter.py
│   └── databricks/     sdk_client.py (Statement API, jobs submit, descarga de Volume), volume_publisher.py
└── interfaces/
    ├── api/            FastAPI: routers experiments, runs, datasets, features, predictions, research, jobs
    ├── cli/            Typer: `rio-search …`
    └── container.py    composition root
```

**Contextos acotados y sus agregados**

| Contexto | Agregado raíz | Invariantes que protege |
| --- | --- | --- |
| Datasets | `DatasetVersion` | Toda corrida referencia `delta_version` + `sha256` del parquet. Un `Split` nunca solapa y respeta el embargo. El escalador se ajusta **sólo** con TRAIN. |
| Experiments | `Search` → `Trial` | Una búsqueda **descarga y pinea una sola** `DatasetVersion` para todos sus trials (Decisión #10). Una config YAML = un hash, logueado. Todo trial tiene métricas **y tiempos** para todos los horizontes de su config, y su `CodeProvenance`. |
| Models | `ModelSpec` + `ModelRegistry` | Un modelo se agrega registrando un adaptador; el dominio y la aplicación no cambian. |
| Predictions | `Champion`, `Forecast` | Un `Forecast` declara `as_of` (último día con inputs completos), `dataset_version`, `run_id` del campeón y `device`. |
| Research | `Document` | Todo documento tiene `BibEntry` válida antes de exportarse a `references.bib`. |

### 3.3. Modelos enchufables (cómo se agrega un modelo nuevo)

```python
# application/ports/model_adapter.py
class ModelAdapterPort(Protocol):
    name: str                       # "bilstm", "persistence", "lightgbm", …
    family: ModelFamily             # NAIVE | SKLEARN | TORCH
    supports: set[HorizonStrategy]  # {MULTI_OUTPUT, PER_HORIZON}
    def build(self, spec: ModelSpec, n_features: int, n_outputs: int, device: Device) -> None: ...
    def fit(self, train: Sequences, val: Sequences, training: TrainingSpec, callbacks: FitCallbacks) -> FitResult: ...
    def predict(self, X: Sequences) -> Predictions: ...
    def save(self, path: Path) -> None: ...
    @classmethod
    def load(cls, path: Path, device: Device) -> "ModelAdapterPort": ...

# infrastructure/models/torch/bilstm.py
@register_model("bilstm")
class BiLSTMAdapter(BaseTorchAdapter): ...
```

* `ModelRegistry` descubre adaptadores por decorador (`@register_model`) al importar
  `infrastructure.models`. Agregar un modelo = un archivo nuevo + un YAML de experimento.
* `per_horizon` se implementa **en la aplicación** (bucle sobre horizontes, un run hijo de MLflow por
  horizonte, agregación de métricas en el run padre), no en cada adaptador: un adaptador que soporte
  `n_outputs=1` ya soporta `per_horizon` gratis.
* Los modelos naïve (`persistence`, `climatology`, `seasonal_naive`) usan la misma interfaz: son la vara
  contra la que se mide el *skill* de todo lo demás.

### 3.4. Detección de device (Decisión #6)

`TorchDeviceResolver.resolve(preferred="auto")`:

1. `torch.cuda.is_available()` → `cuda` (loguea nombre de GPU, VRAM, versión CUDA).
2. `torch.backends.mps.is_available()` → `mps` (Apple Silicon; setea `PYTORCH_ENABLE_MPS_FALLBACK=1`
   para los kernels no soportados).
3. Si no, `cpu`.

Se invoca **al inicio de `RunSearch` y de `IssueDailyForecast`** (Decisión #6: también en la
re-ejecución de predicción), se loguea como tag `rio_search.device` y se persiste en el `Forecast`. Los
checkpoints se guardan en CPU (`state_dict` con `map_location`) para que un modelo entrenado en CUDA se
pueda re-ejecutar en MPS o CPU sin conversión. AMP (`autocast`) sólo en CUDA; determinismo
(`torch.manual_seed`, `cudnn.deterministic`) activado por defecto.

### 3.5. MLflow en Databricks (Decisión #1)

* Paquete **`mlflow-skinny`** (cliente de tracking sin pandas/numpy; Decisión #9) + `databricks-sdk`.
  Tracking URI: `databricks://joaquintschopp@gmail.com` (usa el perfil del CLI, sin tokens en el repo).
  Registro de modelos: `databricks-uc`.
* Experimentos: `/Users/joaquintschopp@gmail.com/rio_search/<familia>` —
  `baselines`, `bilstm`, `<modelo_futuro>`, `daily_forecast`, `smoke`.
* **Jerarquía de runs**: `Search` = run padre; cada `Trial` = run hijo (`nested=True`); con
  `per_horizon`, cada trial abre a su vez 8 runs nietos (uno por horizonte). Un experimento simple es
  una búsqueda de un solo trial — misma jerarquía, sin caso especial.
* Nombre de run: `{model}__{target}__{strategy}__{split}__{train_start}__{YYYYMMDD-HHMM}`
  (el padre: `search__{name}__{YYYYMMDD-HHMM}`).
* Tags obligatorios (`rio_search.*`): `model`, `target`, `horizon_strategy`, `split_policy`,
  `train_start`, `dataset_delta_version`, `dataset_sha256`, `config_sha256`, `feature_groups`,
  `experimental_transforms`; de procedencia (§3.13): `git_sha`, `git_branch`, `git_remote`,
  `git_dirty`, `github_url`; de hardware (§3.12): `device`, `device_name`, `cuda_version`,
  `torch_version`, `cpu`, `ram_gb`, `hostname`.
* Params: la config YAML aplanada (`model.hidden_size`, `sequence.lookback_days`, …).
* Métricas de calidad: por split y horizonte, jerárquicas: `test/rmse/h01` … `test/kge/h14`, `val/…`;
  agregadas `test/rmse/mean`; curvas `train/loss` y `val/loss` por `step=epoch`.
* **Métricas de tiempo** (`time/*`, §3.12): en todos los runs, siempre en segundos, siempre las mismas
  claves — comparables entre búsquedas, modelos y máquinas.
* Artefactos: `config/experiment.yaml`, `split/split.json` (fechas exactas de cada split + cobertura),
  `features/spec.json` (columnas finales, orden, transforms aplicadas), `preprocess/pipeline.pkl`
  (imputador + escalador ajustados con TRAIN), `predictions/{val,test}.parquet` (fecha, horizonte,
  observado, predicho), `series/*.json` (para los gráficos interactivos de la UI), `plots/*.png` (para
  la tesis), `timings/timings.json` (§3.12), `code/` (§3.13), `model/` (`mlflow.pytorch` /
  `mlflow.sklearn` con *signature* y `code_paths`), `env/uv.lock`, `env/pip_freeze.txt`.
* Dataset: `mlflow.log_input(MetaDataset(name="training_dataset_v0@delta{N}", digest=sha256[:8],
  source=<ruta del Volume>))` — `MetaDataset` registra nombre, digest y origen sin materializar el
  DataFrame ni depender de pandas (no existe `from_polars` en MLflow; se verifica en Fase 0).
* Registro UC (**decidido**, Decisión #12): schema `weather.ml` creado en la Fase 0; modelo
  `weather.ml.rio_search_<model>`; alias `champion_<target>` apunta a la versión campeona. Copia local en
  SQLite para operar sin red. **Revisión** de nombres, aliases y política de versiones tras la primera
  corrida registrada (Fase 3).

### 3.6. Datos: versiones, features, splits, ventanas

**Polars, no pandas** (Decisión #9). Toda la capa de datos es Polars: `DatasetRepository` devuelve
`pl.DataFrame`; las transformaciones experimentales son expresiones (`list[pl.Expr]`) que se aplican en
un solo `with_columns`; imputación y escalado son expresiones ajustadas con estadísticos de TRAIN; los
splits son filtros sobre `fecha`; el ventaneo produce tensores con `df.to_torch()` / `df.to_numpy()`;
las métricas corren sobre NumPy; los parquet de predicciones y de pronóstico se escriben con Polars.
pandas no está instalado en el entorno (§7).

**Descarga obligatoria al iniciar cada búsqueda** (Decisión #10). `RunSearch` llama a `RefreshDataset`
**antes** de cualquier otra cosa, y lo que descarga queda pineado para todos los trials de esa búsqueda.
La lógica de sincronización se porta desde `notebooks_local/gold_export/export_gold_dataset.py`
(`sync`, `needs_download`, verificación `sha256`, lock de un solo proceso) a
`infrastructure/datasets/gold_snapshot_sync.py`, sin pandas y usando el SDK en vez de `subprocess`
sobre el CLI. Protocolo de frescura, con `dataset.refresh` en la config:

| Paso | Qué hace | Por qué |
| --- | --- | --- |
| 1 | `DESCRIBE HISTORY weather.gold.training_dataset_v0 LIMIT 1` vía Statement API (warehouse serverless) → versión Delta actual de Gold | El snapshot del Volume puede estar atrás de Gold — hoy lo está: manifest delta 263 / 71 columnas vs. Gold con 83. |
| 2 | Baja `manifest.json` del Volume | Liviano; siempre. |
| 3 | Si `manifest.delta_version < versión de Gold` → `jobs submit` de un run ad hoc con el notebook `05_Gold/Export_Gold_Snapshot` (mismo patrón que `gefs_bronze_merge_submit.json`), espera a que termine y vuelve a bajar el manifest | Garantiza que "dataset actual" = Gold de hoy, no el último snapshot que alguien exportó. |
| 4 | Si el `sha256` del parquet en cache ≠ `manifest.file_sha256` (o `refresh: force`) → baja el parquet y verifica el hash | Nunca se entrena sobre un archivo distinto del que dice el manifest. |
| 5 | Construye `DatasetVersion = (delta_version, sha256, rows, fecha_min, fecha_max, columns)`, valida el catálogo de features contra `columns` y lo pinea en el run padre (tags + `MetaDataset`) | Todos los trials de la búsqueda comparan sobre el mismo dato. |

Modos: `ensure_latest` (default, los 5 pasos), `volume_as_is` (salta el paso 3: usa el snapshot tal
como está), `offline` (sólo cache local; falla si no hay). El tiempo de cada paso se registra
(`time/dataset_refresh_s` y sus sub-pasos, §3.12). Si Gold cambia de esquema (Fase 4 del roadmap agrega
columnas), la app lo ve como una versión nueva; los experimentos viejos siguen apuntando a la suya.

**Catálogo de features** (`configs/feature_groups.yaml`, generado desde el diccionario de
`gold_quality_report.md` §7 y validado contra el parquet en cada carga):

| Grupo | Columnas (resumen) | Default |
| --- | --- | --- |
| `caudal_estado` | `caudal_actual_m3s`, lags 1/3/7, medias 3/7, `delta_1d` | on |
| `nivel_estado` | `nivel_rio_actual_m`, lags, medias, `delta_1d` | on |
| `caudal_agregado_alta_frontera` | `_m3s`, lags 1-3, `confiable_pct` | on (con `clip` experimental) |
| `caudal_agregado_otras` | `intermedia_paso_libres_*`, `baja_salto_grande_*` | **off** (Decisión 018) |
| `temp_estacion` | `temp_media/min/max_c`, `station_count`, `cobertura_pct` | off (0 % antes de 2006) |
| `lluvia_estacion` | `lluvia_acumulada_mm`, `acum_3d/7d`, `station_count`, `cobertura_pct` | off (suma no estacionaria) |
| `cptec_grid` | `lluvia_merge_*`, `temp_samet_*` | on |
| `calidad` | `caudal_confiable`, `supera_aforo_maximo`, `*_es_preliminar` (cast 0/1) | off |
| `forecast` | reservado (Fase 4 del roadmap) | — |
| `targets_caudal` / `targets_nivel` | `*_t_mas_{h}d` | según `target` |
| `meta` | `fecha`, `punto_prediccion`, `codigoestacao`, timestamps, deprecadas (`temp_station_count`, `lluvia_is_usable`) | nunca |

**Transformaciones experimentales** (Decisión #5): registro de funciones puras con nombre, versión y
params (`log1p`, `doy_cyclic`, `clip`, `ratio` p. ej. `lluvia_acumulada_mm / station_count`, `diff`,
`rolling`). Se declaran en el YAML, se aplican **después** de cargar Gold y **antes** de ajustar el
escalador, se loguean en `features/spec.json` y en el tag `experimental_transforms`. Cada transform lleva
su docstring "cómo se promovería a Gold" (columna equivalente en PySpark). Una transform se promueve cuando
un experimento demuestra que aporta: se implementa en `ETL_Gold_Training_Dataset_v0.ipynb`, se registra
la Decisión, y el YAML pasa a usar la columna nativa.

**Preparación dependiente del modelo** (siempre en la app): selección de columnas → transforms →
imputación (`ffill` acotado + mediana de TRAIN; se loguea el % imputado por columna y split) → escalado
(`standard` | `robust` | `minmax` | `none`, ajustado sólo con TRAIN) → ventaneo (`lookback_days`) →
tensores `(N, lookback, n_features)` y targets `(N, n_horizons)`.

**Políticas de split** (Decisión #4). `anchor` = último día en el que el target es observable
(`caudal_t_mas_{h}d` no nulo); en `multi_output` se toma el mínimo entre los 8 horizontes (= `fecha_max − 14`).
`embargo_days` (default `max(horizons)` = 14) separa los splits para que ningún target de VAL caiga
dentro del período de inputs de TEST.

| Política | TEST | VAL | TRAIN |
| --- | --- | --- | --- |
| `rolling_365` | `(anchor − 365, anchor]` | `(anchor − 730 − e, anchor − 365 − e]` | `[train_start, anchor − 730 − 2e]` |
| `calendar_year` | año `Y` (último año calendario completo con target) | año `Y−1` menos embargo al final | `[train_start, 31-dic-(Y−2) − e]` |

Con los datos de hoy, `rolling_365` da TEST ≈ 2025-08-10 → 2026-08-09, VAL ≈ 2024-07-27 → 2025-07-26.

**Ventana de entrenamiento** (`train_window`): `start: 2008-01-01` **o** `years: 10` (los N años previos a
VAL). Es el eje "cambiar ventanas de entrenamiento" del pedido original; junto con `sequence.lookback_days`
(ventana de secuencia) son los dos parámetros de ventana del experimento.

### 3.7. Evaluación

Métricas por horizonte y por split (`val`, `test`), calculadas sobre targets observados (se reporta
cobertura): **RMSE, MAE, MAPE, NSE (Nash-Sutcliffe), KGE (Kling-Gupta), PBIAS, R²**, error en picos
(top 5 % de caudal observado: MAE y sesgo) y **skill score vs. persistencia** (`1 − RMSE_modelo /
RMSE_persistencia`). NSE y KGE son las métricas estándar en hidrología y las que la tesis va a defender;
RMSE/MAE en m³/s son las que se leen en la UI. Las métricas se implementan como funciones puras con tests
contra valores conocidos.

Gráficos (artefactos PNG + JSON): hidrograma observado vs. predicho en TEST por horizonte, dispersión,
residuos en el tiempo, curva de pérdida, métrica vs. horizonte, y **tiempo de entrenamiento vs. métrica**
(frente de Pareto entre trials de una búsqueda: cuánto cuesta cada punto de KGE).

**Selección de campeón**: por métrica en **VAL** (default `val/kge/mean`), nunca por TEST — TEST se
reporta una vez. La tesis lo declara así.

### 3.8. Inferencia diaria (Decisión #7)

`IssueDailyForecast(target="caudal")`:

1. `RefreshDataset` con el mismo protocolo de frescura de §3.6 (la cadena diaria de Databricks corre a
   las 04:30 Montevideo y termina en `Export_Gold_Snapshot`, así que el paso 3 normalmente no dispara nada).
2. Resuelve device (Decisión #6) y carga el campeón (`run_id` → `model/`, `preprocess/pipeline.pkl`,
   `features/spec.json`) — **exactamente** los artefactos del run, nada se recalcula distinto.
3. `AsOfPolicy`: `as_of` = último día con todos los inputs requeridos no nulos tras la imputación
   permitida; loguea `data_lag_days = hoy − as_of` (la cola de Gold tiene días con nivel sin caudal).
4. Predice t+1…t+7, t+14 respecto de `as_of`; guarda `Forecast` en SQLite + `data/forecasts/*.parquet`;
   loguea un run corto en el experimento `daily_forecast` (tags: `as_of`, `dataset_delta_version`,
   `champion_run_id`, `device`, procedencia del código) **con sus tiempos**: `time/dataset_refresh_s`,
   `time/model_load_s`, `time/preprocess_s`, `time/predict_s`, `time/total_s` (§3.12).
5. Opcional (flag): publica el parquet al Volume `weather.raw.gold_export_volume/forecasts/` para que
   Databricks lo pueda consumir después (tabla Delta = fase posterior, no en esta entrega).

Se programa con **Task Scheduler** (mismo mecanismo que los backfills), a las 06:30 Montevideo. La UI
"Pronóstico de hoy" muestra el abanico t+1…t+14, la serie observada reciente y el **backtest móvil**: cada
día que llega un observado nuevo se compara contra lo que se predijo (`BacktestRecent`).

### 3.9. Frontend (React)

Stack mínimo: **Vite + React + TypeScript + React Router + TanStack Query + Recharts**. Sin gestor de
estado global (TanStack Query cubre el cache de servidor). Estilo: CSS modules + tokens propios (sin
framework pesado). Build estático servido por FastAPI en `/`; en desarrollo, Vite con proxy a `/api`.

| Página | Qué muestra | Endpoints |
| --- | --- | --- |
| **Búsquedas** | Búsquedas (runs padre) y sus trials: modelo, estrategia, split, `train_start`, dataset pineado, métricas clave por horizonte, **tiempo total y por trial**, estado. Filtros y orden. | `GET /api/searches`, `GET /api/runs?…` |
| **Run** | Config, tags (dataset, procedencia con link a GitHub, hardware), métricas por horizonte (tabla + gráfico), **panel de tiempos** (descarga, preprocesamiento, entrenamiento total/por epoch, evaluación, inferencia), curva de pérdida, hidrograma TEST, artefactos, cobertura de splits, botón "promover a campeón". | `GET /api/runs/{id}`, `GET /api/runs/{id}/series/{name}`, `POST /api/champions` |
| **Comparar** | N runs seleccionados: métrica vs. horizonte, **tiempo vs. métrica**, tabla comparativa, diff de configs. | `GET /api/runs/compare?ids=` |
| **Lanzar** | Formulario desde un YAML de `configs/experiments/` (editable), cola local de jobs con log en vivo. | `POST /api/jobs`, `GET /api/jobs/{id}/log` (SSE) |
| **Pronóstico de hoy** | Abanico t+1…t+14 del campeón, `as_of`, `data_lag_days`, device, backtest reciente, historial de pronósticos. | `GET /api/forecasts/latest`, `GET /api/forecasts/backtest` |
| **Datasets** | Versiones del snapshot (delta, sha, filas, rango), cobertura por columna y por año, grupos de features, transforms disponibles. | `GET /api/datasets`, `GET /api/features` |
| **Research** | Biblioteca: subir PDF, metadatos, tags, notas por sección, vínculos a Decisiones y runs, exportar BibTeX. | `GET/POST /api/research/documents`, `PUT …/notes`, `POST /api/research/export-bib` |

### 3.10. Research (Decisión #3)

* `Document`: `slug`, `title`, `authors`, `year`, `venue`, `doi/url`, `type` (paper | tesis | informe |
  plantilla), `tags`, `file` (ruta en `rio_search/research/documents/`), `added_at`.
* `Note`: por sección — *metodología*, *modelos*, *ventanas/splits*, *métricas*, *resultados*, *qué me llevo* —
  en Markdown, con `links` a `Decisión NNN` y a `run_id` de MLflow.
* Persistencia **versionable y legible**: `rio_search/research/catalog/<slug>.yaml` + `rio_search/research/notes/<slug>.md`;
  los PDF en `rio_search/research/documents/` quedan fuera de git (allowlist para lo propio). Sin base de datos: el
  repo es la base.
* `ExportBibtex` escribe `rio_search/thesis/common/references.bib` (una entrada por documento, clave = `slug`).
  La tesis cita con `\cite{slug}`; la trazabilidad "paper → decisión → experimento → capítulo" queda cerrada.

### 3.11. Tesis LaTeX (Decisión #8)

* Va **inmediatamente después de Research** (Fase 8). Primer paso de la fase: **pedir al usuario el
  trabajo ya presentado con formato validado** (lo coloca en `rio_search/research/templates/`), extraer clase,
  preámbulo, portada y estilo de bibliografía, y replicarlos en `rio_search/thesis/common/`.
* Dos documentos: `rio_search/thesis/proyecto/` (proyecto de tesis) y `rio_search/thesis/tesis/`; capítulos en archivos
  separados; `latexmk -pdf` (MiKTeX ya instalado); salida en `build/` (gitignored).
* Puente con MLflow: `rio-search thesis export --run <id> [--compare …]` genera `rio_search/thesis/figures/*.pdf` y
  `rio_search/thesis/tables/*.tex` (métricas por horizonte, comparaciones) desde artefactos reales; cada figura lleva
  el `run_id` en un comentario LaTeX.
* El capítulo de metodología se escribe **desde `decisions.md`**: cada decisión relevante (018, 019,
  021, 033, 038…) se cita como justificación.

### 3.12. Tiempos: qué se mide y dónde queda (Decisiones #13 y #14)

El tiempo **no limita nada** (sin presupuesto, sin `max_time`, early stopping sólo por paciencia) pero
**se registra todo**: es un resultado de la tesis (costo computacional de cada metodología), no
telemetría. Reglas:

* Un `Stopwatch` de dominio (puerto) implementado con `time.perf_counter()`; en CUDA llama a
  `torch.cuda.synchronize()` antes de detener el reloj para que la ejecución asincrónica de la GPU no
  subestime el tiempo. Uso: `with stopwatch.track("train_total"): …`.
* Claves fijas, siempre en segundos, siempre bajo `time/` — las mismas en todos los runs para que se
  puedan comparar entre búsquedas, modelos y máquinas:

| Ámbito | Métricas `time/*` | Dónde |
| --- | --- | --- |
| Descarga del dataset | `dataset_refresh_s` y sub-pasos `dataset_gold_version_s`, `dataset_manifest_s`, `dataset_export_job_s` (0 si no disparó), `dataset_download_s`, `dataset_verify_s` | run padre (búsqueda) e inferencia |
| Preprocesamiento | `preprocess_s` (transforms + imputación + escalado + ventaneo) | trial |
| Entrenamiento | `train_total_s`, `train_epoch_s` (por `step=epoch`), `train_to_best_epoch_s`, `train_epochs`, `train_samples_per_s` | trial (y nietos en `per_horizon`) |
| Evaluación | `eval_val_s`, `eval_test_s` | trial |
| Inferencia sobre TEST | `predict_test_s`, `predict_per_sample_ms` | trial |
| Búsqueda de HP | `search_total_s`, `search_trials`, `search_trial_mean_s`, `search_trial_max_s`, `search_overhead_s` (total − suma de trials) | run padre |
| Inferencia diaria | `dataset_refresh_s`, `model_load_s`, `preprocess_s`, `predict_s`, `total_s` | run en `daily_forecast` |
| Registro de modelo | `model_log_s` (subida de artefactos a Databricks) | trial |

* Además: tags `started_at` / `ended_at` (ISO, UTC) en cada run, y el **hardware** que produjo los
  tiempos (`device`, `device_name`, `cuda_version`, `torch_version`, `cpu`, `ram_gb`, `hostname`) — sin
  eso un tiempo no se puede comparar entre la RTX 3060 y una Mac.
* Artefacto `timings/timings.json` con el desglose completo (incluye tiempos por epoch y por trial), para
  la tesis y para el panel de tiempos de la UI.
* La UI muestra los tiempos en cada run, en la lista de búsquedas y en Comparar (tiempo vs. métrica).

### 3.13. Procedencia del código (Decisión #11)

Sí, es factible: MLflow ya setea `mlflow.source.git.commit` / `mlflow.source.git.branch` cuando el
proceso corre dentro de un repo git; Rio_Search lo hace explícito y completo:

* **Tags**: `rio_search.git_sha` (referencia durable), `git_branch`, `git_remote`, `git_dirty`
  (`true` si hay cambios sin commitear en `rio_search/`), `github_url`
  (`https://github.com/JoacoTschopp/rio-uruguay-hydro-pipeline/tree/<sha>/rio_search`).
* **Artefactos `code/`**: `uncommitted.patch` (`git diff HEAD -- rio_search/`, vacío si el árbol está
  limpio), `package.zip` (snapshot del paquete `rio_search/` y de la config, ~cientos de KB), y el
  modelo se loguea con `code_paths=["rio_search"]` para que cargue solo desde MLflow sin el repo.
* **Política**: `provenance.require_clean_git: false` por defecto (exploración: el patch cubre la
  diferencia); `true` para corridas que van a la tesis — la búsqueda se niega a arrancar con árbol
  sucio, así cada número del documento apunta a un commit que existe en GitHub.
* La rama es comodidad para navegar; el **SHA** es lo que se cita. La UI linkea a GitHub por SHA.

---

## 4. Contratos clave

### 4.1. Config de experimento (YAML)

```yaml
# configs/experiments/bilstm_baseline_v1.yaml
name: bilstm_baseline_v1
description: Baseline BiLSTM, caudal, multi-output, ventana 2008->, CPTEC + estado hidrológico.

dataset:
  source: gold_training_dataset_v0
  refresh: ensure_latest     # ensure_latest | volume_as_is | offline (Decisión #10, §3.6)
  version: latest            # o "delta-263": falla si lo descargado no coincide (reproducción exacta)
  target: caudal             # caudal | nivel
  horizons: [1, 2, 3, 4, 5, 6, 7, 14]

search:                      # opcional: sin este bloque la búsqueda tiene un único trial
  strategy: random           # grid | random | tpe (Optuna)
  n_trials: 40               # sin límite de tiempo (Decisión #13)
  objective: val/kge/mean
  space:
    sequence.lookback_days: [30, 60, 90, 120]
    model.params.hidden_size: [32, 64, 128, 256]
    model.params.num_layers: [1, 2, 3]
    training.optimizer.lr: {log_uniform: [0.0001, 0.01]}
    split.train_window.start: ["2000-01-01", "2008-01-01"]

provenance:
  require_clean_git: false   # true para corridas que van a la tesis (Decisión #11, §3.13)

split:
  policy: rolling_365        # rolling_365 | calendar_year
  embargo_days: 14
  train_window:
    start: 2008-01-01        # o  years: 10

features:
  groups: [caudal_estado, nivel_estado, caudal_agregado_alta_frontera, cptec_grid]
  exclude: []
  experimental_transforms:
    - {name: clip, columns: [caudal_agregado_alta_frontera_m3s], max: 50000, version: 1}
    - {name: log1p, columns: ["caudal_*", "caudal_agregado_alta_frontera_m3s"], version: 1}
    - {name: doy_cyclic, version: 1}
  imputation: {method: ffill_median, max_ffill_days: 3}
  scaling: standard

sequence:
  lookback_days: 60

model:
  name: bilstm
  horizon_strategy: multi_output   # multi_output | per_horizon
  params: {hidden_size: 64, num_layers: 2, dropout: 0.2}

training:
  max_epochs: 1000           # techo de seguridad, no un presupuesto: corta el early stopping (Decisión #13)
  batch_size: 64
  optimizer: {name: adam, lr: 0.001, weight_decay: 0.0}
  loss: mse                  # mse | mae | huber
  early_stopping: {monitor: val/loss, patience: 25}
  grad_clip: 1.0
  seed: 42
  device: auto               # auto | cuda | mps | cpu

tracking:
  experiment: /Users/joaquintschopp@gmail.com/rio_search/bilstm
  tags: {thesis_chapter: baseline}
  register_model: false
```

### 4.2. CLI (`rio-search`)

```
rio-search databricks init-schema            # CREATE SCHEMA IF NOT EXISTS weather.ml (Fase 0)
rio-search datasets refresh [--mode ensure_latest|volume_as_is|offline] [--force]
rio-search datasets describe [--version delta-263]
rio-search search run configs/experiments/bilstm_baseline_v1.yaml [--dry-run] [--require-clean-git]
rio-search search list [--experiment bilstm] [--metric val/kge/mean] [--with-times]
rio-search search show <search_run_id>       # trials, métricas y tiempos de una búsqueda
rio-search champions set --run <run_id> --target caudal
rio-search predict run [--as-of 2026-08-23] [--publish]
rio-search research add <pdf> --title … --authors … --year …
rio-search research export-bib
rio-search thesis export --run <run_id> [--compare <run_id> …]
rio-search api serve [--port 8000]
```

### 4.3. Reproducibilidad (lo que todo run debe permitir)

Dado un `run_id`: recuperar `config/experiment.yaml`, `dataset_delta_version` + `sha256`, `git_sha` (+
`code/uncommitted.patch` si el árbol estaba sucio), `uv.lock`, `seed` y `device`, hacer `git checkout
<sha>` y volver a correr `rio-search search run --dataset-version delta-<N>` obteniendo métricas iguales
(CPU, determinismo estricto) o dentro de una tolerancia documentada (GPU). Los tiempos **no** se exigen
reproducibles: se comparan sólo entre runs con el mismo hardware (tags de §3.12).

---

## 5. Fases

Cada fase cierra con su test (offline con `pytest` o contra Databricks/MLflow real cuando corresponda),
su entregable versionado y su Decisión si introduce criterio nuevo — mismo "Criterio de avance" que
`roadmap.md` §4. Estimaciones en días de trabajo efectivo.

### Fase 0 — Cimientos

**Estimación:** ≈ 1 día · **Depende de:** nada

- [ ] Rama `feature/rio-search`; árbol de §3.1; `.gitignore` (`rio_search/backend/.venv`, `rio_search/backend/data/`, `rio_search/frontend/node_modules`, `rio_search/research/documents/`, `rio_search/thesis/**/build/`).
- [ ] `rio_search/backend`: proyecto `uv` con Python 3.12, `torch` (índice CUDA 12.x en Windows; en macOS el wheel default trae MPS), **`polars`**, **`mlflow-skinny`**, `databricks-sdk`, `pyarrow`, `numpy`, `pydantic`, `pyyaml`, `scikit-learn`, `optuna`, `fastapi`, `uvicorn`, `typer`, `pytest`, `ruff`. **Sin pandas**: regla `banned-api` en `ruff` + test `test_no_pandas_in_env` que falla si `import pandas` funciona en el entorno.
- [ ] `rio_search/frontend`: `npm create vite@latest` (React + TS), React Router, TanStack Query, Recharts; página vacía que consume `GET /api/health`.
- [ ] Módulo `device` con `resolve()` y tests (CUDA presente / MPS simulado / CPU). Módulo `timing` (`Stopwatch` con `cuda.synchronize`) y `provenance` (git sha/rama/remote/dirty/patch) con tests.
- [ ] **Portar la descarga del snapshot** (`gold_snapshot_sync.py`, Decisión #10) desde `export_gold_dataset.py`, con el protocolo de frescura de §3.6 completo (versión de Gold por Statement API, `jobs submit` de `Export_Gold_Snapshot`, descarga por SDK, `sha256`). Tests offline con SDK falso; primera corrida real: **el manifest debe pasar de 71 a 83 columnas** solo, sin intervención manual.
- [ ] `rio-search databricks init-schema`: `CREATE SCHEMA IF NOT EXISTS weather.ml` (Decisión #12).
- [ ] Conectividad MLflow con `mlflow-skinny`: run `smoke` en `/Users/joaquintschopp@gmail.com/rio_search/smoke` con param, métrica, `time/*`, tags de procedencia y hardware, artefacto `code/`, `MetaDataset` y un modelo de juguete logueado con `mlflow.pytorch.log_model(code_paths=…)` — verifica que skinny alcanza sin pandas.

**Criterio de cierre:** `pytest` en verde (incluido `test_no_pandas_in_env`); `rio-search datasets refresh`
deja el parquet con 83 columnas y sha igual al manifest tras disparar `Export_Gold_Snapshot` por sí solo;
schema `weather.ml` existe; run `smoke` visible en Databricks con tiempos, procedencia y modelo; `npm run
dev` muestra la respuesta de `/api/health`.

### Fase 1 — Contexto Datasets

**Estimación:** ≈ 2-3 días · **Depende de:** Fase 0

- [ ] `DatasetVersion` desde `manifest.json`; `GoldParquetDatasetRepository` en Polars sobre `gold_snapshot_sync` (Fase 0); `RefreshDataset` como primer paso obligatorio de `RunSearch`, con sus tiempos.
- [ ] `configs/feature_groups.yaml` + validación contra columnas reales (falla explícita si Gold cambia).
- [ ] Transforms experimentales como expresiones Polars (`log1p`, `doy_cyclic`, `clip`, `ratio`, `diff`, `rolling`) con versión y docstring de promoción.
- [ ] Imputación y escalado como expresiones ajustadas sólo con estadísticos de TRAIN; reporte de % imputado por columna y split.
- [ ] `SplitPolicy` `rolling_365` y `calendar_year` con `embargo_days`; `anchor` por horizonte y por estrategia.
- [ ] `SequenceBuilder` (lookback → tensores) y `TargetBuilder` (`multi_output` / `per_horizon`).
- [ ] `DescribeDataset`: cobertura por columna/año/split (alimenta la página Datasets).

**Tests:** dataset sintético (patrón `test_export_gold_dataset.py`): no hay fechas de TRAIN posteriores al
inicio de VAL − embargo; ningún target de VAL cae dentro de los inputs de TEST; el escalador no ve VAL/TEST;
las ventanas no cruzan el `anchor`; `calendar_year` y `rolling_365` dan los rangos esperados.
**Criterio de cierre:** `rio-search datasets describe` sobre el parquet real imprime cobertura por split para
`bilstm_baseline_v1.yaml` sin errores.

### Fase 2 — Evaluación, tracking y baselines naïve

**Estimación:** ≈ 1-2 días · **Depende de:** Fase 1

- [ ] Métricas de §3.7 como funciones puras + tests con valores conocidos (NSE = 1 en predicción perfecta, KGE de la media = −0,41, etc.).
- [ ] `MlflowDatabricksTracking`: jerarquía búsqueda → trial (→ horizonte), tags, params, métricas jerárquicas, **`time/*` con las claves fijas de §3.12**, `timings/timings.json`, procedencia (§3.13), `MetaDataset`.
- [ ] Adaptadores `persistence`, `climatology` (por día del año sobre TRAIN), `seasonal_naive`.
- [ ] `RunSearch` completo para modelos naïve (sin entrenamiento) → primeras búsquedas reales, cada una con su descarga del dataset al inicio.

**Criterio de cierre:** 3 búsquedas naïve en `/…/rio_search/baselines` con métricas por horizonte para `val`
y `test`, `time/dataset_refresh_s` y `time/eval_*` registrados, tags de procedencia y hardware, artefacto
`code/`; `predictions/test.parquet` descargable; skill de persistencia = 0 por construcción.

### Fase 3 — BiLSTM baseline (PyTorch)

**Estimación:** ≈ 3-4 días · **Depende de:** Fase 2

- [ ] `BaseTorchAdapter`: tensores desde Polars (`to_torch`), bucle de entrenamiento con early stopping sobre VAL (por paciencia, **nunca por tiempo**, Decisión #13), grad clipping, seed, checkpoint del mejor epoch, curvas y `time/train_epoch_s` a MLflow por epoch, `train_to_best_epoch_s`, `train_samples_per_s`.
- [ ] `BiLSTMAdapter` (LSTM bidireccional sobre la ventana pasada → cabeza densa de `n_outputs`).
- [ ] `per_horizon` en la aplicación (trial + 8 runs por horizonte) y `multi_output`.
- [ ] **Búsqueda de hiperparámetros** (`search:` del YAML): `grid`, `random` y `tpe` (Optuna, sin pandas); cada trial un run hijo; `time/search_*` en el padre; sin límite de trials por reloj.
- [ ] `mlflow.pytorch.log_model` con *signature* y `code_paths`; `preprocess/pipeline.pkl`; checkpoint en CPU; `time/model_log_s`.
- [ ] Registro en `weather.ml.rio_search_bilstm` (`register_model: true`) → **revisión con el usuario tras la primera corrida registrada** (Decisión #12): nombre, aliases, política de versiones.
- [ ] Búsqueda baseline desde YAML versionado: espacio de §4.1 (`lookback`, `hidden_size`, `num_layers`, `lr`, `train_start`) × ambas estrategias de horizonte; dura lo que dure.

**Criterio de cierre:** el BiLSTM supera a persistencia en TEST para t+1…t+7 (skill > 0) **o** se documenta
por qué no; ambas estrategias de horizontes corridas y comparables; cada trial con sus tiempos completos y
el padre con `time/search_total_s`; re-corrida con el mismo seed en CPU reproduce las métricas; modelo
registrado en `weather.ml` y revisión hecha; Decisión con los resultados de la búsqueda (incluido el costo
en tiempo de cada configuración).

### Fase 4 — Backend API

**Estimación:** ≈ 2 días · **Depende de:** Fase 3

- [ ] FastAPI con los endpoints de §3.9; cliente MLflow con cache de lectura en SQLite (la UI no debe pegarle a Databricks en cada render).
- [ ] `SubprocessJobRunner`: cola local, un job a la vez (comparte el `lock.py` de `ana_historic_backfill`), log en vivo por SSE.
- [ ] OpenAPI documentada; tests con `TestClient` y `TrackingPort` falso.

**Criterio de cierre:** `rio-search api serve` + `curl /api/runs` devuelve los runs de la Fase 3 con sus
tiempos; una búsqueda lanzada desde `POST /api/jobs` descarga el dataset, termina y aparece en MLflow.

### Fase 5 — UI React

**Estimación:** ≈ 3-4 días · **Depende de:** Fase 4

- [ ] Páginas Búsquedas, Run (con panel de tiempos y procedencia), Comparar, Lanzar, Datasets (§3.9). "Pronóstico de hoy" y Research se agregan en sus fases.
- [ ] Gráficos: métrica vs. horizonte, tiempo vs. métrica, hidrograma, curva de pérdida (JSON de `series/` y `timings/`).
- [ ] Build estático servido por FastAPI.

**Criterio de cierre:** navegación completa contra el backend real; comparar ≥ 3 runs de la Fase 3 en pantalla;
`npm run build` + `rio-search api serve` sirve la app en `http://127.0.0.1:8000`.

### Fase 6 — Inferencia diaria

**Estimación:** ≈ 2-3 días · **Depende de:** Fases 3 y 4

- [ ] `PromoteChampion` (por `val/kge/mean`, alias UC + SQLite) y `IssueDailyForecast` (§3.8) con `AsOfPolicy`.
- [ ] `rio-search predict run`; tarea de Task Scheduler a las 06:30 Montevideo (`scheduler/register_tasks.ps1`, mismo patrón que ANA).
- [ ] `BacktestRecent`; página "Pronóstico de hoy".
- [ ] Publicación opcional al Volume (`--publish`).

**Criterio de cierre:** una corrida real end-to-end disparada por Task Scheduler; la UI muestra el pronóstico con
`as_of`, `data_lag_days`, `dataset_delta_version`, `champion_run_id`, `device` y **sus tiempos**
(`dataset_refresh_s`, `model_load_s`, `predict_s`, `total_s`); re-ejecución manual en CPU (`--device cpu`)
reproduce el mismo pronóstico y registra sus propios tiempos.

### Fase 7 — Research

**Estimación:** ≈ 2 días · **Depende de:** Fase 5

- [ ] Dominio `research` + `YamlCatalog` + `FileSystemDocumentStore` + `BibtexExporter`.
- [ ] Endpoints y página Research (subir PDF, editar metadatos/notas/tags, vincular a Decisión y run, exportar bib).
- [ ] `rio_search/research/README.md` con la convención de slugs y secciones de nota.

**Criterio de cierre:** 3 documentos cargados desde la UI; `rio_search/thesis/common/references.bib` generado; un `.tex`
mínimo que los cita compila con `latexmk`. **Al cerrar esta fase se le pide al usuario el trabajo con formato
validado** para `rio_search/research/templates/` (entrada de la Fase 8).

### Fase 8 — Tesis LaTeX

**Estimación:** ≈ 1-2 días de armado (la escritura es continua) · **Depende de:** Fase 7 y del modelo aportado por el usuario

- [ ] **Solicitar y recibir el modelo LaTeX** (`rio_search/research/templates/`); extraer clase/preámbulo/portada/bibliografía a `rio_search/thesis/common/`.
- [ ] `rio_search/thesis/proyecto/` y `rio_search/thesis/tesis/` con capítulos separados; `latexmk`; `build/` ignorado.
- [ ] `rio-search thesis export` (figuras y tablas desde runs reales, con `run_id` en comentario).
- [ ] Esqueleto del capítulo de metodología referenciando `decisions.md`.

**Criterio de cierre:** ambos documentos compilan con el formato del modelo; al menos una figura y una tabla
generadas desde un run real de MLflow.

### Fase 9 — Extensibilidad probada y promoción a Gold

**Estimación:** ≈ 2-3 días · **Depende de:** Fase 6

- [ ] Segundo modelo no-DL (`ridge` con lags o `lightgbm`) **y/o** un segundo DL (TCN o GRU) agregados sólo con un adaptador + YAML.
- [ ] Promover 1-2 transforms experimentales que hayan demostrado valor (p. ej. `clip` del agregado, `lluvia / station_count`) a `ETL_Gold_Training_Dataset_v0.ipynb` con su Decisión; nueva versión de dataset; re-correr el baseline sobre ella.
- [ ] Documento `rio_search/docs/como_agregar_un_modelo.md`, validado por haberlo hecho.

**Criterio de cierre:** el modelo nuevo entra sin tocar `domain/` ni `application/`; la comparación multi-modelo
se ve en la UI; la Decisión de promoción está registrada.

### Hitos posteriores (fuera de esta entrega, ya previstos por el diseño)

* **Llegada de las features de pronóstico** (roadmap Fase 4): grupo `forecast`, nueva `DatasetVersion`,
  experimentos "con vs. sin pronóstico" — resultado central de la tesis.
* Tabla Delta de pronósticos en Databricks y su validación en `06_Quality`.
* Extracción asistida por LLM en Research (adaptador opcional, Decisión #3).
* Segundo punto de predicción, si la Decisión 018 se revierte: el dominio ya modela `punto_prediccion`.

**Total estimado:** ≈ 20-27 días efectivos de trabajo (el tiempo de máquina de las búsquedas no cuenta: dura
lo que dure, Decisión #13). Orden recomendado: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9. Las Fases 4-5
(API/UI) pueden solaparse con la búsqueda de la Fase 3 mientras la GPU trabaja.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
| --- | --- |
| El parquet local queda desactualizado respecto de Gold (hoy: 71 vs. 83 columnas) | Descarga obligatoria al iniciar cada búsqueda con el protocolo de frescura de §3.6 (verifica la versión Delta de Gold y regenera el snapshot si está atrás); la app falla explícitamente si las columnas del catálogo no existen. |
| `mlflow-skinny` no cubre algún camino (p. ej. `log_model` o `MetaDataset`) sin pandas | El run `smoke` de la Fase 0 ejercita exactamente esos caminos; si alguno falla, se aísla en un adaptador y se registra la Decisión — pandas no entra igual. |
| El paso 3 del protocolo (`Export_Gold_Snapshot` ad hoc) consume serverless y tarda minutos | Solo dispara cuando el manifest está atrás de Gold (normalmente nunca: la cadena diaria ya lo exporta a las 04:30); el tiempo queda registrado en `time/dataset_export_job_s`; `volume_as_is` para saltarlo a propósito. |
| Tiempos no comparables entre máquinas (RTX 3060 vs. Mac) | Tags de hardware obligatorios en cada run; la UI y la tesis sólo comparan tiempos con el mismo `device_name`. |
| Fuga temporal sutil (targets de VAL dentro de inputs de TEST; escalador con datos futuros) | `embargo_days`; escalador ajustado sólo con TRAIN; tests de no-fuga en Fase 1; verificación adicional de que la persistencia da skill 0. |
| Outliers del agregado (823.897 m³/s) distorsionan el escalado | `clip`/`winsor` experimental + `robust` scaling; promoción a Gold en Fase 9. |
| Temperatura por estación ausente 2000-2005 | `train_window.start` configurable; SAMeT (100 %) como sustituto; imputación acotada y reportada. |
| Huecos del target en TEST (26 días de caudal en 2026) | Métricas sobre observados + cobertura reportada; `calendar_year` (TEST = 2025) como política alternativa cuando importe. |
| MLflow desde local: auth/latencia | `databricks://<perfil>` con el CLI ya válido; cache de lectura en SQLite; la UI nunca bloquea por red. |
| Instalación de `torch` CUDA en Windows / MPS en macOS | `uv` con índice explícito por plataforma en `pyproject.toml`; `resolve()` cae a CPU y lo loguea, nunca aborta. |
| Un solo proceso pesado a la vez (GPU, CLI de Databricks) | `JobRunner` comparte `lock.py` con los backfills de ANA. |
| Las features de pronóstico llegan a mitad de camino | Versionado de dataset + grupo `forecast` reservado: no rompe experimentos previos. |

---

## 7. Convenciones

* **Código en inglés**, vocabulario de dominio en español cuando nombra columnas o conceptos de Gold
  (`caudal`, `nivel`, `horizonte`, `punto_prediccion`), igual que el resto del repo. Docs y UI en español.
* **Polars, nunca pandas** (Decisión #9): `pandas` no está en `pyproject.toml`, `ruff` lo bloquea como
  import (`flake8-tidy-imports.banned-api`) y `test_no_pandas_in_env` falla si alguna dependencia lo
  arrastra. Por eso `mlflow-skinny` y no `mlflow`.
* Un YAML por experimento, versionado en `configs/experiments/`; nunca se edita un YAML ya corrido — se
  crea `_v2`.
* Toda búsqueda descarga el dataset actual al arrancar (Decisión #10); todo run registra tiempos con las
  claves de §3.12 y procedencia con las de §3.13. Un run sin `time/*` o sin `git_sha` es un bug.
* Ningún secreto en el repo: MLflow y Databricks usan el perfil del CLI.
* Tests offline por defecto; los que tocan MLflow/Databricks real se marcan `@pytest.mark.integration`.
* Cada fase cierra con Decisión en `decisions.md` cuando fija un criterio nuevo (métrica de selección de
  campeón, política de embargo, promoción de una feature, etc.).
* `ruff` para formato y lint del backend; `eslint` + `prettier` del template de Vite para el frontend.

---

## 8. Dependencias del usuario

| Cuándo | Qué se necesita |
| --- | --- |
| Fase 3 | **Revisar `weather.ml` después de la primera corrida registrada** (Decisión #12): nombre del modelo, aliases, política de versiones. |
| Cierre de la Fase 7 | El **trabajo presentado con formato validado** (LaTeX) en `rio_search/research/templates/`, insumo de la Fase 8. |
