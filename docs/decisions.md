# Decisiones técnicas y de investigación

## 1. Objetivo del documento

Este documento registra las decisiones técnicas y metodológicas tomadas durante la construcción del dataset de tesis.

El objetivo es mantener trazabilidad sobre por qué se eligieron ciertos enfoques, fuentes, herramientas o criterios de modelado.

Cada decisión debería actualizarse cuando cambie el contexto o aparezca nueva evidencia.

---

## Decisión 001: Mantener Databricks como entorno principal de procesamiento

### Estado

`Aceptada`

### Contexto

El pipeline actual ya cuenta con jobs implementados en Databricks para ingesta diaria y carga en capa Bronze.

A partir del estado actual, existen procesos asociados a:

* estaciones ANA;
* niveles hidrométricos ANA;
* temperatura de aeropuertos en Brasil.

Los jobs observados siguen el patrón:

`notebook de extracción diaria -> notebook de ETL Bronze`

### Decisión

Se mantiene Databricks como entorno principal de procesamiento para la construcción inicial del dataset de tesis.

### Justificación

Databricks ya está configurado y ejecutando procesos diarios. Además, permite trabajar con una arquitectura por capas compatible con el enfoque Medallion:

`Landing -> Bronze -> Silver -> Gold`

Migrar todo a PostgreSQL o montar un entorno Spark local completo en esta etapa podría demorar la construcción del dataset entrenable.

### Consecuencias

* El procesamiento principal seguirá corriendo en Databricks.
* El repositorio deberá documentar claramente notebooks, jobs, tablas y rutas.
* El código deberá tender progresivamente a ser modular y versionable.
* PostgreSQL no se descarta, pero no será el almacén principal del dataset histórico en esta primera etapa.

---

## Decisión 002: Priorizar `training_dataset_v0` antes de la incrementalidad completa

### Estado

`Aceptada`

### Contexto

El proyecto tiene dos objetivos relacionados:

1. Construir un dataset entrenable para la tesis.
2. Construir un pipeline incremental diario que permita continuidad en el tiempo e incorporación de nuevas fuentes.

Ambos objetivos son importantes, pero resolverlos simultáneamente puede generar dispersión.

### Decisión

La prioridad inicial será construir una primera versión entrenable y reproducible del dataset:

`gold.training_dataset_v0`

La incrementalidad diaria completa se abordará después de validar la estructura del dataset.

### Justificación

La tesis requiere primero una base estable para entrenamiento, evaluación y análisis. Sin una primera tabla Gold entrenable, es difícil evaluar modelos, identificar problemas de datos o justificar nuevas fuentes.

### Consecuencias

* No se incorporarán nuevas fuentes si bloquean la construcción de `training_dataset_v0`.
* La automatización incremental se diseñará luego de validar el dataset inicial.
* El foco inicial estará en cerrar una versión usable, aunque no sea definitiva.

---

## Decisión 003: Usar granularidad diaria

### Estado

`Aceptada`

### Contexto

Las fuentes candidatas tienen distintas frecuencias temporales. Algunas pueden ser subdiarias, otras diarias y otras derivadas de grillas o pronósticos.

Para la tesis se requiere una unidad de observación consistente y manejable.

### Decisión

El dataset de entrenamiento se construirá con granularidad diaria.

El grano lógico será:

`fecha + punto_prediccion`

### Justificación

La granularidad diaria permite integrar fuentes heterogéneas con menor complejidad inicial. También resulta adecuada para horizontes predictivos de 1 a 14 días.

### Consecuencias

* Las fuentes subdiarias deberán agregarse a nivel diario.
* Se deberán definir reglas explícitas de agregación.
* Algunas señales de corto plazo podrían perderse frente a una granularidad horaria, pero se gana estabilidad y simplicidad.
* La granularidad horaria podría evaluarse en una etapa posterior si el dataset diario demuestra viabilidad.

---

## Decisión 004: Modelar horizontes de predicción entre 1 y 14 días

### Estado

`Propuesta`

### Contexto

El objetivo predictivo definido es estimar el nivel del río Uruguay en los próximos 1 a 14 días.

Todavía resta definir si se construirán todos los horizontes diarios o un subconjunto representativo.

### Decisión propuesta

Construir inicialmente targets para horizontes seleccionados:

* 1 día;
* 3 días;
* 7 días;
* 14 días.

Luego evaluar si conviene extender a todos los horizontes entre 1 y 14 días.

### Justificación

Los horizontes 1, 3, 7 y 14 días permiten cubrir corto, mediano y mayor plazo sin multiplicar excesivamente la complejidad inicial.

### Consecuencias

* El dataset inicial tendrá varias columnas target.
* La evaluación de modelos deberá reportarse por horizonte.
* En una etapa posterior podría definirse un modelo por horizonte o un único modelo multi-horizonte.

---

## Decisión 005: Definir dos puntos críticos de predicción

### Estado

`Propuesta`

### Contexto

El objetivo inicial contempla dos zonas de interés:

1. Frontera Brasil/Argentina.
2. Zona aguas abajo asociada a la represa de Salto Grande.

Estos puntos representan ubicaciones hidrológicamente relevantes para la predicción del nivel del río Uruguay.

### Decisión propuesta

La primera versión del dataset incluirá dos puntos críticos de predicción.

### Justificación

Trabajar con dos puntos permite comparar comportamiento aguas arriba y aguas abajo sin ampliar demasiado el alcance inicial.

### Consecuencias

* La clave lógica del dataset será `fecha + punto_prediccion`.
* Se deberá definir con precisión qué estación o conjunto de estaciones representa cada punto.
* Podrá evaluarse si conviene entrenar un modelo único con `punto_prediccion` como variable o modelos separados por punto.

---

## Decisión 006: Usar enfoque Medallion

### Estado

`Aceptada`

### Contexto

El pipeline actual ya se organiza parcialmente mediante una lógica de extracción diaria y carga Bronze.

La construcción del dataset requiere separar claramente datos crudos, datos limpios y datos analíticos.

### Decisión

Se utilizará una arquitectura por capas:

`Landing -> Bronze -> Silver -> Gold`

### Justificación

Este enfoque permite separar responsabilidades:

* Landing conserva datos originales.
* Bronze estructura datos crudos.
* Silver normaliza, limpia y alinea.
* Gold construye datasets listos para análisis y modelado.

### Consecuencias

* Cada fuente deberá tener una salida clara por capa.
* Las transformaciones deberán ser trazables.
* El dataset de tesis se construirá desde Gold.
* Será necesario documentar rutas, tablas y reglas de transformación.

---

## Decisión 007: No migrar todo a PostgreSQL en la etapa inicial

### Estado

`Aceptada`

### Contexto

Se evaluó la posibilidad de mudar el procesamiento o almacenamiento principal a PostgreSQL.

PostgreSQL puede ser útil para servir resultados o manejar datos relacionales, pero no necesariamente como base principal del histórico hidrometeorológico.

### Decisión

No se migrará todo el proyecto a PostgreSQL en la etapa inicial.

### Justificación

El pipeline ya se encuentra avanzado en Databricks y el objetivo urgente es construir el dataset entrenable. Migrar a PostgreSQL podría generar trabajo adicional sin resolver el bloqueo principal.

### Consecuencias

* PostgreSQL queda como opción futura para consumo, APIs, dashboards o catálogos auxiliares.
* El histórico principal seguirá gestionándose en Databricks/Delta.
* Se evita reescribir el pipeline antes de validar el dataset.

---

## Decisión 008: No montar Spark local como prioridad inicial

### Estado

`Aceptada`

### Contexto

Se evaluó la posibilidad de montar un entorno local o virtualizado con Spark para facilitar la interacción con herramientas de IA y desarrollo local.

### Decisión

No se priorizará el montaje de Spark local para la primera versión del dataset.

### Justificación

El esfuerzo principal debe estar en cerrar el dataset de tesis. Montar un ecosistema local completo podría consumir tiempo sin aportar directamente al entregable inicial.

### Consecuencias

* Databricks seguirá siendo el entorno de ejecución principal.
* El repositorio deberá mejorar su documentación y estructura para facilitar asistencia con IA.
* Podrán extraerse módulos reutilizables a futuro para facilitar ejecución local parcial.

---

## Decisión 009: Documentar antes de ampliar fuentes

### Estado

`Aceptada`

### Contexto

El proyecto tiene múltiples fuentes candidatas y existe riesgo de ampliar el alcance antes de consolidar lo existente.

### Decisión

Antes de incorporar nuevas fuentes, se documentará el estado actual del pipeline, fuentes, tablas y brechas.

### Justificación

La documentación permite recuperar continuidad, trabajar mejor con asistentes de IA y reducir decisiones repetidas.

### Consecuencias

* Se priorizan archivos de documentación en `docs/`.
* Cada nueva fuente debería tener justificación y estado documentado.
* El roadmap funcionará como guía para evitar dispersión.

---

## Decisión 010: Construir primero un dataset útil, no perfecto

### Estado

`Aceptada`

### Contexto

La tesis requiere avanzar hacia experimentación y resultados. Buscar un dataset completo desde el inicio puede retrasar indefinidamente el modelado.

### Decisión

La primera versión del dataset debe ser útil, entrenable y reproducible, aunque no incorpore todas las fuentes posibles.

### Justificación

Un dataset inicial permite entrenar modelos base, medir errores, detectar problemas y orientar mejoras futuras.

### Consecuencias

* `training_dataset_v0` podrá tener una cantidad limitada de fuentes.
* Las limitaciones se documentarán explícitamente.
* Las versiones posteriores podrán incorporar más fuentes y mejor calidad.

---

## Decisión 011: Ingesta de pronóstico ECMWF vía secret scope, portal ECMWF Data Stores, recorte en Silver

### Estado

`Aceptada`

### Contexto

Se incorporó al pipeline el pronóstico ECMWF (control forecast `cf` + determinístico `fc`, ver `data_sources.md` §7). Tres decisiones de diseño quedaron fijadas durante la implementación:

1. Las credenciales existentes en el proyecto (`USER_API_ANA`/`PASS_API_ANA`) se guardan en texto plano como `base_parameters` de los jobs en `databricks.yml`. Para las credenciales nuevas de ECMWF (`cdsapi_url`/`cdsapi_key`) se evaluó reproducir ese mismo patrón o usar un secret scope de Databricks.
2. A mitad de la implementación, el usuario cambió de portal: el ECMWF Web API legacy (`api.ecmwf.int`, paquete `ecmwfapi`, archivo `~/.ecmwfapirc`) tenía el token deshabilitado y fue reemplazado por el portal nuevo **ECMWF Data Stores** (`https://ecds.ecmwf.int`), que usa el paquete estándar `cdsapi` y el archivo `~/.cdsapirc`.
3. El diseño original recortaba al polígono exacto de las sub-cuencas ya en el landing/Bronze. El usuario corrigió esto explícitamente: el recorte real debe hacerse en Silver; Bronze debe conservar todo el *bounding box* de descarga sin recortar, y ese bounding box debe calcularse dinámicamente a partir de los límites reales del geojson (no un área fija grande), siempre en la resolución nativa más fina (0,25°).

### Decisión

* Las credenciales ECMWF (`cdsapi_url`, `cdsapi_key`) se guardan en el secret scope de Databricks `ecmwf`, accedidas vía `dbutils.secrets.get(...)` — no se reproduce el patrón de texto plano usado para ANA.
* La ingesta de `cf` usa `cdsapi` contra el dataset `tigge-forecasts` del portal `ecds.ecmwf.int`; `fc` sigue usando ECMWF Open Data (sin autenticación) por ser servicios independientes.
* El bounding box de descarga se calcula dinámicamente (`compute_download_area()`) a partir de `SIG/subcuencas_modelo.geojson`, y el recorte al polígono real (con buffer) se aplica únicamente en las tablas Silver (`ecmwf_forecast_fc_basin` / `_cf_basin`), nunca en Bronze.

### Justificación

Evitar reproducir un patrón de credenciales inseguro ya identificado como deuda técnica; adaptarse al cambio de portal real del proveedor en vez de mantener una integración con un servicio deshabilitado; y mantener la separación de responsabilidades del enfoque Medallion (Decisión 006) — Bronze como espejo fiel de lo descargado, Silver como capa de reglas de negocio (el recorte geográfico exacto es una regla de negocio, no un hecho crudo).

### Consecuencias

* Cualquier credencial nueva que se agregue al proyecto de aquí en más debería preferir un secret scope sobre texto plano en `base_parameters`.
* Las tablas Bronze de ECMWF (`ecmwf_forecast_fc`/`_cf`) contienen más filas que las Silver correspondientes (todo el bbox vs. solo los puntos dentro de las 3 sub-cuencas) — esto es esperado y no un bug.
* Si ECMWF vuelve a cambiar de portal o de paquete cliente, solo deberían verse afectados los notebooks de Landing (`Daily_ECMWF_FC`/`_CF`) y el secret scope, no Bronze/Silver.

---

## Decisión 012: Alcance de la reconstrucción histórica del pronóstico ECMWF (`cf`+`pf` desde 2006-10, `fc` fuera de alcance)

### Estado

`Aceptada`

### Contexto

Se planificó reconstruir el histórico del pronóstico ECMWF (ver `data_sources.md` §7.11) para tener series largas de precipitación pronosticada, útiles como features para el dataset de tesis. La intención inicial del usuario era cubrir desde el año 2000, priorizando avanzar desde el presente hacia atrás.

Al investigar las APIs reales se encontraron dos restricciones duras:

1. **`fc` (HRES determinístico, ECMWF Open Data)** no tiene archivo histórico: retiene solo ~12 corridas (2-3 días). Acceder a su histórico real requeriría un Service Agreement / acceso MARS distinto con ECMWF, fuera del acceso actual (`cdsapi` + Open Data) y fuera del alcance de este pipeline.
2. **`cf`/`pf` (TIGGE vía `cdsapi`/ECDS)** sí tienen archivo histórico, pero **desde octubre de 2006**, no desde 2000 (confirmado en la documentación oficial de ECMWF/TIGGE).

El usuario confirmó explícitamente, ante estas restricciones: reconstruir `cf` + `pf` (no `fc`) desde 2006-10 hasta hoy, aceptando que 2000–2006 queda fuera de alcance por limitación real de la fuente, no del pipeline.

### Decisión

* La reconstrucción histórica cubre únicamente `cf` y `pf`, ambos vía TIGGE/`cdsapi`, en el rango 2006-10-01 → presente.
* `fc` histórico queda explícitamente fuera de alcance de este pipeline. Si en el futuro se necesita, es un proyecto aparte (gestión de acceso MARS/Service Agreement con ECMWF), no una extensión de los notebooks actuales.
* Para no generar miles de requests individuales (uno por día) contra la cola de TIGGE/ECDS y arriesgar el token de la cuenta, los requests históricos se agrupan por lotes de fechas: 1 año calendario por request para `cf`, 1 mes calendario por request para `pf` (el multiplicador de 50 miembros del ensemble obliga a lotes más chicos). Ver `Historic_ECMWF_CF.ipynb` / `Historic_ECMWF_PF.ipynb`.
* El job `ECMWF_Forecast_Historic_Backfill` no tiene schedule (se dispara a mano) y encadena `cf` y `pf` de forma estrictamente secuencial, para nunca competir por la cola de la API al mismo tiempo que `ECMWF_Forecast_Daily_Incremental` ni entre sí.

### Justificación

Prometer una cobertura que la fuente no puede dar (2000–2006) generaría una limitación silenciosa o datos inexistentes más adelante en el proceso. Es preferible documentar el límite real ahora. Agrupar por lotes en vez de por día es la única forma razonable de traer ~20 años de historia sin generar miles de requests secuenciales contra una cola cuyo tiempo de respuesta no está documentado, y sin arriesgar que la cuenta quede bloqueada o penalizada por spam de requests.

### Consecuencias

* Cualquier feature de precipitación pronosticada anterior a 2006-10 no estará disponible para el dataset de tesis salvo que se incorpore otra fuente (ej. reanálisis ERA5 como proxy, que no es un pronóstico real y tendría que documentarse como tal si se usara).
* Bronze/Silver de `cf`/`pf` no requirieron cambios de esquema: los notebooks históricos escriben JSONs diarios con el mismo formato que el job diario. El único cambio de código fue agregar `load_mode=backfill` a `ETL_Silver_ECMWF_CF`/`_PF` (con `range_start`/`range_end` explícitos), porque el modo `incremental` existente no cubre filas más viejas que el máximo ya cargado.
* La duración real del backfill completo (~20 requests `cf` + ~238 requests `pf`) no está validada contra la API todavía — queda pendiente calibrar `max_batches_per_run` con el tiempo de cola real observado la primera vez que se corra en Databricks.

---

## Decisión 013: Causa raíz del crash de `Daily_ECMWF_FC` (cfgrib/eccodes vs. compute serverless)

### Estado

`Pendiente` (causa raíz identificada, fix definitivo no aplicado — ver Consecuencias)

### Contexto

El task `Daily_ECMWF_FC` del job `ECMWF_Forecast_Daily_Incremental` fallaba en todas sus corridas desde su primer deploy, siempre con el mismo síntoma: `Fatal error: The Python kernel is unresponsive` / `exit code 134 (SIGABRT)`, sin traceback de Python (el proceso muere, no lanza una excepción).

Se investigó ejecutando ~25 corridas de prueba contra el job real en Databricks (vía `databricks jobs run-now` con `--json '{"only": ["Daily_ECMWF_FC"]}'`), iterando sobre el notebook desplegado directamente vía `databricks workspace import` (el bundle deploy normal **no** actualiza estos notebooks — ver Consecuencias). Se descartaron, en orden, las siguientes hipótesis:

1. **Conflicto `geopandas` (GDAL/PROJ) vs. `cfgrib` (eccodes) en el mismo proceso**: plausible a priori (el notebook llama `compute_download_area()`, que usaba `geopandas`, antes de abrir el grib con `engine="cfgrib"`). Se eliminó `geopandas`/`pyogrio` del notebook (bbox calculado a mano leyendo el GeoJSON, ver `_geojson_total_bounds` en `common_ecmwf.py` y en el notebook) — el crash persistió idéntico, con la misma traza (`gribapi/bindings.py:find_binary_libs`), descartando esta hipótesis.
2. **`netCDF4` instalado junto a `cfgrib` en el mismo `%pip install`** (copiado sin necesidad del notebook `Daily_ECMWF_CF`, que sí lo usa): se eliminó, mismo crash.
3. **OpenMP duplicado (`OMP Error #15`)**: se probó `KMP_DUPLICATE_LIB_OK=TRUE`, sin efecto.

Con logging a archivo (los prints a stdout se pierden en un `SIGABRT`, el buffer nunca se flushea) se aisló el punto exacto: el crash ocurre al cargar `libeckit.so` (parte de `eckitlib`, dependencia nativa de la que depende `eccodeslib` desde que ecCodes ≥2.39 reescribió su binding en base a la librería C++ `eckit` de ECMWF). Se confirmó que:

* `libeccodes.so` (bundleado en el wheel `eccodeslib`) tiene una dependencia dura (`DT_NEEDED`) de `libeckit_geo.so`, que vive en un paquete pip **distinto** (`eckitlib`), no al lado.
* El mecanismo normal para resolver esto (`findlibs._find_in_package`, con `preload_deps=True`) precarga con `dlopen(..., RTLD_GLOBAL)` **todas** las `.so` de `eckitlib/lib64/` (incluye `libeckit_mpi.so`, `libeckit_web.so`, etc.) — y es ahí donde aborta, incluso al precargar solo `libeckit.so` en aislamiento (con o sin `RTLD_GLOBAL`).
* El proceso del notebook corre en **serverless compute**, con Spark Connect activo (`SparkMode.REMOTE_CONNECT`, confirmado en el log de arranque del kernel), que ya tiene cargados en el mismo proceso Python `grpc._cython.cygrpc` y `google._upb._message` (protobuf) antes de que el notebook ejecute una sola celda. Cargar la librería C++ `eckit` (que también embebe su propio protobuf/runtime para config y codecs) en un proceso que ya tiene otro protobuf/gRPC inicializado es un patrón de crash conocido y bien documentado en el ecosistema científico de Python (colisión de símbolos / doble registro en el pool de descriptores de protobuf, que aborta el proceso por diseño).
* Esto coincide con un issue abierto y sin resolver upstream: [ecmwf/cfgrib#430](https://github.com/ecmwf/cfgrib/issues/430) — mismo síntoma exacto (`exit code 134`, Databricks serverless, Python 3.12, `xr.open_dataset(engine="cfgrib")`), reportado como funcionando en un serverless environment más viejo (Python 3.11 / xarray 2024.3.0) y fallando en el más nuevo (Python 3.12 / xarray 2025.8.0).
* Pinnear `eccodes==2.38.3` (versión previa a la reescritura sobre `eckit`) evita el crash pero rompe la carga de otra forma (`RuntimeError: Cannot find the ecCodes library`): esa versión espera un `libeccodes` de sistema (conda/apt), que no existe en este runtime — no es una opción viable sin agregar una instalación de sistema.

### Decisión

Por ahora **no se fuerza un fix desde el notebook** (todas las mitigaciones posibles desde Python puro — reordenar imports, `LD_LIBRARY_PATH`, precarga manual selectiva, `RTLD_LOCAL`, pinnear versión — fueron probadas contra el job real y no evitan el crash o lo trasladan a un error distinto sin solución dentro del notebook). Sí quedan aplicados y mergeados los cambios que son mejoras válidas independientemente de esta causa raíz: eliminar `geopandas`/`pyogrio`/`netCDF4` de `Daily_ECMWF_FC` (dependencias no usadas o reemplazables por stdlib, una fuente menos de conflicto nativo en el proceso).

Se intentó el fix de correr este task específico en un **cluster clásico (job cluster, no serverless)** (que evitaría la colisión con Spark Connect/gRPC/protobuf) agregando un `job_cluster` de un solo nodo a `ecmwf_forecast_daily_incremental` en `databricks.yml`. El deploy fue rechazado por Terraform: `Only serverless compute is supported in the workspace` — el workspace tiene compute clásico deshabilitado a nivel de política, no es una opción disponible acá. Se revirtió el cambio.

Alternativas que quedan sin probar, para decidir con el usuario:

* **`pygrib`** en vez de `cfgrib`/`xarray` para leer el grib2: es otro binding sobre ecCodes, no está confirmado si su wheel evita el árbol de dependencias `eckit` que causa el crash — habría que probarlo contra el job real antes de asumir que funciona.
* Pedirle a ECMWF Open Data el dato en otro formato: descartado, la API solo sirve GRIB2 (y BUFR para ciclones tropicales), no hay opción NetCDF en Open Data (a diferencia de TIGGE/`cdsapi`, que sí la tiene).
* Escribir un parser GRIB2 mínimo sin ecCodes (implementación propia, acotada a los campos que usa este pipeline): evita la dependencia nativa por completo, pero es un desarrollo no trivial que no se justifica sin antes agotar alternativas más baratas.

### Justificación

Ejecutar mitigaciones "a ciegas" (reintentos, pines de versión al azar, `try/except` alrededor de un `SIGABRT`, que ni siquiera es capturable desde Python) sin haber aislado la causa real habría dejado el job igual de roto pero con más código incidental. Se priorizó diagnosticar contra el entorno real (no reproducible localmente, ya que localmente no hay Spark Connect) antes de decidir el fix, dado el costo de cada iteración (~1-3 min por corrida real de Databricks).

### Consecuencias

* `Daily_ECMWF_FC` sigue fallando: el cluster clásico (la mitigación más segura) no está disponible en este workspace, y ninguna mitigación posible desde serverless evita el crash. Sigue roto hasta que se pruebe `pygrib`, se implemente un parser propio, o aparezca un fix upstream en `cfgrib`/`eccodes-python`/`findlibs`/Databricks.
* Se descubrió que `databricks bundle deploy` **no** sincroniza los notebooks hacia `${var.workspace_project_path}` (los jobs apuntan a una copia del workspace separada de `.bundle/.../files`, sincronizada por otro mecanismo, probablemente Git folder / IDE). Cualquier cambio a estos notebooks necesita `databricks workspace import --format JUPYTER --overwrite` apuntando directamente al path de `${var.workspace_project_path}` para que el job lo vea, no alcanza con `bundle deploy`.
* `Daily_ECMWF_CF`/`Daily_ECMWF_PF` no sufren este problema porque usan `engine="netcdf4"` (TIGGE vía `cdsapi` entrega netCDF, no grib), nunca importan `cfgrib`/`eckit`.

## Decisión 014: OOM en `ETL_Silver_ECMWF_CF`/`_PF` en modo `backfill` — chunking por sub-rango de fechas

### Estado

`Resuelto y desplegado` (2026-08-05)

### Contexto

El run `978415325295651` del job `ECMWF_Forecast_Historic_Backfill` (el primero que avanzó de verdad tras corregirse el bug de formato de rango de fechas — ver Decisión 012/notas de `docs/data_sources.md` 7.11) falló en el task `ETL_Silver_ECMWF_CF_Historic`, dos veces (intento original + 1 retry automático), con un mensaje genérico de Databricks (`INTERNAL_ERROR`, "contact Databricks support"). El traceback real, obtenido con `databricks jobs get-run-output` sobre el `run_id` del task (la API `get-run` normal no lo incluye), mostró la causa concreta:

```
SparkException: [TASK_FAILED_EXECUTOR_LOSS] ... Command exited with code 52, oom
```

en la línea `pdf = bronze.toPandas()`.

Causa raíz: el modo `backfill` de `ETL_Silver_ECMWF_CF`/`_PF` filtraba Bronze por `[range_start, range_end]` — el rango que `Historic_ECMWF_CF`/`_PF` publica como task values al final de **cada corrida del job**, no por cada lote individual — y hacía un único `toPandas()` sobre todo ese rango. El comentario original del notebook ya decía la intención ("se corre una vez por cada lote... para no hacer un único toPandas() gigante de todo el histórico"), pero el DAG real solo invoca Silver una vez por corrida del job, después de que `Historic_ECMWF_CF` procesa hasta `max_batches_per_run` (25) lotes internamente. Como esta corrida cayó en años recientes de TIGGE (rápidos de traer del archivo MARS), `Historic_ECMWF_CF` alcanzó a aterrizar ~8 años de golpe (2018-08 a 2026-08, 2923 `run_date`, ~50M filas en Bronze) antes de que corriera Silver — y el `toPandas()` sobre esas ~50M filas reventó el driver.

Para `pf` el riesgo es aún mayor (mismo patrón de código, ya con una nota de comentario anticipándolo): 50 miembros de ensemble por día implican ~50x más filas por día que `cf` para el mismo rango de fechas.

### Decisión

Se reescribió el bloque de procesamiento de `ETL_Silver_ECMWF_CF.ipynb` y `ETL_Silver_ECMWF_PF.ipynb`: en modo `backfill`, en vez de un único `bronze.filter(...).toPandas()` sobre `[range_start, range_end]`, se itera en sub-rangos de `backfill_chunk_days` días (nuevo widget), cada uno con su propio `toPandas()` + `tag_points()` + `MERGE` independiente hacia Silver. Default `backfill_chunk_days=60` para `cf`, `backfill_chunk_days=2` para `pf` (proporcional a la multiplicación por 50 miembros). Los modos `incremental` (acotado por `incremental_lookback_days=3`) y `full` no se tocaron — no mostraron el problema y no está en alcance acotarlos también todavía.

Los notebooks se desplegaron al workspace real con `databricks workspace import --format JUPYTER --overwrite` (recordatorio de la Decisión 013: `bundle deploy` no sincroniza estos notebooks) y se verificó el contenido desplegado con `workspace export` antes de considerar el fix activo.

### Justificación

Chunkear por rango de fechas acota el tamaño de cada `toPandas()` de forma predecible sin importar cuántos lotes aterrice una corrida de `Historic_ECMWF_CF`/`_PF`, en vez de depender de que el `max_batches_per_run` actual "por suerte" no genere un rango demasiado grande (lo cual ya dejó de ser cierto apenas el backfill empezó a progresar de verdad). Se descartó reintentar la corrida tal cual estaba antes del fix: los años que faltan por traer (2006-2018) son los más lentos de descargar de MARS, así que podían generar rangos más chicos por corrida y no repetir el OOM — pero apostar a eso sin arreglar el diseño hubiera dejado el mismo bug latente para cualquier corrida futura que sí aterrice muchos lotes rápidos de una.

### Consecuencias

* El backfill de `cf` puede seguir corriendo con `databricks jobs run-now 458746025401273` (cobertura actual: 2018-08-03 a 2026-08-03; falta 2006-10-01 a 2018-08-02, ~12 años).
* El backfill de `pf` todavía no arrancó (0 filas en `weather.bronze.ecmwf_forecast_pf`): está encadenado detrás de que `cf` complete Landing+Bronze+Silver en una misma corrida (comparten cola/token de TIGGE/ECDS), así que recién se probará una vez que `cf` termine.
* `backfill_chunk_days` es un widget, no una constante hardcodeada: si 60 días (`cf`) o 2 días (`pf`) igual resultan grandes en la práctica (por ejemplo si el bounding box de la cuenca creciera), se puede bajar sin tocar código.

---

## Decisión 015: Backfill histórico ANA para estaciones vigentes sin historia previa (nivel + lluvia)

### Estado

`Implementado y desplegado, primera corrida en curso` (2026-08-05)

### Contexto

Al analizar cuántas estaciones ANA (nivel/lluvia) tienen historia útil como atributos predictores, se encontró que de las 385 estaciones con algún registro de nivel (`Cota_Adotada`) en `weather.bronze.ana_rio_uruguai`, **359 arrancan todas el mismo día, 2026-03-03** — la fecha en la que se puso a correr el job diario `All_Estacoes_ANA_Daily` sobre el inventario ampliado de estaciones. Solo 22 estaciones tienen historia profunda real (la más antigua desde 1939), cargada a mano en su momento vía `Historic_Nivel_ANA.ipynb` para una sola estación (74100000) y por un mecanismo aparte no documentado del todo (recordado por el usuario como "no funcionó para todas"). El mismo patrón se confirmó en lluvia: 271 de 376 estaciones con `Chuva_Adotada` también arrancan en 2026-03-03, con 225 de ellas coincidiendo con las estaciones "shallow" de nivel (mismo request de la API trae ambas variables juntas por estación).

Se investigó el mecanismo histórico existente:

* `Historic_ANA.ipynb` (versión anterior) pegaba contra `https://www.snirh.gov.br/hidroweb/rest/api/seriehistorica`, sin autenticación. Confirmado con `curl` directo: el endpoint devuelve **401 Unauthorized** ("Token de Autenticação da API Inexistente ou mal Formatado") — está muerto, no es un problema del código que lo llama.
* Su ETL compañero, `ETL_Bronze_ANA_Histo.ipynb`, tenía además tres bugs propios independientes de lo anterior: buscaba archivos `.zip` pero el notebook de landing escribía `.csv` (nunca se hubieran encontrado); forzaba `Cota_Adotada=None` en todos los registros (nunca pudo cargar nivel, solo lluvia); y un bug de indentación en el loop de filas que solo agregaba a `records` el último día del último mes iterado por archivo, en vez de la serie completa.
* Se probó el endpoint **autenticado moderno** (`HidroinfoanaSerieTelemetricaAdotada/v2`, el mismo que ya usa `Daily_ANA.ipynb`) contra estaciones "shallow": la estación 72818000 devolvió 712 registros reales para una ventana en 2015 y 0 para una ventana en 2010 — confirma que la API sí tiene historia real más allá de 2026-03-03, simplemente nunca se le pidió.
* Un sondeo parcial (40 de 362 estaciones vigentes, ventanas anuales gruesas) no encontró datos anteriores a 2014 en ninguna, con pico de estaciones nuevas en 2015 — sugiere una expansión de red de telemetría más reciente que las 22 estaciones "viejas", distinta en naturaleza.

### Decisión

Se reescribió `Historic_ANA.ipynb` desde cero, descartando el endpoint legado. Diseño:

* Usa el mismo endpoint autenticado y el mismo patrón de lotes (5 códigos de estación por request, `HidroinfoanaSerieTelemetricaAdotada/v2`, intervalo `DIAS_30`) que `Daily_ANA.ipynb` — validado localmente primero contra la API real (`notebooks_local/ana_historic_backfill/test_batch_request.py`) antes de escribir el notebook de Databricks.
* **Universo objetivo calculado en vivo contra Bronze**, no hardcodeado: estaciones cuyo `MAX(Data_Hora_Medicao) >= hoy - 7 días` (vigentes, el job diario las sigue trayendo) Y `MIN(Data_Hora_Medicao) >= 2026-01-01` (aún sin historia profunda). Deja fuera intencionalmente las 22 estaciones ya profundas y cualquier estación que haya dejado de reportar — pedido explícito del usuario: optimizar la consulta, no barrer el inventario completo.
* **Recorre ventanas de 30 días yendo hacia atrás desde `end_date` (default 2026-03-02, el día antes del arranque del job diario)**, en lotes de 5 estaciones. En cuanto una estación no aparece con ningún registro real (`Cota_Adotada`/`Chuva_Adotada`/`Vazao_Adotada` todos no-nulos) en una ventana de 30 días, se la saca del lote activo y no se le vuelve a preguntar por ventanas más viejas — pedido explícito del usuario: "si se encuentra 1 mes sin registros se deje de solicitar para esa estación, y no se propague la consulta en el pasado". Filtra también los registros "placeholder" que la API devuelve con todos los campos en `null` (confirmado empíricamente, no aportan nada a Bronze).
* Estado persistido en `historic_backfill_state.json` (estaciones activas, próxima ventana a pedir, estaciones ya agotadas con la ventana en que se agotaron) para que la corrida sea resumible entre ejecuciones manuales — corte por `max_windows_per_run` (default 60) sin perder progreso, igual patrón que `max_batches_per_run` en el backfill de ECMWF.
* Reutiliza sin cambios `ETL_Bronze_ANA.ipynb` (ya lee todo `json/` y hace MERGE idempotente por `codigoestacao + Data_Hora_Medicao`); se borró `ETL_Bronze_ANA_Histo.ipynb` (los 3 bugs lo hacían inservible, y ya no hace falta un ETL separado porque el output de landing usa el mismo esquema que el daily).
* Job nuevo `ANA_Historic_Backfill` en `databricks.yml` (`Historic_ANA -> ETL_Bronze_ANA_Historic`), sin schedule, mismo criterio operativo que `ECMWF_Forecast_Historic_Backfill`: se dispara a mano tantas veces como haga falta, nunca en paralelo con `All_Estacoes_ANA_Daily` (comparten cuenta/token de la API de ANA).
* Validado localmente antes de desplegar: `notebooks_local/ana_historic_backfill/test_stateful_dropout.py` corrió la mecánica completa de dropout contra la API real sobre una muestra de 15 estaciones y 20 ventanas — confirmó que `active_stations` se va achicando correctamente y que las estaciones agotadas no se vuelven a consultar en ventanas más viejas.

### Justificación

Pedir el rango completo hasta un piso fijo (ej. 2000-01-01) para las 362 estaciones vigentes sin discriminar hubiera generado consultas masivas sin sentido para estaciones que en la práctica solo tienen ~1 año de historia real (la mayoría, según el sondeo parcial) — exactamente el escenario que el usuario pidió evitar explícitamente. Cortar por estación en cuanto aparece un hueco de 30 días es más barato y se auto-ajusta a la profundidad real de cada estación sin necesidad de sondear primero. Se validó el mecanismo localmente contra la API real (dos scripts en `notebooks_local/ana_historic_backfill/`) antes de tocar el notebook de Databricks, siguiendo el mismo criterio que se usó para la curva de descarga (Decisión previa, sin número asignado en este log): confirmar contra la fuente real antes de comprometer una corrida completa en Databricks.

### Consecuencias

* Job `ANA_Historic_Backfill` (`job_id 610868118241460`) desplegado y primera corrida disparada (`run_id 353257401449660`) el 2026-08-05; estado de esa corrida a verificar en la próxima sesión de trabajo.
* `notebooks/00_Landing/ANA_Hidrico/Historic_ANA.ipynb` y `notebooks/02_Bronze/ETL_Bronze_ANA_Histo.ipynb` (borrado) — cualquier referencia previa a la versión anterior del notebook (por ejemplo en `dataset_definition.md` o notas de EDA) debe asumirse desactualizada.
* Un ejercicio pendiente y explícitamente fuera de este alcance: las 22 estaciones con historia profunda ya cubren nivel; no se investigó si también les falta lluvia reciente o algún hueco entre su carga manual original y el arranque del job diario — quedaría para una revisión de completitud aparte.
* No se tocaron las estaciones que dejaron de reportar (no vigentes) ni las que ya tienen historia profunda — quedan con el registro actual, tal como pidió el usuario para esta etapa.

---

## Decisión 016: Backfill histórico ANA movido a ejecución local + automatización (Task Scheduler + dashboard Gradio)

### Estado

`Implementado` (2026-08-14)

### Contexto

Tras desplegar el job `ANA_Historic_Backfill` (Decisión 015) y dispararlo en Databricks (`run_id 353257401449660`), la corrida real mostró un costo de tiempo mucho mayor al estimado: una sola ventana de 30 días (351 estaciones activas, ~71 lotes de 5 estaciones) tardó entre **6 y 21 minutos** en pruebas locales posteriores, con latencia muy variable request a request. Dado que el job no tiene Spark ni ningún paso pesado (todo el trabajo es HTTP secuencial vía `requests`, salvo el cálculo inicial del universo de estaciones objetivo, que sí usa Spark SQL sobre Bronze), mantenerlo corriendo en un job de Databricks implica pagar cómputo serverless por horas de espera de red pura — un uso pobre del free tier, y el usuario expresó preocupación explícita por agotarlo. Pidió mover la descarga a un proceso local monitoreable, dejando Databricks reservado para el job diario existente.

### Decisión

* **Se canceló** el run en curso (`databricks jobs cancel-run 353257401449660`) sin pérdida de progreso: el estado (`historic_backfill_state.json`) y los 4 archivos de ventana ya escritos quedaron intactos en el Volume (`/Volumes/weather/raw/ana_volume/`), confirmados y bajados localmente antes de cancelar.
* **Se eliminó el job `ANA_Historic_Backfill` de `databricks.yml`** y se redesplegó el bundle — confirmado que Databricks solo retiene los jobs operativos (`All_Estacoes_ANA_Daily`, `Nivel_ANA_Target`, los dos de ECMWF). El job de backfill de ANA ya no existe como recurso en Databricks.
* **`run_backfill_local.py`** (en `notebooks_local/ana_historic_backfill/`): puerto 1:1 de la lógica de `Historic_ANA.ipynb` (mismo endpoint, mismo batching de 5 estaciones, mismo criterio de corte por estación al mes sin datos) corriendo como script local. Retoma desde el `historic_backfill_state.json` bajado del Volume — sin pérdida de progreso respecto a la corrida cancelada. Reescrito con:
  - Logging a archivo (`logs/backfill.log`) además de stdout, vía el módulo estándar `logging`, para que tanto la tarea programada como el dashboard puedan mostrar progreso sin acoplarse al proceso.
  - Lock de un solo proceso (`lock.py`, basado en PID + `tasklist`) envolviendo la corrida (`run_with_lock`), para que la tarea programada de Windows y el botón "Iniciar" del dashboard nunca corran dos backfills en paralelo pisándose el estado.
* **`sync_to_databricks.py`**: sube los JSON ya descargados localmente al mismo Volume que lee `ETL_Bronze_ANA.ipynb` (`databricks fs cp`, solo los archivos que todavía no estén ahí). No dispara ningún job — el próximo run programado de `All_Estacoes_ANA_Daily` los mergea solo, porque `ETL_Bronze_ANA.ipynb` ya lee todo el folder `json/` sin distinguir origen del archivo. Refactorizado para exponer `sync()` como función invocable (además del CLI), usada por el dashboard sin pasar por subproceso.
* **Automatización con Windows Task Scheduler** (`scheduler/register_tasks.ps1`, a correr una sola vez por el usuario, no por el agente — crear tareas programadas persistentes es una acción de sistema que el usuario debe ejecutar explícitamente):
  - `ANA_Backfill_Download`: corre `run_backfill_task.ps1` (tandas de `--max-windows 10`) cada 4 horas, `MultipleInstances=IgnoreNew` para no solaparse.
  - `ANA_Backfill_Sync`: corre `sync_task.ps1` dos veces al día (08:00 y 20:00).
* **Dashboard local con Gradio** (`dashboard_app.py`, puerto 7860): panel de estado (activas/agotadas/ventana actual/corriendo o no), tail de log, botones "Iniciar backfill" (lanza `run_backfill_local.py` como subproceso independiente), "Detener" (mata el proceso activo vía `lock.stop_running()`, sin importar si lo inició la tarea programada o el propio dashboard) y "Sincronizar ahora" (llama `sync()` directo, sin subproceso). Auto-refresco cada 5s vía `gr.Timer`. Probado localmente: levanta y responde HTTP 200 antes de darlo por bueno.
* **`notebooks_local` completo se llevó a una rama nueva (`feature/ana-backfill-automation`)** y se preparó (sin pushear todavía) un commit sobre `main` que lo elimina de ahí: `notebooks_local/ecmwf/*.py` ya estaba trackeado en `main` desde un merge anterior, lo cual el usuario consideró "ruido" en la rama que efectivamente se despliega a Databricks vía `databricks bundle deploy`. `notebooks_local` nunca fue referenciado por `databricks.yml` ni por ningún notebook desplegado, así que removerlo de `main` no afecta nada operativo.
* Se agregó `.gitignore` scoped a `notebooks_local/ana_historic_backfill/` para no versionar datos/estado regenerable (`output_json/`, `historic_backfill_state.json`, `backfill.lock`, `last_sync.json`, logs) — el JSON de una sola ventana de prueba pesó 111 MB, no tiene sentido en el historial de git.

### Justificación

El costo real medido (6-21 min/ventana, cientos de ventanas potenciales hasta agotar ~351 estaciones o llegar al piso 2000) hace que correr esto como job de Databricks sea desproporcionado: es I/O-bound puro contra una API externa, no se beneficia de Spark ni de cómputo distribuido, y cada corrida mantiene un cluster serverless facturando mientras solo espera respuestas HTTP. Correrlo local es estrictamente más barato y, con logging a archivo + lock + dashboard, no se pierde observabilidad frente a la alternativa de Databricks — al contrario, se gana (el usuario puede ver el log en vivo y parar/arrancar sin pasar por la UI de Databricks). Se usó Task Scheduler nativo de Windows en vez de un loop Python autoprogramado porque sobrevive reinicios y cierres de sesión sin dependencias nuevas, y ya tiene soporte nativo para "no arrancar una instancia nueva si la anterior sigue corriendo" (`MultipleInstances=IgnoreNew`), complementando (no reemplazando) el lock de aplicación que además cubre el caso de un arranque manual desde el dashboard.

### Consecuencias

* El usuario debe correr `scheduler/register_tasks.ps1` una vez (manualmente) para activar la automatización; el agente no registra tareas programadas por su cuenta dado que es una acción persistente de sistema.
* El commit de remoción de `notebooks_local` sobre `main` quedó preparado localmente pero **sin pushear** — pendiente de confirmación del usuario antes de subirlo a `origin/main`.
* La sesión de Databricks CLI (`databricks auth login`) usada por `sync_task.ps1` y por el dashboard sigue expirando cada ~1 semana (ya observado varias veces en esta misma sesión de trabajo); si el sync empieza a fallar, el primer diagnóstico es reautenticar con `databricks auth login --profile joaquintschopp@gmail.com`.
* Sigue sin resolverse *por qué* la latencia por ventana varía tanto (5.9 min vs 20.7 min entre dos ventanas consecutivas, mismo tamaño de lote) — no se investigó si es throttling del lado de ANA, reintentos silenciosos del `Retry` adapter, o variabilidad de red genérica. No bloquea el uso del sistema, pero conviene tenerlo en cuenta si el tiempo total termina siendo mucho mayor al estimado.
