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

`Aceptada`, **parcialmente superada** (2026-08-21). Sigue vigente todo lo referido a las restricciones reales de las fuentes y al diseño por lotes. Quedan superadas dos de sus consecuencias: el piso de 2006-10 para las features de pronóstico (la Decisión 021 lo baja a 2000 con GEFS Reforecast v12) y `fc` fuera de alcance (la Decisión 022 lo reincorpora por vía local).

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

**`Resuelta`** (2026-08-21) por la Decisión 022: `fc` se mueve a ejecución local, donde no existe el Spark Connect que provoca la colisión. La causa raíz descrita acá sigue siendo válida y sin solución conocida para `cfgrib` dentro del compute serverless de este workspace; lo que cambió es que el pipeline dejó de necesitarlo ahí.

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

### Enmienda (2026-08-14): descarga continua en vez de tandas de 10 ventanas

El troceo original (`--max-windows 10` cada 4 h) no era una restricción de la API — la protección contra saturar ANA vive en la capa de request (lotes de 5 estaciones, 0.5 s entre lotes, `Retry` con backoff, re-login en 401) y es idéntica corra continuo o troceado. El corte de 10/4h era solo por resumibilidad, y hacía que llegar al piso 2000 tardara ~5 días de reloj (10 ventanas ≈ 64 min cada 4 h). A pedido del usuario se pasó a **descarga continua**:

* `run_backfill_task.ps1`: se quitó `--max-windows`, así `run_backfill_local.py` recorre todas las ventanas en una sola pasada (default del script ya era prácticamente ilimitado).
* `register_tasks.ps1`: `ExecutionTimeLimit` 3h → **6h** (backstop anti-cuelgue, no un tope funcional: el estado se checkpointea por ventana en `run_backfill_local.py`, así que un kill a las 6h pierde a lo sumo la ventana en curso); trigger de descarga **cada 1 h** en vez de 4 h (con `IgnoreNew` los disparos horarios son no-op mientras la corrida vive; solo sirven para **retomar** del `state.json` si se cortó por el límite de 6h, reinicio o crash); sync **cada 6 h** en vez de 08:00/20:00 (más frecuente ⇒ menos MB por corrida, porque `sync()` solo sube lo que aún no está en el Volume).
* Resultado: la descarga termina en ~30 h en vez de ~5 días, se auto-reanuda si se corta, y se frena sola al agotar estaciones o llegar a 2000. El usuario autorizó explícitamente re-registrar las tareas en esta sesión (excepción puntual a "el agente no registra tareas por su cuenta").

---

## Decisión 017: Curvas de aforo multi-estación y conversión nivel → caudal (Fase 1 + Fase 2)

### Estado

`Implementado y desplegado` (2026-08-19). Grupo A (22 estaciones) completo end-to-end incluyendo Gold. Grupo B (~370 estaciones) en descarga de curvas al cierre de esta sesión.

### Contexto

El pipeline solo tenía la curva de descarga de una estación (74100000), descargada a mano con `notebooks_local/ana_rating_curve/download_rating_curve.py`, y el dataset de entrenamiento usaba nivel (cota, cm) como target/feature — una magnitud que no es comparable entre estaciones (depende del cero de escala local). El caudal (m³/s) sí lo es, tiene sentido hidrológico para propagación aguas abajo, y es lo que usan los sistemas operativos reales. El usuario pidió un plan de dos fases (descarga de curvas para todas las estaciones con nivel + transformación nivel→caudal en el pipeline), con cuatro decisiones explícitas (D1-D4): conversión en Silver, target = caudal sin perder nivel, extrapolación con flag en vez de NULL, y alcance = todas las estaciones con piso 2000-01-01.

Calibración real contra la API (Paso 0 del plan) corrigió la hipótesis inicial: el endpoint `HidroSerieCurvaDescarga/v1` filtra por `Data_Ultima_Alteracao` (fecha de modificación del registro en el sistema de ANA), no por vigencia de la curva. Se verificó contra 8 estaciones que todas las modificaciones históricas caen en una banda de ~3 años (2023-02 a 2026-02); se adoptó como barrido una ventana fija de **5 ventanas de 365 días cubriendo `(hoy.año − 4)-01-01 → hoy`** (5 requests por estación en vez de las 77 del rango 1950-2026). Detalle operativo a conservar para el refresco trimestral (Decisión 020):

* La vigencia de cada segmento devuelto es la real, sin importar cuándo se tocó el registro por última vez; las curvas se traen completas y el recorte temporal se aplica a los datos de nivel, no a los metadatos de curva (una vigencia iniciada en 1992 puede seguir vigente en 2003).
* `[]` en todas las ventanas es señal confiable de "sin curva publicada", no de "ventana equivocada" — confirmado contra las 3 estaciones sin curva de la muestra de calibración.
* Si aparece una estación con curva conocida por otra vía (por ejemplo `Vazao_Adotada` con muchos registros en Bronze) pero `sin_curva` en el barrido, la hipótesis a probar es que el margen de la ventana no alcanzó para esa estación y hay que ampliarlo puntualmente.

### Decisión

**Fase 1 (descarga local, `notebooks_local/ana_rating_curve/`):**

* `download_rating_curve.py` corregido: la convención de unidades de `Q = A·(H−H0)^N` estaba mal resuelta (el selector elegía entre dos fórmulas incorrectas por descarte, quedándose con 44% de MAPE en vez de 5,1%). Se fijó la fórmula correcta (`H0` viene en metros, la cota se pasa de cm a m antes de restar) y la validación contra aforos pasó de "selector de convención" a "control de calidad reportado" (`evaluate_curve_accuracy`).
* Nuevo `download_rating_curves_batch.py`: barrido multi-estación con estado resumible (`rating_curve_state.json`), reautenticación ante 401, lock compartido con el backfill histórico (mismo `lock.py` importado desde `notebooks_local/ana_historic_backfill/`, nunca corren en paralelo), reporte de cobertura (`--report-only`) y flags `--group {A,B}` / `--stations` / `--skip-aforos` / `--only-missing`.
* Universo calculado en vivo (no hardcodeado): `estaciones_nivel.json`, 392 estaciones con `Cota_Adotada` en `weather.bronze.ana_rio_uruguai`. Grupo A = 22 estaciones con historia profunda (`SIG/estaciones_ana_nivel_historico.geojson`), Grupo B = las ~370 restantes — ambos son solo orden de ejecución, no recorte de alcance.
* Resultado real grupo A: 509 segmentos de curva (22 estaciones, 0 sin curva, 0 error), 1.737 aforos desde 2000-01-01. Subido a `/Volumes/weather/raw/ana_volume/rating_curves/{curve_segments,discharge_measurements}/` (un JSON por estación, no por ventana).

**Fase 2 (Databricks, job `Rating_Curve_Discharge_Initial_Load` en `databricks.yml`):**

* Tablas nuevas: `weather.bronze.ana_rating_curve_segments`, `weather.bronze.ana_discharge_measurements`, `weather.silver.rating_curve_segments`, `weather.silver.river_discharge_daily`, `weather.silver.estacion_subcuenca` (DDL en `DDL_Silver_Gold.ipynb`); columnas nuevas de caudal en `weather.gold.training_dataset_v0` vía `ALTER TABLE ADD COLUMNS` idempotente.
* `ETL_Bronze_Rating_Curve.ipynb`: MERGE idempotente por `(codigoestacao, Numero_Curva, Periodo_Validade_Inicio, Periodo_Validade_Fim)` y `(codigoestacao, Data_Hora_Dado)`. Dos bugs de Unity Catalog/serverless encontrados y corregidos en la primera corrida real: `input_file_name()` no soportado (usar `_metadata.file_path`), y los campos crudos de aforos vienen como `"Cota (cm)"` / `"Vazao (m3/s)"` (con espacios y unidades en el nombre), no `Cota`/`Vazao` como se asumió inicialmente.
* `ETL_Silver_River_Discharge_Daily.ipynb`: tipa y consolida los segmentos (incluye `is_lowest_segment`/`is_highest_segment`, `aforo_stage_max_cm`, `validation_mape` por estación vía join contra aforos en rango); calcula el nivel diario de **todas** las estaciones con curva leyendo directo de `weather.bronze.ana_rio_uruguai` (no de `river_levels_daily`, que es solo la estación target 74100000); hace el range-join fecha↔vigencia y selecciona el segmento con la tabla de decisión de 5 casos de D3 (`interpolado` / `extrapolado_superior` / `extrapolado_inferior` / `bajo_cero_curva` / `sin_curva`), con `distancia_fuera_rango_cm` y `supera_aforo_maximo` como columnas de contexto en vez de un booleano de descarte.
* `ETL_Gold_Training_Dataset_v0.ipynb`: agrega targets `caudal_t_mas_{1,3,7,14}d` (principales, D2) manteniendo `nivel_rio_t_mas_*` intactos; features de caudal (lag/media/delta) y de contexto de extrapolación; agregados por sub-cuenca (`caudal_agregado_{subcuenca}_m3s/_lag_Nd/_confiable_pct`) sumando caudal de todas las estaciones de `weather.silver.estacion_subcuenca` — físicamente válido porque el caudal es aditivo entre estaciones (el nivel no).
* `weather.silver.estacion_subcuenca`: tabla de referencia sembrada con las 22 estaciones del grupo A (todas en `alta_frontera`, la única sub-cuenca con estaciones de historia profunda). Las columnas de `intermedia_paso_libres`/`baja_salto_grande` quedan en NULL hasta mapear estaciones del grupo B a sub-cuenca (fuera de alcance de esta sesión: requiere unir coordenadas de estación contra los polígonos de `SIG/subcuencas_modelo.geojson`, no hay ese mapeo para las ~370 estaciones del grupo B todavía).
* `Validate_River_Discharge.ipynb`: valida claves únicas, control cruzado contra `Vazao_Adotada` (Bronze, gratuito), MAPE contra aforos separando interpolado/extrapolado, cobertura por `caudal_metodo`, distribución de `distancia_fuera_rango_cm`, monotonicidad/continuidad de segmentos, saltos en bordes de vigencia.

**Resultado real (grupo A, verificado 2026-08-19):** `river_discharge_daily` con 210.106 filas (22 estaciones, 2000-01-01 → hoy), 99,2% `interpolado`, 0,8% `sin_curva`, 0% extrapolado (esperable: el rango calibrado de las curvas cubre casi todo el histórico observado en 26 años). 20/22 estaciones con `is_usable=true` (MAPE ≤ 20%); dos sospechosas (70100000 MAPE=123%, 70300000 MAPE=138%) quedan flageadas para revisión de coeficientes, no bloquean el pipeline. `training_dataset_v0` (`ana_74100000`) con 31.094 filas totales, caudal poblado en las 9.694 filas desde 2000, agregado de sub-cuenca `alta_frontera` calculado.

### Justificación

Separar Fase 1 (local, I/O contra API externa) de Fase 2 (Databricks, transformación) sigue el mismo criterio que las Decisiones 015/016: no pagar cómputo Spark por trabajo que es HTTP secuencial. Poner la conversión en Silver (D1) es coherente con la Decisión 011 (reglas de negocio en Silver, no en Bronze/Gold) y evita duplicar la lógica de vigencia de curvas en cada Gold futuro. Descubrir el bug del selector de convención de unidades (44% vs 5,1% de MAPE) antes de escalar a 392 estaciones evitó propagar un error sistemático a todo el dataset de entrenamiento — se validó contra 292 aforos reales antes de tocar el barrido masivo, mismo criterio de "confirmar contra la fuente real antes de comprometer una corrida completa" usado en la Decisión 015.

### Consecuencias

* El job `Rating_Curve_Discharge_Initial_Load` no tenía schedule al cierre de esta decisión — se disparaba a mano mientras el grupo B se seguía descargando. Su cadencia quedó definida después en la Decisión 020: conversión nivel→caudal diaria, descarga de curvas trimestral.
* Grupo B (~370 estaciones) quedó descargando curvas (sin aforos, pasada no bloqueante aparte) en segundo plano al cierre de esta sesión — el estado es resumible vía `rating_curve_state.json`, se puede continuar con `python download_rating_curves_batch.py --group B --skip-aforos --only-missing`.
* Los agregados de caudal por sub-cuenca (`caudal_agregado_intermedia_paso_libres_*`, `caudal_agregado_baja_salto_grande_*`) están en el esquema pero vacíos hasta que se genere el mapeo estación→sub-cuenca para el grupo B — es la ganancia predictiva más grande pendiente de este trabajo (ver plan §4.5).
* Las dos estaciones sospechosas (70100000, 70300000) no fueron investigadas a fondo; quedan flageadas en `weather.silver.rating_curve_segments.is_usable=false` para que Gold las excluya de `caudal_confiable`, pero valdría la pena revisar sus coeficientes/vigencias manualmente.
* `notebooks/06_Quality/Validate_Training_Dataset_v0.ipynb` y `Check_Bronze_Freshness.ipynb` existen en el Workspace de Databricks pero no estaban versionados en este repo git — se detectó al construir `Validate_River_Discharge.ipynb` siguiendo su mismo patrón. No se resolvió esa desprolijidad en esta sesión (fuera de alcance), pero conviene exportarlos a `notebooks/06_Quality/` en una sesión futura para que el repo sea la fuente de verdad completa.

---

## Decisión 018: El alcance de la tesis se limita a la cuenca alta; la ingesta sigue cubriendo toda la cuenca

### Estado

`Aceptada` (2026-08-21)

### Contexto

El dataset se diseñó desde la Decisión 005 con **dos** puntos críticos de predicción: la frontera Brasil/Argentina (estación ANA 74100000, Irai) y una zona aguas abajo asociada a la represa de Salto Grande. El primero está implementado end-to-end; el segundo nunca arrancó porque sus datos no vienen de ANA sino de CARU / Salto Grande, con una fuente y una conversión nivel→caudal propias todavía sin definir.

Al cerrarse el barrido de curvas de aforo y el backfill histórico de ANA (ver §2 de `roadmap.md`), el dataset quedó completo para la cuenca alta y bloqueado para aguas abajo por trabajo que no tiene fecha. Mantener los dos puntos como objetivo implicaba dejar el dataset permanentemente "incompleto por diseño" y postergar el modelado por una fuente externa que aún no se relevó.

### Decisión

* `gold.training_dataset_v0` contiene **únicamente** la sub-cuenca `alta_frontera`, con el target ya fijado en `ana_74100000`.
* El segundo punto de predicción aguas abajo queda **cancelado** como objetivo de la tesis. Las sub-cuencas `intermedia_paso_libres` y `baja_salto_grande` no se analizan.
* Las columnas de agregado de esas dos sub-cuencas permanecen **reservadas en el esquema de Gold, en `NULL`**, marcadas como fuera de alcance y no como pendientes.
* **La ingesta no se recorta.** ANA nivel/lluvia, curvas de aforo, ECMWF y Salto Grande se siguen descargando y consolidando en Landing/Bronze/Silver para las tres sub-cuencas, incluido el histórico.

### Justificación

El recorte convierte un dataset permanentemente incompleto en uno terminado dentro de un alcance declarado, que es lo que permite escribir la tesis y cerrar la fase de datos. Mantener la ingesta completa cuesta poco (los procesos ya corren y son incrementales) y es lo que hace la decisión reversible: si más adelante se decide reincorporar aguas abajo, el trabajo pendiente es recortar y unir, no volver a descargar veinte años de historia.

Se prefirió el recorte al alcance antes que bajar la calidad del punto que sí está resuelto, en línea con la Decisión 010 (un dataset útil y acotado antes que uno completo e indefinido).

### Consecuencias

* Un solo `punto_prediccion` en el dataset; la clave lógica `fecha + punto_prediccion` se mantiene igual por si se revierte.
* Salen del listado de pendientes: el segundo punto de predicción, el mapeo estación→sub-cuenca de las sub-cuencas intermedia y baja, y sus agregados de caudal.
* Revertir la decisión requiere levantar el filtro en `ETL_Gold_Training_Dataset_v0.ipynb` y sembrar `weather.silver.estacion_subcuenca` con las estaciones de las otras dos sub-cuencas — no requiere ninguna descarga nueva.
* La Decisión 005 (dos puntos críticos, estado `Propuesta`) queda **superada** por ésta.

---

## Decisión 019: Reglas de consolidación hacia Gold y ampliación a ocho horizontes

### Estado

`Aceptada` (2026-08-21), implementación pendiente en la Fase 2 de `roadmap.md`

### Contexto

Las reglas que deciden qué llega a Gold estaban dispersas en el código de los notebooks y nunca se escribieron como contrato. Al cerrarse el barrido de curvas aparecieron además tres situaciones sin regla definida: estaciones sin curva publicada (330 de 392), estaciones cuya última curva vigente termina antes de hoy (25 de las 62 con curva, 2 de ellas en la cuenca alta) y registros con cota por encima del rango calibrado de la curva.

Sobre los horizontes, la Decisión 004 fijó cuatro (1, 3, 7 y 14 días) dejando abierto si convenía extender a todos los días entre 1 y 14.

### Decisión

El principio que ordena todas las reglas: **el nivel nunca se pierde; lo que se puede perder es el caudal derivado de él.**

* **R3 — Estación sin curva de aforo:** no se deriva caudal, pero **el nivel se conserva** y sigue disponible como feature. No se descarta la estación.
* **R4 — Vigencia vencida:** para las estaciones cuya última curva publicada termina antes de la fecha actual, se **extiende esa última vigencia hasta hoy** en vez de dejar el tramo sin caudal. La extensión se marca con una columna propia `curva_vigencia_extendida` para poder reportarla: es un supuesto (asume que la sección no cambió desde el fin de la vigencia), no un dato publicado por ANA.
* **R5 — Cota fuera del rango calibrado:** se mantiene la Decisión 017 · D3 (se extrapola y se marca, nunca se anula). Se agrega la lectura hidrológica: un valor fuera de tabla es muy probablemente una **crecida real**, así que se conserva y las fechas afectadas se emiten como listado para contrastarlas al escribir la tesis contra crónicas de inundaciones documentadas.
* **R6 — Estación íntegramente fuera de tabla:** si **toda** la serie temporal de una estación cae fuera del rango calibrado de su curva, se descarta su caudal y queda sólo el nivel. Es una salvaguarda: hoy ninguna estación de la cuenca alta califica (0% extrapolado observado).
* **Horizontes:** se amplía de 4 a **8** — `t+1, t+2, t+3, t+4, t+5, t+6, t+7, t+14`. Son 8 targets de caudal más 8 de nivel en paralelo, 16 columnas de target.
* **R9 — Cola sin target:** cada horizonte pierde sus últimos *h* días de serie; el descarte se aplica por horizonte, no de forma global.

### Justificación

Extender la última curva vigente (R4) recupera el tramo 2024-2026 de dos estaciones de la cuenca alta que si no quedarían sin caudal justo en el período más reciente y más relevante para validar. Es un supuesto explícito y flageado, preferible a un hueco silencioso.

Conservar los extrapolados (R5) responde a que el error de una ley de potencia por encima de su rango calibrado es máximo justamente en crecidas — que es el fenómeno que interesa modelar. Descartarlos sería descartar los eventos de mayor valor predictivo. Cruzarlos después contra crónicas reales convierte una limitación numérica en evidencia verificable.

La semana día por día (8 horizontes) permite ver **dónde** se degrada el error dentro del rango operativo útil, que con sólo t+1, t+3 y t+7 queda invisible. El costo es de 8 columnas en una tabla de decenas de miles de filas: despreciable.

### Consecuencias

* La Decisión 004 (horizontes 1/3/7/14, estado `Propuesta`) queda **cerrada** con el conjunto de ocho.
* Gold hay que regenerarlo: 8 columnas de target nuevas más `curva_vigencia_extendida`.
* Queda un punto abierto que no se resuelve acá: la definición única de MAPE / `is_usable` (el reporte local y la validación en Silver dan números distintos para las mismas estaciones). Se resuelve en la Fase 2 de `roadmap.md`.
* El contrato completo, con las nueve reglas y el conteo de filas que explica cada una, se publica en `docs/gold_consolidation_contract.md` como entregable de la Fase 2.

### Enmienda (2026-08-21): se cierran los cuatro criterios que habían quedado abiertos

La decisión original dejó cuatro reglas con el criterio sin fijar. Se cierran así:

* **R1 — Piso temporal, ahora duro.** `training_dataset_v0` **arranca en 2000-01-01**. Las 21.400 filas de 1941–1999 (nivel sin caudal) salen de Gold: quedaban vacías en casi todas las columnas y desalineadas con el caudal, con el pronóstico (GEFS v12 arranca en 2000, ver Decisión 021) y con el objetivo de la tesis. **La serie larga de nivel no se pierde**: sigue completa en `weather.silver.river_levels_daily` desde 1941, disponible para análisis histórico de nivel fuera del dataset de entrenamiento. Gold pasa de 31.094 a ~9.694 filas.
* **R7 — Umbral de `is_usable`: MAPE ≤ 30% medido únicamente contra los aforos que caen dentro del rango calibrado de la curva.** Se elige la comparación en rango porque mide lo que la curva efectivamente promete cubrir, y no la penaliza por puntos que nunca pretendió representar. El umbral de 30% (en vez de 20%) responde a que el agregado de la cuenca alta es chico —22 estaciones— y perder una por dos puntos porcentuales cuesta más de lo que aporta el rigor extra. Resultado: **20 de 22 estaciones usables**; quedan fuera `70100000` (MAPE 123%) y `70300000` (138%), que conservan su nivel y sólo pierden el caudal, según la regla general. No se investigan sus coeficientes en esta etapa.
* **R8 — Sin umbral de exclusión para lluvia y temperatura.** Se publica toda estación con algún dato real y la cobertura viaja como columna (`_station_count`, `_cobertura_pct` en el agregado por sub-cuenca). Se abandona el portón todo-o-nada de `missing_pct > 0,90`: era un promedio sobre todas las estaciones juntas y borraba la tabla entera aunque hubiera estaciones con serie excelente. El criterio nuevo es coherente con la Decisión 017 · D3 — el dato sale completo y el filtrado es una decisión de modelado, no una pérdida de información en el pipeline. Cualquier umbral fijo hubiera sido arbitrario y habría que justificarlo en la tesis.
* **R9 — El recorte de la cola sin target se aplica en el exportador, no en Gold.** Gold conserva todas las filas con los targets en `NULL` donde no hay observación; el exportador recorta según el flag `--horizonte` al bajar el dataset. Gold sigue siendo la foto completa y las filas más recientes —las que no tienen target— son justamente las que se usan para predecir en operación. Borrarlas en Gold hubiera dejado la tabla inservible para su propósito operativo.

---

## Decisión 020: Cadencias del pipeline y orden de la cadena diaria

### Estado

`Aceptada` (2026-08-21), implementación pendiente en la Fase 5 de `roadmap.md`

### Contexto

El requisito operativo es que **todos los días a las 06:00 el dataset tenga el día anterior cerrado**, tanto para predecir como para reentrenar y testear. Al revisar los schedules reales de `databricks.yml` aparecieron dos cosas sin definir:

1. La Decisión 017 dejó sin fijar la cadencia de `Rating_Curve_Discharge_Initial_Load`, que se venía disparando a mano.
2. `ECMWF_Forecast_Daily_Incremental` corre a las 08:00 UTC (05:00 America/Montevideo), es decir **después** de `Silver_Gold_Daily_Incremental` (04:30 Montevideo). Mientras el pronóstico no entra a Gold eso es inocuo, pero al integrarlo (Fase 4 del roadmap) Gold estaría consumiendo el pronóstico del día anterior, con un desfase de 24 h que no queda registrado en ninguna columna.

### Decisión

* **La conversión nivel → caudal de las estaciones con curva es diaria**, encadenada como task previo a Gold dentro de `Silver_Gold_Daily_Incremental`. No depende de que haya curvas nuevas: se aplica a los niveles del día con las curvas ya cargadas.
* **La descarga de curvas de aforo nuevas es trimestral**, en un job propio sin schedule diario. Corre en local (`download_rating_curves_batch.py`, ver Decisión 016 sobre por qué el I/O contra la API de ANA no corre en Databricks), seguida de la carga a Bronze y el reproceso del caudal histórico.
* **El pronóstico entra a Gold antes del volcado.** Si el ciclo está disponible en ECMWF antes de la hora de descarga actual, se adelanta la descarga. Si la medición de latencia real muestra que no está disponible tan temprano, se corre Gold detrás del pronóstico (Gold puede moverse a las 05:15 y seguir cumpliendo la meta de las 06:00). Lo que no se acepta es dejar el pronóstico fuera de la corrida del día.
* **Regla general de la cadena:** ningún eslabón que alimente a Gold puede correr después de Gold. Queda escrita en `current_pipeline_inventory.md` junto al orden completo.

### Justificación

Separar la cadencia del dato (diaria) de la cadencia del metadato (trimestral) es la distinción que faltaba: las curvas de aforo cambian con baja frecuencia porque son recalibraciones de ANA, mientras que los niveles llegan todos los días y su conversión a caudal es una transformación determinística que no tiene motivo para esperar.

Sobre el orden: un eslabón que corre después de Gold introduce un desfase de 24 h invisible en los datos — no hay columna que lo delate, y aparece más adelante como una señal rara en el modelo que cuesta semanas rastrear hasta el schedule. Es más barato fijar el orden ahora que auditarlo después.

### Consecuencias

* `Rating_Curve_Discharge_Initial_Load` se parte en dos: un task diario de conversión dentro del incremental, y un job trimestral de refresco de curvas.
* Queda como punto abierto la **latencia real de disponibilidad del pronóstico**: TIGGE (`cf`/`pf`, vía `cdsapi`) documenta un embargo para acceso público que puede llegar a ~48 h. Si se confirma, el pronóstico que entra a Gold no es el del día sino el del ciclo disponible más reciente, lo que cambia el significado operativo del modelo. Se mide en la Fase 4 y se registra por fila en una columna `forecast_age_days`; no se asume ni a favor ni en contra hasta medirlo.
* El criterio de cierre de la Fase 5 es empírico: tres días consecutivos en que a las 06:00 el snapshot local tenga la fila de ayer completa, con caudal y pronóstico del ciclo correcto.

---

## Decisión 021: El pronóstico cubre desde 2000 — GEFS Reforecast v12 empalmado con TIGGE por calibración

### Estado

`Aceptada` (2026-08-21), implementación en la Fase 4 de `roadmap.md`

### Contexto

La Decisión 012 aceptó que la reconstrucción histórica del pronóstico arrancara en 2006-10, por ser el piso real del archivo TIGGE, y dejó explícitamente fuera de alcance el período 2000–2006. El dataset de caudal, en cambio, arranca en 2000-01-01 (Decisión 017 · D4). Eso dejaba 6 años y 9 meses de dataset sin ninguna feature de pronóstico — casi un tercio de la serie entrenable.

Al revisar el roadmap se decidió que esa asimetría no es aceptable: si el pronóstico es la única familia de features con información del futuro, tenerla ausente en un tercio de la serie obliga a entrenar con dos regímenes de features distintos o a resignar el tramo temprano.

La restricción de TIGGE es real y no se puede levantar. Lo que sí existe es otra fuente de pronósticos retrospectivos que cubre exactamente el hueco.

### Decisión

* **El pronóstico cubre desde 2000-01-01**, alineado con el piso temporal del caudal. El período 2000–2006 deja de estar fuera de alcance.
* **Fuente para el tramo temprano: GEFS Reforecast v12 (NOAA)**, con cobertura aproximada 2000–2019 y acceso público en AWS Open Data. Son pronósticos retrospectivos reales, no reanálisis: no introducen fuga de información. El horizonte y la resolución exactos se verifican al implementar, contra el requisito de cubrir hasta t+14 con resolución útil a escala de sub-cuenca.
* **Se descarta ERA5 como fuente de pronóstico.** Es reanálisis: describe lo que efectivamente pasó, no lo que se pronosticaba. Usarlo como feature de pronóstico sobrestimaría sistemáticamente la habilidad del modelo. Sólo sería admisible declarado como experimento de cota superior (*perfect prognosis*), y no se incorpora en esta etapa.
* **Empalme calibrado en el solapamiento.** GEFS v12 y TIGGE coexisten en 2006–2019, 13 años. Se usa ese solapamiento para ajustar GEFS contra TIGGE (corrección de sesgo por sub-cuenca y por horizonte) y se publica **una sola serie homogénea** de pronóstico, con una columna `forecast_source` que declara el origen de cada fila.
* La ingesta de GEFS corre **en local**, siguiendo el precedente de las Decisiones 015/016: es I/O contra una API externa, no se beneficia de Spark, y no tiene sentido pagar cómputo serverless por esperar descargas. Mismo patrón de estado resumible y lock compartido que el resto de las descargas locales.
* La corrección de sesgo se aplica **en Silver**, coherente con la Decisión 011: es una regla de negocio, no un hecho crudo. Bronze conserva lo descargado tal cual.

### Justificación

Empalmar dos fuentes sin calibrar habría creado un escalón artificial en la serie de features justo en 2006 o 2020 — una discontinuidad que un modelo de árboles aprende como si fuera señal y que después aparece como una importancia de variable inexplicable. Con 13 años de solapamiento hay material más que suficiente para caracterizar el sesgo entre modelos, así que la corrección es medible y no un supuesto.

Publicar una serie única con `forecast_source` en vez de dos columnas paralelas evita el NULL estructural en un tercio de la serie, que es exactamente el problema que la decisión venía a resolver.

El trabajo de calibración además rinde como material propio de tesis: comparar la habilidad de dos sistemas de pronóstico sobre la misma cuenca es un resultado en sí mismo, no sólo un paso de ingeniería.

### Consecuencias

* Queda **superada la consecuencia de la Decisión 012** que fijaba 2006-10 como piso de las features de pronóstico. La restricción de TIGGE sigue vigente; lo que cambia es que ya no determina el piso del dataset.
* GEFS v12 termina alrededor de 2019 y TIGGE cubre 2006 → hoy, así que no queda ningún hueco: el tramo 2020 → hoy sale de TIGGE.
* Aparece una fuente nueva que hay que documentar en `data_sources.md` antes de escribir código, según la regla de §10 de ese documento.
* El volumen de descarga de GEFS hay que dimensionarlo al implementar: se necesita sólo precipitación sobre el bounding box de la cuenca, pero los archivos de origen son globales por variable y fecha.
* `forecast_source` pasa a ser una columna del dataset y debe entrar al diccionario de columnas de la Fase 6.

---

## Decisión 022: `fc` se resuelve moviéndolo a ejecución local; su historia se investiga y tiene reemplazo definido

### Estado

`Aceptada` (2026-08-21), implementación en la Fase 8 de `roadmap.md`. **Resuelve la Decisión 013**, que estaba `Pendiente`.

### Contexto

`fc` (HRES determinístico, vía ECMWF Open Data) tenía dos problemas distintos que se venían tratando como uno solo:

1. **El job diario crashea.** `Daily_ECMWF_FC` aborta con `SIGABRT` al cargar `libeckit.so`, por colisión entre la librería nativa `eckit` (que `cfgrib`/`eccodes` ≥2.39 arrastra) y el protobuf/gRPC que Spark Connect ya tiene cargado en el mismo proceso. Diagnóstico completo en la Decisión 013. Todas las mitigaciones desde Python puro fallaron, y el workspace no permite compute clásico, que era la salida natural.
2. **No tiene archivo histórico.** ECMWF Open Data retiene sólo ~12 corridas (2-3 días). La Decisión 012 lo puso fuera de alcance por eso.

La Decisión 013 quedó abierta sin fix. El roadmap la trae de vuelta al alcance.

### Decisión

* **`fc` se descarga en local, no en Databricks.** La causa raíz del crash es la convivencia con Spark Connect en el compute serverless; en una máquina local ese proceso no existe y `cfgrib` funciona normalmente. Se reinstala el camino de landing local para `fc` (`notebooks_local/ecmwf/landing_fc_opendata.py`, borrado en el commit `ac6deab`) y se suma su carga al script de descarga y sincronización que ya usan las demás fuentes locales.
* **La descarga diaria arranca cuanto antes.** Como Open Data no retiene historia, cada día que pasa sin descargar es archivo perdido de forma irrecuperable. El costo de acumular es casi nulo.
* **La historia de `fc` se investiga como tarea de la fase**, no se da por perdida: relevar si existe alguna ruta de archivo accesible (Service Agreement / MARS con acuerdo académico institucional, u otro endpoint de ECMWF).
* **Criterio de salida si la investigación no encuentra ruta viable:** el lugar del pronóstico determinístico lo ocupa el **GEFS operativo de NOAA**, cuyo reforecast 2000–2019 ya va a estar ingestado por la Decisión 021 — con lo cual entrenamiento y operación quedan sobre el mismo modelo, sin asimetría. **El reemplazo aplica únicamente a `fc`**: el ensemble sigue siendo de ECMWF (`cf`/`pf` vía TIGGE), no se migra a NOAA.
* **Acceso en tiempo real:** la vía es **ECMWF Open Data, que es gratuita y sin embargo** — es de donde ya sale `fc`. La tarea de investigación de la Fase 4 verifica qué productos de ensemble y qué parámetros de precipitación expone hoy (la nota de `data_sources.md` §7 dice que `tp` para `cf`/`pf` no estaba disponible ahí, pero el catálogo de Open Data cambió varias veces desde entonces). No se contrata ninguna vía paga.

### Justificación

Mover `fc` a local es la misma jugada que ya resolvió el backfill histórico de ANA (Decisión 016): sacar de Databricks el trabajo que es I/O contra una API externa y que además choca con el entorno. Acá tiene un beneficio extra que allá no existía — elimina la causa raíz del crash en vez de mitigarla, porque el conflicto es con el entorno de ejecución, no con el código.

Se prefirió esto a las alternativas que la Decisión 013 dejaba planteadas: `pygrib` era una apuesta sin confirmar (es otro binding sobre el mismo ecCodes, podía arrastrar el mismo árbol de dependencias) y un parser GRIB2 propio es desarrollo no trivial que no se justifica en una tesis de datos cuando existe una salida de una línea de configuración.

Definir el reemplazo por GEFS operativo antes de investigar evita que la fase quede rehén de un trámite institucional de duración desconocida: la fase puede cerrar con o sin acceso a MARS.

### Consecuencias

* La **Decisión 013 pasa de `Pendiente` a resuelta**, por relocalización del proceso y no por fix del crash. Si en el futuro se volviera a necesitar `cfgrib` dentro de Databricks serverless, el problema sigue intacto y sin solución conocida en este workspace.
* `fc` no aporta historia para entrenar en el corto plazo: su archivo empieza a acumularse desde el día que se prenda la descarga. Hasta que la investigación resuelva, el entrenamiento usa `cf`/`pf` y GEFS, que sí cubren 2000 → hoy.
* Si el reemplazo se activa, el dataset queda con determinístico de NOAA y ensemble de ECMWF. Es una combinación defendible pero hay que documentarla explícitamente en el capítulo de datos.
* `data_sources.md` §7.1 debe actualizarse: `fc` deja de estar «descartado» y pasa a estar ingestado por vía local.

## Decisión 023: R8 para lluvia — sin umbral de exclusión, agregado por sub-cuenca con cobertura expuesta

### Estado

`Aceptada` (2026-08-21), implementada en la Fase 3 de `roadmap.md` (tareas — lluvia).

### Contexto

`ETL_Silver_Rainfall_Daily.ipynb` publicaba lluvia diaria sólo si un único indicador global —
`missing_pct` promediado sobre las ~522 estaciones de `weather.bronze.ana_rio_uruguai` en una
ventana de 30 días — quedaba por debajo de 0,90; si no, ejecutaba un `DELETE` de **todas** las
filas de la fuente, sin distinguir estación. Además, `ETL_Gold_Training_Dataset_v0.ipynb` sumaba
`lluvia_acumulada_mm` sobre **toda la cuenca** (~392 estaciones con curva más el resto de la red),
violando el alcance espacial de la Decisión 018: Gold sólo debe publicar el agregado de
`alta_frontera`, igual que el caudal.

Al medir el estado real contra Databricks para corregir esto, aparece un hallazgo que condiciona
el resultado: de las 22 estaciones del grupo A (`weather.silver.estacion_subcuenca`, todas en
`alta_frontera`), **sólo 9 reportan `Chuva_Adotada` alguna vez, y sólo desde 2026-03-03** — 0 días
de lluvia antes de esa fecha en las 26 años de historia de nivel/caudal de esas estaciones. El
resto de la red (hasta 522 estaciones con algún dato de lluvia, back hasta 1912) está fuera de
`alta_frontera`. El indicador global anterior ocultaba esto: sumaba lluvia de estaciones lejanas
y daba la falsa impresión de cobertura casi completa.

### Decisión

* **Se elimina el portón binario y el `DELETE` global.** `ETL_Silver_Rainfall_Daily.ipynb` publica
  toda estación con dato real, sin umbral de exclusión (R8). La medición de `missing_pct` contra
  `weather.silver.attribute_quality` se conserva, pero pasa a ser puramente informativa: ya no
  bloquea publicación ni borra filas.
* **`lluvia_acumulada_mm` en Gold corrige su alcance, no su nombre.** Se recalcula uniendo
  `weather.silver.rainfall_daily` contra `weather.silver.estacion_subcuenca` filtrado a
  `alta_frontera` — mismo join que ya usa el agregado de caudal. La columna sigue llamándose
  igual porque su intención (lluvia relevante para el punto de predicción) no cambió; lo que
  cambió es que ahora sí la cumple.
* **La cobertura viaja como columna, no como portón.** Cuatro columnas nuevas en
  `weather.gold.training_dataset_v0`: `lluvia_agregado_alta_frontera_station_count`,
  `lluvia_agregado_alta_frontera_cobertura_pct` (contra el universo de 22 estaciones mapeadas),
  y los acumulados móviles `lluvia_agregado_alta_frontera_acum_3d_mm` /
  `_acum_7d_mm`, que faltaban (roadmap: "acumulados y ventanas móviles").
* **`lluvia_is_usable` queda deprecada** (siempre `NULL`): era el resultado del portón que se
  elimina. Se conserva la columna en el esquema en vez de borrarla, porque Delta no permite un
  `ADD COLUMNS` no idempotente ni un `DROP COLUMN` barato en este workspace, y no hay lectores
  externos que dependan de dropearla.
* **`weather.silver.sg_rainfall_daily` (Salto Grande) no se conecta al agregado de Gold.** El
  inventario de estaciones activas (`estaciones_activas.csv`, columna `subcuenca_nombre` ya
  provista por el proveedor) confirma que ninguna de sus 69 estaciones cae en `alta_frontera`:
  59 en `baja_salto_grande`, las 10 restantes en `intermedia_paso_libres`. Conectarlas violaría el mismo
  R2 que esta decisión corrige para ANA. La tarea del roadmap ("conectar SG a Gold") se resuelve
  por la negativa: queda fuera de alcance mientras Gold no publique esas sub-cuencas (Decisión
  018), documentado en vez de forzado.

### Justificación

Un portón que mide una sola cifra sobre 522 estaciones heterogéneas no puede representar la
calidad real de ninguna de ellas individualmente: puede pasar con estaciones del target vacías
(como se descubrió acá) o fallar con estaciones del target perfectas si el resto de la red tiene
un mal día. El principio que ya rige las otras ocho reglas de consolidación (R1-R7, R9) —no
perder información buena por un criterio grueso, exponer la calidad real como dato en vez de
decidir por el usuario final— se aplica igual acá.

Corregir el alcance de `lluvia_acumulada_mm` en el mismo cambio (en vez de en un paso aparte) es
necesario porque ambos bugs se enmascaraban mutuamente: con el portón global activo, cualquier
intento de leer la cobertura real de `alta_frontera` en particular hubiera dado un número
optimista y falso.

### Consecuencias

* **La lluvia es casi inutilizable como feature en el dataset actual.** Con cobertura real desde
  2026-03-03 nada más, cualquier modelo entrenado con el histórico completo (2000-2026) va a ver
  `lluvia_acumulada_mm` en `NULL` en el 98,6% de las filas. Esto no es un bug de esta fase: es el
  estado real de la fuente, medido con las herramientas que esta fase construyó. Queda registrado
  como limitación conocida en `data_sources.md` y en el roadmap.
* Hay dos salidas posibles para esto, ninguna implementada todavía: (a) que las 13 estaciones sin
  lluvia empiecen a reportar `Chuva_Adotada` de acá en adelante (la telemetría de ANA es del
  proveedor, no del pipeline) — la cobertura mejoraría desde hoy en adelante, nunca hacia atrás; o
  (b) sumar lluvia de estaciones del grupo B dentro de `alta_frontera` (Fase 7) si alguna tiene
  historia de lluvia más profunda que las del grupo A, cosa que no se investigó todavía.
* `docs/gold_consolidation_contract.md` (R8) y `docs/data_sources.md` (§4, lluvia; §6, Salto
  Grande) se actualizan con estos números reales.

---

## Decisión 024: El hueco de lluvia de la Decisión 023 era un artefacto de `estacion_subcuenca`, no de la fuente — sembrado completo del inventario ANA

### Estado

`Aceptada` (2026-08-22), implementada contra Databricks real.

### Contexto

La Decisión 023 midió, contra la `estacion_subcuenca` que existía en ese momento, que sólo 9 de
las 22 estaciones de `alta_frontera` reportaban `Chuva_Adotada`, y sólo desde 2026-03-03 — 0 días
de lluvia en 26 años. Esa tabla de referencia (`weather.silver.estacion_subcuenca`) tenía **sólo
22 filas**: las estaciones del grupo A (con curva de aforo), sembradas a mano en algún momento
anterior a cualquier notebook versionado, nunca documentado. Ninguna de las ~760 estaciones
exclusivamente pluviométricas o fluviométricas sin curva —que sí están en Bronze desde el job
`All_Estacoes_ANA_Daily`, que descarga *todo* el inventario de la cuenca, no sólo el grupo A—
tenía fila en `estacion_subcuenca`. El agregado de lluvia de Gold, al hacer `JOIN` contra esa
tabla filtrada a `alta_frontera`, sólo podía ver esas 22 estaciones aunque la cuenca tuviera
cientos de estaciones de lluvia reales.

Se confirmó contra Databricks real (2026-08-22) que el inventario que ya usa `Daily_ANA.ipynb`
como universo de descarga
(`/Volumes/weather/raw/ana_volume/estaciones_rio_uruguai_pluvio_fluvio.json`) trae
`subcuenca_nombre` ya resuelto por estación: 782 en `alta_frontera`, 581 en
`intermedia_paso_libres`, 24 en `baja_salto_grande` (total 1.387). Cruzando ese inventario contra
`weather.bronze.ana_rio_uruguai` (`Chuva_Adotada IS NOT NULL`), 332 estaciones de `alta_frontera`
tienen lluvia real, con historia desde **1923-01-01** — 103 años antes del hallazgo "0 días" de la
Decisión 023.

### Decisión

* **`weather.silver.estacion_subcuenca` se resiembra con el inventario completo** (las tres
  sub-cuencas, 1.387 estaciones), no sólo las 22 del grupo A. Implementado como celda nueva en
  `notebooks/04_Silver/DDL_Silver_Gold.ipynb` (`MERGE` idempotente por `codigoestacao`, ejecuta en
  cada corrida del job — no sólo una vez a mano), y verificado también con el `MERGE` equivalente
  corrido directo contra Databricks vía SQL warehouse (1.365 filas insertadas, 22 actualizadas,
  1.387 totales).
* **No hace falta tocar `ETL_Gold_Training_Dataset_v0.ipynb`.** Ya hacía el `JOIN` correcto contra
  `estacion_subcuenca` filtrado a `alta_frontera` (Decisión 023); el bug estaba exclusivamente en
  qué filas tenía esa tabla, no en la lógica de agregación.
* **Se re-materializó todo el pipeline Silver→Gold** (`Silver_Gold_Initial_Load_v0`, `load_mode:
  full`, corrido en Databricks: 7/7 tareas en verde) para que el agregado recalculara con la tabla
  corregida.
* El backfill dirigido a las 22 estaciones del grupo A
  (`notebooks_local/ana_historic_backfill/run_backfill_alta_frontera.py`, iniciado en la sesión
  2026-08-21 para investigar la Decisión 023) **queda como mejora secundaria, no como el
  arreglo**: seguía corriendo al momento de este hallazgo (9/22 estaciones activas, retomando
  ~2023-12) y se lo deja terminar, porque cada estación que reporte su propia lluvia en vez de
  depender del agregado de vecinas es una señal más limpia, pero el hueco de cobertura que
  bloqueaba el uso de la columna en Gold ya no existe con este cambio.

### Verificación real contra Databricks (2026-08-22)

| Métrica | Antes (Decisión 023) | Después (Decisión 024) |
| --- | --- | --- |
| Filas en `estacion_subcuenca` | 22 | 1.387 |
| Estaciones de `alta_frontera` con `Chuva_Adotada` real | 9 | 332 |
| Historia más antigua de lluvia real en `alta_frontera` | 2026-03-03 | 1923-01-01 |
| `training_dataset_v0`, filas con `lluvia_acumulada_mm` no nulo | 138 / 9.730 (1,42%) | 9.696 / 9.730 (99,65%) |
| Cobertura anual 2000-2025 (% de días con lluvia agregada) | — (no medible con 22) | 100% todos los años; 85,4% en 2026 (parcial, mes en curso) |
| Promedio de estaciones que aportan al agregado diario | 0,13 | 73,7 (contra un universo de 782 mapeadas en `alta_frontera`) |

Consultas ad hoc vía `databricks api post /api/2.0/sql/statements` contra el warehouse serverless
`Serverless Starter Warehouse` (mismo mecanismo que las fases anteriores; no se usó notebook para
medir, sólo para aplicar el cambio).

### Justificación

El principio que ya rige R1-R9 y la Decisión 023 —medir contra Databricks real antes de concluir,
no confiar en un número agregado que puede ocultar la causa— se aplica un nivel más abajo acá: la
Decisión 023 sí midió contra datos reales, pero contra una tabla de referencia (`estacion_subcuenca`)
que nunca se auditó a sí misma. Sembrarla a mano con 22 filas, sin notebook ni fecha de origen, era
exactamente el tipo de paso no reproducible que este roadmap busca eliminar (§4 del roadmap: "no
cuenta como avance... modificar código sin registrar la decisión"). La corrección no fue ampliar la
fuente de lluvia (la fuente siempre tuvo esta cobertura) sino corregir qué parte de la fuente el
pipeline podía ver.

### Consecuencias

* **`lluvia_acumulada_mm` pasa de inutilizable a la feature con mejor cobertura de todo el dataset**
  después del propio caudal/nivel. La limitación registrada en la Decisión 023 ("98,6% NULL") queda
  obsoleta y se corrige en `data_sources.md` y en el roadmap.
* El mismo problema podría existir para `intermedia_paso_libres` y `baja_salto_grande` si alguna
  fase futura reabre esas sub-cuencas (Decisión 018 las mantiene fuera de Gold hoy); ya no hace
  falta resembrarlas a mano porque quedaron sembradas en este mismo cambio.
* La Fase 7 del roadmap ("ampliación del agregado con las 40 estaciones del grupo B") queda
  parcialmente resuelta por este cambio para lluvia (ya están todas sembradas); para caudal/nivel
  sigue pendiente tal como estaba, porque ese agregado depende de `river_discharge_daily`
  (estaciones con curva), no de `estacion_subcuenca`.
* `docs/data_sources.md` §3 (inventario ANA) y §4 (lluvia) se actualizan con el mecanismo de siembra
  y los números reales de esta tabla.

---

## Decisión 025: Ingesta de INMET y corrección del alcance espacial de `temp_global` en Gold

### Estado

`Aceptada` (2026-08-24), implementada e ingestada contra Databricks real.

### Contexto

La Fase 3 del roadmap dejaba pendiente la temperatura: ingestar INMET (investigación cerrada en
la Decisión previa/`data_sources.md` §9.3, 2026-08-22) y aplicar a `weather.silver.temperature_daily`
el mismo criterio R8 que ya se aplicó a lluvia (Decisiones 023/024) — sin umbral de exclusión,
cobertura real como columna.

Al diseñar la unificación METAR+INMET se encontró un segundo problema, de la misma familia que el
que motivó la Decisión 024: el bloque `temp_global` de `ETL_Gold_Training_Dataset_v0.ipynb` promediaba
**todos** los aeropuertos METAR con un simple `groupBy('fecha')`, sin ningún `JOIN` contra
`weather.silver.estacion_subcuenca` — a diferencia de lluvia y caudal, nunca se había escopeado a
`alta_frontera`. Geométricamente, además, **ninguno de los 4 aeropuertos METAR** (`SBGR` São Paulo,
`SBCT`/`SBGL` — hay un mismatch preexistente entre `Daily_Temp_Airport.ipynb` y `Hist_NOAA.ipynb`
sobre cuál es el cuarto aeropuerto, no se toca en esta decisión —, `SBPA` Porto Alegre, `SBFL`
Florianópolis) cae dentro de ninguna de las tres sub-cuencas del modelo (`SIG/subcuencas_modelo.geojson`):
`temp_media_c`/`temp_min_c`/`temp_max_c` en Gold nunca midieron la temperatura de la cuenca, sino un
promedio de temperatura nacional brasileña.

### Decisión

**Catálogo de estaciones INMET.** `notebooks_local/inmet_backfill/fetch_station_catalog.py` descarga
el catálogo nacional de INMET (`apitempo.inmet.gov.br/estacoes/T`, requiere `User-Agent` de navegador)
y resuelve la sub-cuenca real de cada estación con un join espacial exacto (`geopandas.sjoin`,
predicado `within`) contra `SIG/subcuencas_modelo.geojson` — el mismo método que la Decisión 024 usó
para validar el inventario ANA de forma independiente. El bounding box usado en la investigación
inicial (2026-08-22) daba 49 estaciones y se había estimado "42" a ojo; el join de polígono exacto da
el número real: **27 estaciones dentro de alguna sub-cuenca — 15 en `alta_frontera`, 12 en
`intermedia_paso_libres`, 0 en `baja_salto_grande`**.

**Backfill histórico.** `notebooks_local/inmet_backfill/download_inmet_zips.py` descarga los 27 ZIP
anuales (2000-2026, `portal.inmet.gov.br/uploads/dadoshistoricos/{AAAA}.zip`), extrae en memoria sólo
los CSV de esas 27 estaciones (nunca escribe los ~2,6 GB completos de ZIP a disco) y produce un JSON
por estación/año. Corrida completa 2026-08-24: **2.593.410 registros horarios**, 340 archivos
estación/año, 0 años fallidos (26/26 desde 2001, más 2000 sin datos porque ninguna estación de la
cuenca operaba todavía). `sync_to_databricks.py` sube catálogo y JSON a
`weather.raw.inmet_volume` (mismo patrón que `notebooks_local/ana_historic_backfill/`, incluyendo
el lock compartido `lock.py`).

**Bronze.** `weather.bronze.inmet (codigo_estacao, data_hora_medicao, temp_c, source_file)`, MERGE
append-only por `(codigo_estacao, data_hora_medicao)` en `ETL_Bronze_INMET.ipynb` (mismo patrón que
`ETL_Bronze_Temp_Daily.ipynb` para METAR). Sólo se conservan filas con `temp_c` no nulo.

**Silver.** `ETL_Silver_Temperature_Daily.ipynb` unifica METAR + INMET: `weather.silver.temperature_daily`
gana `estacion_id` (= `icao_id` para METAR, = `codigo_estacao` para INMET) y `fuente`
(`metar`|`inmet`); `icao_id` se conserva sin tocar. R8 aplica de entrada — no hay umbral de exclusión
para ninguna de las dos fuentes.

**Gold.** `ETL_Gold_Training_Dataset_v0.ipynb` reemplaza `temp_global` por `temp_alta_frontera`: un
`JOIN` de `weather.silver.temperature_daily.estacion_id` contra el mismo universo
`estacion_subcuenca` filtrado a `alta_frontera` que ya usa lluvia. `temp_media_c`/`temp_min_c`/
`temp_max_c` mantienen sus nombres pero corrigen su alcance (igual que `lluvia_acumulada_mm` en la
Decisión 024); se agregan `temp_agregado_alta_frontera_station_count` y
`temp_agregado_alta_frontera_cobertura_pct` (mismo patrón que lluvia). `temp_station_count`
(la columna vieja, sin escopear) queda deprecada.

**Sin regla de prioridad entre fuentes.** El diseño original (`data_sources.md` §9.3) dejaba pendiente
"una regla de prioridad a definir (INMET más cercano al punto de predicción vs. METAR más estable)".
No hizo falta: dado que los 4 aeropuertos METAR están geográficamente fuera de las tres sub-cuencas,
METAR e INMET nunca compiten por el mismo territorio dentro de `alta_frontera` — el agregado de Gold
usa exclusivamente estaciones INMET.

**Sin job de descarga periódica.** Igual que ANA histórico (Decisión 016), no se agregó ningún job
Databricks de re-descarga diaria/incremental de INMET: el único mecanismo viable hoy (re-descargar el
ZIP del año en curso) queda documentado como opción futura en `data_sources.md`, no implementado.
`ETL_Bronze_INMET` sí se agregó a `databricks.yml` (tasks `silver_gold_initial_load_v0` y
`silver_gold_daily_incremental`, antes de `ETL_Silver_Temperature_Daily`) para que cualquier archivo
nuevo que se sincronice manualmente al Volume se mergee a Bronze en la próxima corrida.

### Verificación real contra Databricks (2026-08-24)

`Silver_Gold_Initial_Load_v0` corrido en `load_mode=full` contra Databricks real: 8/8 tareas en
verde (incluyendo `ETL_Bronze_INMET`, `ETL_Silver_Temperature_Daily`, `ETL_Gold_Training_Dataset_v0`,
`Validate_Training_Dataset_v0` y `Export_Gold_Snapshot`). Un primer intento falló dos veces y se
corrigió en el camino (ver Consecuencias); la corrida final quedó limpia.

| Métrica | Valor real |
| --- | --- |
| `weather.bronze.inmet` | 2.593.410 filas, 27 estaciones, 2001-12-05 a 2026-07-31 |
| `weather.silver.temperature_daily`, filas `fuente = inmet` | 110.857 filas, 27 estaciones |
| `weather.silver.temperature_daily`, filas `fuente = metar` | 47.215 filas, 5 estaciones (ver nota del mismatch SBCT/SBGL) |
| Claves duplicadas `(fecha, estacion_id)` | 0 |
| `weather.silver.estacion_subcuenca`, `alta_frontera` | 797 (782 ANA + 15 INMET) |
| `training_dataset_v0`, filas con `temp_media_c` no nulo | 7.184 / 9.732 (73,8%) |
| Cobertura diaria de `alta_frontera` por año | 0% en 2000-2005 (sin estaciones operando); 9,6% en 2006 (arranca a mitad de año); 99,2% en 2007; **100% todos los años desde 2008 hasta 2025**; 90,2% en 2026 (parcial, año en curso) |
| Estaciones promedio que aportan al agregado diario | de 2,0 (2006) a 8-12 (2008 en adelante), sobre un universo de 15 mapeadas en `alta_frontera` |

Verificado también localmente sin abrir Databricks: `export_gold_dataset.py --refresh --resumen`
reprodujo las mismas 9.732 filas (2000-01-01 a 2026-08-23) y el mismo 26,2% de `temp_media_c` nulo,
tras el corte por versión Delta (236 → 257).

**Bug encontrado y corregido durante la implementación (no en el diseño, en la ejecución):**

1. **Formato de fecha de INMET cambia en 2019.** El CSV histórico usa `DATA (YYYY-MM-DD)` con
   guiones hasta 2018 y con barras (`YYYY/MM/DD`) desde 2019 en adelante. La primera corrida de
   `download_inmet_zips.py` no normalizaba el separador y produjo `data_hora_medicao` con formato
   mixto; `to_timestamp` sin formato explícito falló al parsear las filas 2019-2026
   (`CAST_INVALID_INPUT`) y tumbó `ETL_Silver_Temperature_Daily`. Se corrigió normalizando `/` a
   `-` antes de construir el timestamp, se re-descargaron los 8 años afectados (2019-2026) y se
   volvieron a subir al Volume.
2. **Migración de esquema con MERGE dejó filas huérfanas.** `weather.silver.temperature_daily`
   pre-existía con `icao_id` como única clave; al agregar `estacion_id`/`fuente` por
   `ALTER TABLE ADD COLUMNS`, las ~47.000 filas METAR previas quedaron con `estacion_id = NULL`.
   El `MERGE` nuevo usa `t.estacion_id = s.estacion_id` como condición de match — en SQL,
   `NULL = valor` nunca es verdadero, así que esas filas nunca matchearon y quedaron duplicadas
   junto a las filas nuevas (mismo `fecha`/`icao_id`, `estacion_id` poblado). `Validate_Training_Dataset_v0`
   lo detectó correctamente (`assert_unique` sobre `(fecha, estacion_id)`, con varias filas
   `NULL` agrupando bajo la misma clave). Se corrigió con un `DELETE FROM
   weather.silver.temperature_daily WHERE estacion_id IS NULL` (47.215 filas huérfanas) antes de
   reintentar — una migración de esquema con cambio de clave sobre una tabla ya poblada necesita
   limpiar las filas viejas, no sólo agregar columnas.

Ambos bugs se encontraron porque el job realmente falló en Databricks (no se detectaron por
inspección de código) — el mismo principio de "medir contra Databricks real" que ya justificó las
Decisiones 023/024 detectó estos dos antes de que llegaran a producción.

### Justificación

El mismo principio que ya rige R1-R9 y las Decisiones 023/024 —medir contra Databricks real antes de
concluir, no confiar en un número agregado que puede ocultar el alcance real— aplica acá: `temp_global`
no estaba "roto" en el sentido de devolver `NULL` o fallar, devolvía un número plausible (temperatura
promedio de estaciones meteorológicas brasileñas) que nunca fue la temperatura de la cuenca del punto
de predicción. Sin el join espacial exacto tampoco se habría detectado que la estimación inicial de
"42 estaciones" de la investigación de `data_sources.md` era, en los hechos, 27.

### Consecuencias

* `temp_media_c`/`temp_min_c`/`temp_max_c` en Gold dejan de ser temperatura nacional y pasan a ser
  temperatura real de `alta_frontera`, con cobertura medida en vez de asumida.
* `docs/data_sources.md` §9.3 y `docs/gold_consolidation_contract.md` (R8) se actualizan con el
  mecanismo de ingesta y los números reales.
* La Fase 3 del roadmap queda cerrada.
* Si en el futuro se reabre `intermedia_paso_libres` o `baja_salto_grande` (Decisión 018), las 12
  estaciones INMET de `intermedia_paso_libres` ya quedaron sembradas en `estacion_subcuenca` en este
  mismo cambio (mismo catálogo, las tres sub-cuencas).

---

## Decisión 026: Investigación de GEFS Reforecast v12 (NOAA) — cobertura, formato y gotcha de precipitación acumulada

### Estado

`Aceptada` (2026-08-24), investigación cerrada contra la fuente real, implementación pendiente
(Fase 4 del roadmap).

### Contexto

La Fase 4 del roadmap (Decisión 021) exige documentar GEFS Reforecast v12 en `data_sources.md`
antes de escribir código (regla de §10 de ese documento) y resolver la Investigación C: verificar
que la cobertura 2000-2019 llega hasta t+14 con resolución útil a escala de sub-cuenca.

### Hallazgos (verificados contra el documento oficial de NOAA/PSL, no por referencia a librerías
comunitarias)

* Fuente: `noaa-gefs-retrospective` (S3 público, sin autenticación, `--no-sign-request`) — mismo
  costo cero que TIGGE Open Data, ninguna vía paga involucrada.
* Cobertura: 2000-01-01 a 2019-12-31, una corrida diaria a las 00 UTC, 5 miembros (`c00`+`p01..p04`)
  la mayoría de los días, 11 miembros (`c00..p10`) una vez por semana.
* Horizonte: **+16 días** en la corrida estándar de 5 miembros — **cubre t+14 todos los días**,
  sin necesitar la corrida extendida de 11 miembros/+35 días. Cierra la Investigación C de la Fase
  4 con resultado positivo: no hace falta documentar una limitación de cobertura por horizonte.
* Resolución: 0,25°/3h hasta el día +10, 0,50°/6h desde el día +10 — el t+14 del dataset cae en el
  tramo de resolución más gruesa, pero sigue siendo un pronóstico real utilizable, no un hueco.
* Formato GRIB2 (no NetCDF), un archivo por variable+fecha+miembro, directorio
  `GEFSv12/reforecast/{yyyy}/{yyyymmdd00}/{miembro}/`. Variable de precipitación: `apcp_sfc`
  (kg/m² ≡ mm, misma unidad que `tp_mm` de TIGGE).
* **Gotcha de diseño encontrado en la tabla de variables (no un supuesto):** `apcp_sfc` viene
  acumulado **por bloque de 3h/6h más reciente**, no acumulado desde el inicio de la corrida como
  el `tp` de TIGGE. Sumarlo ingenuamente como si fuera acumulado-desde-el-inicio produciría una
  serie de precipitación pronosticada sistemáticamente subestimada frente a `cf`/`pf` — hay que
  acumular los incrementos sucesivos al aplanar/consolidar, antes de comparar o calibrar contra
  TIGGE (Decisión 021).

### Justificación

Documentar antes de implementar (regla de §10 de `data_sources.md`) evitó dos riesgos concretos:
construir el pipeline sobre el supuesto incorrecto de que GEFS es acumulado-desde-el-inicio como
TIGGE (hubiera contaminado el empalme calibrado de la Decisión 021 con un sesgo sistemático), y
sub-invertir en la Investigación C sin haber verificado el horizonte real contra la fuente.

### Consecuencias

* `docs/data_sources.md` §9.4 documenta la fuente completa (cobertura, formato, grilla, gotcha de
  acumulación, volumen medido contra el bucket real).
* La Investigación C de la Fase 4 (§5 del roadmap) queda cerrada: GEFS v12 sí llega a t+14 con
  resolución útil, sin degradar el criterio de salida.
* Pendiente para la implementación (no resuelto en esta decisión): dónde acumular los incrementos
  de `apcp_sfc` (¿en el aplanado de Landing o en Silver?).
* Volumen dimensionado contra el bucket real (listado S3, no descarga completa): ~26,5 MiB/día/miembro
  sin recortar (grilla global), ~950 GB si se bajara el rango completo 2000-2019 × 5 miembros sin
  ningún recorte — cifra que obliga a decidir una estrategia de recorte/reducción de cobertura antes
  de implementar (ver `data_sources.md` §9.4, "Volumen y dimensionamiento"). TIGGE no tiene este
  problema porque sí soporta recorte `area` server-side; GEFS no.
* No cambia ninguna decisión previa: reafirma la Decisión 021 (empalme GEFS+TIGGE) con los datos
  reales en vez de la expectativa inicial.

---

## Decisión 027: Diagnóstico y corrección del OOM en el backfill histórico de `pf` (TIGGE)

### Estado

`Aceptada` (2026-08-24), causa raíz diagnosticada, corrección implementada y **verificada contra
una corrida real completa en Databricks**: `ECMWF_Forecast_Historic_Backfill` corrió con
`max_batches_per_run=1`, las 7 tareas en verde (`Historic_ECMWF_CF` → Bronze → Silver →
`Historic_ECMWF_PF` → Bronze → Silver), sin OOM. `weather.bronze.ecmwf_forecast_pf` pasó de 0 a
**26.784.000 filas** (31 días, 2026-07-23 a 2026-08-22, un lote mensual completo) y
`weather.silver.ecmwf_forecast_pf_basin` (recortado al polígono) quedó en 10.812.800 filas —
confirmado con una consulta SQL real contra el warehouse serverless, no por el estado "SUCCESS"
del job solamente.

### Contexto

El job `ECMWF_Forecast_Historic_Backfill` (Decisión 012, `data_sources.md` §7.11) lleva desde el
28/07 sin lograr aterrizar ninguna fila de `pf` en Bronze (`weather.bronze.ecmwf_forecast_pf`
seguía en 0 filas al 2026-08-24, confirmado con una consulta SQL real contra el warehouse
serverless). El run más reciente antes de esta decisión (`415433127125022`, 2026-08-05) falló con
`Execution ran out of memory` / `SIGKILL (exit code 137)` en el task `Historic_ECMWF_PF`, al pedir
el primer lote (2026-07-04..2026-08-03, 31 días × 50 miembros).

### Diagnóstico

La causa **no** era el tamaño de la descarga GRIB/NetCDF en sí (el archivo `.nc` de un lote
mensual de `pf` es del mismo orden de magnitud que el `.nc` anual de `cf`, que sí funciona). La
causa real está en `flatten_ensemble_forecast_batch()` (`common_ecmwf.py` y su copia inline en
`Historic_ECMWF_PF.ipynb`): la función recorre **todo el lote completo** (reftimes × miembros ×
steps × puntos de grilla) y construye un único `dict` con **todos los días del lote** en memoria
antes de devolver nada — recién ahí el caller escribe los JSON.

Con la grilla real de la cuenca (~975 puntos, medida contra `SIG/subcuencas_modelo.geojson`), un
lote mensual de `pf` genera 31 días × 50 miembros × 16 steps × 975 puntos ≈ **24,2 millones de
records** (`dict` de Python) simultáneos en memoria antes del primer `write_json()` — del orden de
15-20 GB sólo en objetos Python, sobre un compute serverless con memoria acotada (Databricks Free
Edition). El caso de `cf` no sufre esto porque no tiene la dimensión `number` (50 miembros) y usa
`flatten_forecast_batch()`, que genera ~5,3 millones de records por lote anual — 4,5x menos, un
margen que alcanza a no reventar.

### Corrección

Se agregó `iter_ensemble_forecast_batch_by_day()` (generador) en `common_ecmwf.py` y en la copia
inline de `Historic_ECMWF_PF.ipynb`: procesa y devuelve **un día (reftime) a la vez**, en vez de
acumular el lote completo. El caller (`historic_pf_tigge.py` y la celda 5 del notebook) escribe y
descarta cada día apenas se genera (`del records`), acotando el pico de memoria a ~780.000 records
(un día) en vez de ~24,2 millones (el lote completo) — **~31x menos**, sin cambiar el request a la
API, el formato de los JSON de salida, ni el tamaño de lote (`BATCH_MONTHS=1`). `flatten_forecast_batch()`
de `cf` no se tocó (no está roto).

Deploy: `databricks workspace import` directo al Databricks Repo (no `bundle deploy`, ver memoria
de sesión sobre sync), verificado con `workspace export` antes de disparar el job — confirma la
lección operativa ya registrada en la Decisión previa sobre notebooks (Fase 3, lluvia): nunca
confiar en que el bundle sube el cambio.

### Justificación

Reducir el tamaño de lote (menos días o menos miembros por request) habría sido un parche más
fácil de escribir, pero no ataca la causa real (records de Python acumulados en memoria) y
degrada la eficiencia de la reconstrucción histórica (más requests contra la cola de TIGGE/ECDS,
más tiempo total). El generador resuelve la causa raíz sin tocar el contrato con la API externa
ni el tamaño de lote ya calibrado (1 mes, elegido en la Decisión 012 para no generar un orden de
magnitud de fields excesivo del lado de la API — un problema distinto al de memoria del lado del
cliente que resolvió esta decisión).

### Consecuencias

* Desbloquea el backfill histórico de `pf`, detenido desde el 28/07 sin ninguna fila en Bronze.
* Aplica también, por diseño, a cualquier lote futuro más grande (ej. si se decidiera subir
  `max_batches_per_run` o `BATCH_MONTHS` para `pf`): el pico de memoria queda acotado por día, no
  por tamaño de lote.
* Verificado: la corrida de prueba dejó `pf` con datos reales en Bronze y Silver por primera vez
  desde que existe el job (28/07). Sigue el mismo patrón, sin límite artificial de lotes,
  `Historic_ECMWF_PF` puede correr repetidamente (mismo criterio operativo que `cf`, Decisión 012)
  hasta completar el rango 2006-10-01 → hoy — trabajo que queda abierto en la Fase 4, esta
  decisión sólo desbloquea que avance.

---

## Decisión 028: Cierre de la Fase 7 — 14 de las 40 estaciones "grupo B" sí caen en `alta_frontera`, y ya densifican el agregado de caudal sin haber tocado código

### Estado

`Aceptada` (2026-08-24), verificada contra Databricks real. Cierra la Fase 7 del roadmap.

### Contexto

El barrido de curvas de aforo de la Fase 2 (`docs/roadmap.md` §2) clasificó 62 estaciones de toda
la cuenca con curva usable: 22 en `alta_frontera` (grupo A, con historia profunda, mapeadas a mano
en `weather.silver.estacion_subcuenca` desde la Decisión 017) y 40 "con curva, fuera de la cuenca
alta" (grupo B), excluidas del agregado de Gold. Esa clasificación de las 40 nunca tuvo una unión
espacial real detrás: grupo B era, por construcción, "todo lo que no es grupo A"
(`notebooks_local/ana_rating_curve/grupo_b_hechas.txt`, 40 códigos), y en el momento del barrido
`estacion_subcuenca` solo tenía las 22 filas del grupo A — no había con qué comparar la ubicación
real de esas 40.

La Decisión 024 (2026-08-22) resembró `estacion_subcuenca` con el inventario completo de ANA
(1.387 estaciones, `subcuenca_nombre` resuelto por el proveedor y validado al 99,9% con un join
espacial independiente en `geopandas`), motivada por un bug de cobertura de lluvia — no por la
Fase 7. Su sección "Consecuencias" registró que la Fase 7 "queda parcialmente resuelta... para
caudal/nivel sigue pendiente tal como estaba, porque ese agregado depende de
`river_discharge_daily`... no de `estacion_subcuenca`". Esa afirmación no se verificó contra las
40 estaciones concretas del grupo B ni contra el código real de
`ETL_Gold_Training_Dataset_v0.ipynb`. Esta decisión hace esa verificación.

### Investigación

**1. Identificación de las 40 estaciones grupo B.** `notebooks_local/ana_rating_curve/grupo_b_hechas.txt`
lista 40 códigos (`66400390`, `71385400`, ..., `77500000`); `SIG/estaciones_ana_nivel_historico.geojson`
confirma las 22 del grupo A (`70100000`...`74100000`); sin superposición entre ambos conjuntos.

**2. Estado real de `estacion_subcuenca` para las 40 (consulta SQL vía warehouse serverless,
`d8aaafcf1fdb6645`):**

| Resultado | Estaciones |
| --- | ---: |
| No están en `estacion_subcuenca` | 1 (`66400390`) |
| `alta_frontera` | **14** |
| `intermedia_paso_libres` | 23 |
| `baja_salto_grande` | 2 |
| **Total con fila en la tabla** | **39** |

`66400390` es la estación que activó R6 (`weather.gold`/`gold_consolidation_contract.md`): una
única lectura de nivel de ~200 m, descartada como outlier (`caudal_metodo='descartado_r6'`,
`caudal_m3s IS NULL`). No tener mapeo de sub-cuenca es irrelevante para el agregado porque nunca
aporta caudal de todos modos.

Los 14 códigos de `alta_frontera`: `71385400`, `71386500`, `71890500`, `72080000`, `73203000`,
`73204000`, `73330250`, `73340000`, `73552000`, `73553000`, `73560000`, `73570000`, `73600700`,
`73691000`.

**3. Las 14 ya tienen caudal real en `weather.silver.river_discharge_daily`** (consultado
directo): entre 392 y 4.083 filas cada una, todas con al menos una fila `caudal_m3s IS NOT NULL`
(rango de fechas desde 2013-08-09 hasta hoy, la mayoría `caudal_metodo='interpolado'`, dos
`sin_curva` en tramos sin vigencia). Una de ellas, `73552000`, tiene `caudal_confiable=false` en
456 de sus 458 filas (curva probablemente floja); no se excluyó porque la agregación nunca filtró
por `caudal_confiable`, ni siquiera para las dos sospechosas del grupo A (`70100000`, `70300000`,
R7) — mismo criterio que ya regía antes de esta decisión.

**4. El código de agregación de caudal (`ETL_Gold_Training_Dataset_v0.ipynb`, celda 3,
`subcuenca_daily`) ya era dinámico**, no hardcodeado a 22 estaciones:

```python
subcuenca_daily = (
    spark.table(DISCHARGE_TABLE).alias('d')
    .join(spark.table(SUBCUENCA_TABLE).alias('sc'), 'codigoestacao', 'inner')
    .groupBy('fecha', 'subcuenca')
    .agg(F.sum('caudal_m3s').alias('caudal_agregado_m3s'), ...)
)
```

Un comentario del notebook decía lo contrario ("Hoy solo el grupo A... está mapeado... hasta que
el grupo B tenga curva y mapeo de sub-cuenca") — quedó desactualizado por la Decisión 024 y se
corrigió en esta sesión (cambio de comentario únicamente, sin tocar lógica; no requirió redeploy
al Repo de Databricks porque no cambia el comportamiento de ningún job).

**5. El agregado real de Gold ya refleja las 14 estaciones nuevas**, sin que se haya escrito
ningún código para esta decisión. Consulta directa: `SUM(DISTINCT codigoestacao)` con
`caudal_m3s IS NOT NULL` unido a `estacion_subcuenca` filtrado a `alta_frontera` da **36**
estaciones (22 grupo A + 14 grupo B), y el valor de
`weather.gold.training_dataset_v0.caudal_agregado_alta_frontera_m3s` coincide exactamente (a
precisión de punto flotante) con un recálculo fresco del `JOIN` completo para tres fechas de
muestra:

| Fecha | Valor en Gold (m³/s) | Recálculo fresco (m³/s) |
| --- | ---: | ---: |
| 2010-06-01 | 3.926,511379856865 | 3.926,511379856864 |
| 2020-01-15 | 1.311,787461527658 | 1.311,787461527658 |
| 2025-06-01 | 1.420,576914703768 | 1.420,576914703768 |

Esto confirma que las corridas `full` de `Silver_Gold_Initial_Load_v0` disparadas para las
Decisiones 024 (2026-08-22) y 025 (2026-08-24) ya recalcularon el agregado con las 14 estaciones
nuevas — no hace falta una corrida adicional para esta decisión.

**6. Densificación por año** (estaciones grupo-B nuevas que aportan al agregado, promedio diario
por año, 2000-2026, `river_discharge_daily` con `caudal_m3s IS NOT NULL` unido a `estacion_subcuenca`):

| Año | Estaciones grupo B activas (máx. en el año) | Promedio diario de estaciones grupo B aportando |
| --- | ---: | ---: |
| 2000-2014 | 0 | 0,00 |
| 2015 | 3 | 1,08 |
| 2016 | 3 | 2,97 |
| 2017 | 3 | 2,87 |
| 2018 | 6 | 3,57 |
| 2019 | 6 | 5,68 |
| 2020 | 6 | 5,98 |
| 2021 | 6 | 5,83 |
| 2022 | 8 | 6,08 |
| 2023 | 8 | 7,65 |
| 2024 | 9 | 8,79 |
| 2025 | 12 | 10,74 |
| 2026 (parcial, 200 días) | 14 | 12,48 |

Confirma lo que anticipaba el roadmap ("la mayoría de las estaciones del grupo B no tiene nivel
antes de ~2014"): la densificación arranca en **2015**, no en 2000, y crece de forma sostenida
hasta hoy.

**7. Hallazgo colateral, fuera del alcance de `alta_frontera` pero descubierto en la misma
verificación:** las columnas `caudal_agregado_intermedia_paso_libres_m3s` y
`caudal_agregado_baja_salto_grande_m3s`, descritas en el roadmap como "reservadas... en NULL"
(Decisión 018), **también dejaron de estar en NULL** por el mismo mecanismo — 23 y 2 de las 40
estaciones del grupo B caen en esas dos sub-cuencas respectivamente. Verificado:
`weather.gold.training_dataset_v0` tiene 7.684/9.732 filas con `caudal_agregado_intermedia_paso_libres_m3s`
no nulo y 6.843/9.732 con `caudal_agregado_baja_salto_grande_m3s` no nulo (antes de la Decisión 024
ambas columnas eran 100% `NULL`, porque `estacion_subcuenca` solo tenía las 22 filas de
`alta_frontera`). No cambia el alcance de la tesis (Decisión 018, "Tesis: No" para esas dos
sub-cuencas sigue vigente — es una decisión de modelado, no una limitación de datos), pero corrige
la descripción del roadmap §1 y de `data_sources.md` §3.10, que afirmaban que el caudal no se veía
afectado por la resiembra de `estacion_subcuenca`.

### Decisión

* **No se escribió código nuevo.** El `JOIN` dinámico en `ETL_Gold_Training_Dataset_v0.ipynb` ya
  hacía exactamente lo que pedían las tareas de la Fase 7 (unión espacial + siembra + recálculo)
  como efecto colateral de la Decisión 024. Se corrigió únicamente el comentario desactualizado en
  esa celda del notebook (sin cambio de lógica, sin redeploy necesario).
* Se corrige `docs/data_sources.md` §3.10, que registraba (heredado de la Decisión 024) que el
  agregado de caudal "no se ve afectado" por la resiembra de `estacion_subcuenca` — afirmación
  incompleta: sí se ve afectado, y las 14 estaciones nuevas de `alta_frontera` lo demuestran.
* Se cierra la Fase 7 del roadmap con el criterio de cierre cumplido: se sabe cuántas de las 40
  caen en la cuenca alta (14) y desde qué año densifican el agregado (2015).
* El hallazgo colateral sobre `intermedia_paso_libres`/`baja_salto_grande` se deja documentado
  (roadmap §1, este documento) pero no se actúa sobre él: está fuera del alcance de la tesis por
  decisión de modelado explícita (Decisión 018), no por falta de datos.

### Justificación

El mismo patrón que ya aparece en las Decisiones 023, 024 y 025 (INMET "42" estimado vs. "27" con
join exacto; lluvia "0 días" vs. "332 estaciones reales") se repite acá: una clasificación gruesa
de la Fase 2 ("40 fuera de la cuenca alta") no tenía detrás una unión espacial real, y una
afirmación de la Decisión 024 ("para caudal sigue pendiente") tampoco se verificó contra el código
ni contra las estaciones concretas. El principio operativo del repo —medir contra Databricks real
antes de concluir, no asumir que una clasificación anterior sigue vigente— aplica igual cuando la
sospecha es "puede que ya esté resuelto" que cuando es "puede que esté roto": en ambos casos hace
falta la consulta real, no la inferencia.

### Consecuencias

* `caudal_agregado_alta_frontera_m3s` en `weather.gold.training_dataset_v0` pasa de 22 a **36**
  estaciones contribuyentes reales (22 grupo A + 14 grupo B), ya materializado, ya verificado — sin
  ninguna corrida adicional de job.
* La densificación es más significativa desde 2018-2019 en adelante (3 → 6 → 8 → 12-14
  estaciones), lo que mejora la representatividad del agregado en la parte más reciente de la
  serie, coherente con la expectativa original del roadmap.
* Las 26 estaciones restantes de las 40 (23 en `intermedia_paso_libres`, 2 en `baja_salto_grande`,
  1 sin mapeo por ser un outlier descartado por R6) no aportan a `alta_frontera` y no requieren
  ninguna acción adicional.
* Se corrige el comentario de `ETL_Gold_Training_Dataset_v0.ipynb` (celda `subcuenca_daily`),
  `docs/data_sources.md` §3.10 y el roadmap §1/Fase 7 (`docs/roadmap.md`) para reflejar el estado
  real: el agregado de caudal sí depende de `estacion_subcuenca`, tanto como el de lluvia y
  temperatura.
* Queda documentado, pero fuera de esta decisión, que `intermedia_paso_libres` y
  `baja_salto_grande` ya tienen agregados de caudal reales en Gold (7.684 y 6.843 filas no nulas
  respectivamente) — disponibles si una fase futura reabriera esas sub-cuencas (Decisión 018), sin
  necesidad de ingesta ni mapeo adicional.

---

## Decisión 029: Implementación del landing local de GEFS Reforecast v12 — descarga masiva en local, sólo se sube a Databricks el recorte a la cuenca

### Estado

`Aceptada` (2026-08-24), implementada y **verificada contra Databricks real**: 3 días reales
(2018-01-01 a 2018-01-03, incluida una corrida extendida de 11 miembros) descargados, recortados,
subidos y mergeados en `weather.bronze.gefs_reforecast` — 1.876.800 filas, `tp_mm` en rango
`[0.0, 347.0]`, sin duplicados.

### Contexto

La Decisión 026 documentó GEFS Reforecast v12 antes de escribir código (regla de §10 de
`data_sources.md`) y midió que descargar el rango completo sin recortar pesaría ~950 GB (grilla
global, GEFS no soporta recorte `area` server-side como TIGGE). El usuario pidió explícitamente
que, si la descarga es masiva, se haga en local y sólo se suba a Databricks lo que corresponde a
la cuenca — el mismo principio que ya rige `ana_historic_backfill` e `inmet_backfill` (Decisiones
015/016, 025).

### Diseño e implementación

* `notebooks_local/gefs_reforecast/`: mismo patrón que `inmet_backfill` (descarga a un
  directorio temporal, recorta/procesa en memoria, borra el archivo crudo, nunca lo sube).
  * `common_gefs.py`: descarga HTTPS directa al bucket público `noaa-gefs-retrospective` (sin
    autenticación), recorte al bounding box de la cuenca (`compute_download_area()`, reusada de
    `notebooks_local/ecmwf/common_ecmwf.py` vía import cruzado, mismo patrón que INMET reusa
    `lock.py` de `ana_historic_backfill`), `cumsum()` sobre el eje `step` para convertir el
    incremento por bloque de `apcp_sfc` en acumulado-desde-el-inicio-de-la-corrida (comparable a
    `tp_mm` de TIGGE, gotcha de la Decisión 026), y un offset exacto (sin interpolar: los puntos
    de grilla de 0,50° son subconjunto exacto de los de 0,25°, mismo origen factor 2x) para
    empalmar el tramo `Days:1-10` (0,25°/3h) con `Days:10-16` (0,50°/6h) en una sola serie
    cumulativa continua.
  * `download_gefs_backfill.py`: resumible (`gefs_backfill_state.json`), lock compartido
    (`notebooks_local/ana_historic_backfill/lock.py`), lista miembros reales por fecha vía el
    listado S3 (`list_members()`) en vez de asumir 5 fijos — confirmado empíricamente que
    2018-01-03 (miércoles) trajo 11 miembros (`c00`..`p10`), validando que la corrida extendida
    semanal existe y se detecta sola.
  * `sync_to_databricks.py`: sube sólo los JSON ya recortados y aplanados (`output_json/`) al
    Volume `weather.raw.gefs_volume/json/`, nunca los `.grib2` crudos (se borran localmente
    apenas se procesan, igual que los ZIP de INMET).
* **Gotcha nuevo, encontrado al implementar, no documentado en el PDF oficial de NOAA ni en la
  Decisión 026:** el archivo `Days:1-10` de cada miembro perturbado (`p01`..`p10`) mezcla dos
  `dataType` de GRIB2 en un solo archivo — 79 mensajes `pf` (steps +6h a +240h) y **un mensaje
  `cf`** para el primer step (+3h), que `cfgrib` no puede leer sin `filter_by_keys` explícito.
  Verificado que ese mensaje "cf" es idéntico entre miembros perturbados en el mismo punto de
  grilla (compartido porque la dispersión del ensemble todavía no creció en +3h, sólo mal
  etiquetado por el codificador de NOAA) — se lee con ambos `filter_by_keys` y se concatena para
  no perder el primer step. El tramo `Days:10-16` y el miembro `c00` no tienen este problema.
* DDL: `weather.raw.gefs_volume` y `weather.bronze.gefs_reforecast` agregados a
  `notebooks/04_Silver/DDL_Silver_Gold.ipynb` (mismo patrón que INMET). Bronze:
  `notebooks/02_Bronze/ETL_Bronze_GEFS.ipynb`, mismo patrón que `ETL_Bronze_ECMWF_CF.ipynb` con
  `member` (string: `c00`/`p01`..`p10`) en vez de `number` (int) como parte de la clave de
  `MERGE`.
* `databricks.yml`: `ETL_Bronze_GEFS` agregado a `silver_gold_initial_load_v0` y
  `silver_gold_daily_incremental`, dependiendo sólo de `DDL_Silver_Gold`/`Check_Bronze_Freshness`
  — corre en paralelo a la cadena principal de Silver, no la bloquea ni depende de ella (GEFS
  todavía no tiene consumidor en Silver/Gold). Desplegado con `databricks bundle deploy`
  (a diferencia del contenido de los notebooks, la definición de tareas de un job sí se actualiza
  por bundle deploy — sólo el contenido de los notebooks requiere `workspace import` al Repo por
  separado, ver memoria de sesión sobre sync).

### Verificación contra Databricks real

`DDL_Silver_Gold` y `ETL_Bronze_GEFS` corridos como `databricks jobs submit` ad hoc (no se corrió
el job completo para no re-ejecutar el resto de la cadena de Silver/Gold sólo para validar una
rama nueva e independiente): ambos en verde. `sync_to_databricks.py` subió 3 archivos JSON reales
(2018-01-01/02/03). Consulta SQL directa contra el warehouse serverless confirmó
`weather.bronze.gefs_reforecast`: 3 días, 11 miembros distintos, 1.876.800 filas, `tp_mm` entre
0,0 y 347,0 mm (rango sano, sin negativos ni outliers evidentes).

### Volumen real medido — pendiente de decisión antes de correr el backfill completo

* Un día de 5 miembros produce **~164 MiB de JSON recortado** (463.200 registros); un día de 11
  miembros (corrida extendida semanal), ~338 MiB. Es una reducción enorme frente a los ~950 GB
  sin recortar (Decisión 026), pero **igual es un volumen no trivial acumulado**: el hueco
  prioritario 2000-01-01 → 2006-09-30 (~2.459 días, mayoría de 5 miembros) proyecta del orden de
  **~400 GB** de JSON recortado si se baja con los 5 miembros estándar completos; extender al
  solapamiento 2006-2019 para la calibración (Decisión 021) sumaría un orden de magnitud similar
  otra vez.
* **No se decidió todavía** si conviene reducir miembros (ej. sólo `c00`, o `c00`+1 perturbado)
  para el uso como feature de precipitación agregada por sub-cuenca — probablemente no hace falta
  el ensemble completo de 5-11 miembros si el destino final es un agregado por `alta_frontera`,
  pero **reducir miembros ahora sería una decisión de modelado tomada dentro de Landing**, un
  lugar equivocado según el principio ya usado en R8/R9 (Decisiones 019/023): las reglas de
  agregación y selección viven en Silver/Gold, no en Landing. Landing baja lo que la fuente
  publica; el recorte de miembros, si se decide, debería aplicarse ahí explícitamente y
  documentarse como tal.
* Pendiente de decidir con el usuario antes de lanzar el backfill completo (no bloquea lo ya
  implementado y verificado en esta decisión).

### Consecuencias

* El mecanismo de landing local + subida acotada para GEFS queda implementado y probado de punta
  a punta contra datos reales — la tarea "Landing + Bronze de GEFS v12 en local" de la Fase 4
  queda **mecánicamente resuelta**; lo que falta es correr el backfill completo (acotado por la
  decisión de volumen de arriba) y las tareas posteriores de la fase (calibración contra TIGGE,
  serie homogénea, recorte a `alta_frontera` en Silver/Gold).
* `docs/data_sources.md` §9.4 se actualiza de "investigada, no implementada" a implementada y
  verificada, con el gotcha de `dataType` documentado.
* `docs/roadmap.md` Fase 4 se actualiza: la tarea de Landing+Bronze pasa de pendiente a
  mecánicamente resuelta con una nota de la decisión de volumen abierta.

---

## Decisión 030: El backfill histórico de TIGGE (`cf`+`pf`) se mueve a ejecución local, con Task Scheduler

### Estado

`Aceptada` (2026-08-24), implementada y corriendo contra datos reales.

### Contexto

El backfill histórico de `cf`/`pf` (Decisión 012) corría como job de Databricks
(`ECMWF_Forecast_Historic_Backfill`), con `max_batches_per_run` acotado y disparado a mano
repetidamente. El usuario preguntó, mientras el backfill local de GEFS (Decisión 029) corría en
paralelo, si no convenía aplicar el mismo patrón a TIGGE: bajar en local (más control y
visibilidad) y subir solo el JSON ya aplanado — el mismo principio que ya rige
ANA/INMET/GEFS (Decisiones 015/016/025/029).

Al revisar, ya existían scripts locales espejo (`notebooks_local/ecmwf/historic_cf_tigge.py`,
`historic_pf_tigge.py`, con las credenciales de `cdsapi` ya configuradas en `~/.cdsapirc` del
usuario) que nunca se habían usado como vía de ejecución real — solo como espejo 1:1 de los
notebooks de Databricks. Convertirlos en la vía principal fue mecánico.

### Implementación

* `notebooks_local/ecmwf/run_tigge_backfill.py`: orquestador nuevo. Corre `cf` hasta agotar lo
  pendiente y **recién después** arranca `pf` — nunca los dos en paralelo (regla dura de la
  Decisión 012, sigue vigente corra donde corra: comparten cuenta/token con la misma cola de
  TIGGE/ECDS). Sincroniza cada `--sync-every-calls` llamadas exitosas.
* `notebooks_local/ecmwf/sync_to_databricks.py`: nuevo, sube en paralelo (mismo patrón que
  `gefs_reforecast/sync_to_databricks.py`) los JSON de `cf_tigge/json/` y `pf_tigge/json/` al
  mismo Volume/carpeta que ya lee `ETL_Bronze_ECMWF_CF`/`_PF` — Bronze no distingue si el
  archivo vino del job diario, del backfill de Databricks o de este backfill local.
* **Siembra de estado local sin re-descargar lo ya aterrizado**: `historic_cf_tigge.py`/
  `historic_pf_tigge.py` deciden qué lotes están completos mirando el disco local
  (`batch_fully_landed()`), que arrancaba vacío — sin sembrarlo, el backfill local hubiera
  vuelto a pedir los ~8 años de `cf` (2018-08→2026-08) y el mes de `pf` que **ya están en
  Bronze**, desperdiciando cuota de la cola de TIGGE/ECDS. Se listó el Volume real
  (`databricks fs ls`) y se crearon 2.941 archivos JSON vacíos (`cf`) y 30 (`pf`) con los
  nombres exactos ya presentes remotamente. Es seguro: `sync_to_databricks.py` sólo sube
  archivos que **no** están ya en el Volume por nombre, así que estos placeholders vacíos
  nunca se suben (ya existen remotamente con contenido real).
* **Lock dedicado, no el compartido**: `tigge_lock.py` (nuevo, mismo mecanismo que
  `ana_historic_backfill/lock.py` pero con su propio archivo). GEFS, ANA, INMET y TIGGE pegan
  contra APIs completamente distintas (S3 público, ANA, INMET, ECDS/TIGGE) y no hay motivo
  para serializarlos entre sí — de hecho corrieron en paralelo durante esta sesión sin
  problema. Compartir el lock de `ana_historic_backfill` (como hacían INMET/GEFS) hubiera
  bloqueado a TIGGE mientras GEFS seguía corriendo.

### Por qué Task Scheduler y no una corrida lanzada desde la sesión de Claude Code

Confirmado empíricamente (no en la documentación de ninguna herramienta): un proceso lanzado
en background desde esta sesión de Claude Code tiene un límite de vida no documentado, del
orden de 20-40 minutos, después del cual se lo mata sin que sea un crash del proceso ni un
error de código (mismo patrón visto y resuelto para el backfill de GEFS con un supervisor que
lo reinicia solo). Para GEFS esto no importa mucho: cada descarga tarda segundos, así que un
reinicio pierde poco. Para TIGGE, un solo request de `cdsapi.retrieve()` contra un año viejo
(2006-2018) puede tardar **más** que ese límite — confirmado con dos intentos consecutivos del
mismo lote (2017-08-23..2018-08-22) que nunca llegaron a completarse, sólo a quedar
`accepted` en la cola de MARS, antes de que el proceso fuera matado. Un supervisor que
reinicia el mismo request una y otra vez sin que nunca tenga tiempo de terminar no es una
solución — es un bucle infinito sin progreso.

La solución fue la misma que ya existía para el backfill de ANA (Decisión 016): una tarea
programada de Windows (`notebooks_local/ecmwf/scheduler/register_tasks.ps1`,
`run_backfill_task.ps1`), que no está sujeta al límite de la sesión — corre hasta completar o
hasta el `ExecutionTimeLimit` de 6 horas, con redisparo horario (`IgnoreNew`) para retomar si
se corta. Registrada y disparada manualmente el 2026-08-24; confirmado el proceso corriendo
bajo un PID de Task Scheduler, independiente de la sesión.

### Consecuencias

* El backfill histórico de `cf`+`pf` corre ahora en local, vía Task Scheduler, sin intervención
  manual repetida de "Run now" en Databricks.
* `docs/data_sources.md` §7.11 va a necesitar actualizarse cuando el backfill termine (vía de
  ejecución real, no la del job de Databricks) — pendiente, no bloqueante.
* El job `ECMWF_Forecast_Historic_Backfill` de Databricks queda sin uso activo pero no se
  elimina de `databricks.yml` en esta decisión — decisión de limpieza aparte, no urgente.
* Patrón reusable: cualquier backfill local futuro que dependa de un request individual lento
  (no descargas rápidas en paralelo como GEFS) debería usar Task Scheduler desde el principio,
  no un supervisor de sesión.

### Addendum (2026-08-24, mismo día): colisión real con el job de Databricks — pausado, no abandonado

Antes de moverse a local, se había intentado un supervisor que disparaba
`ECMWF_Forecast_Historic_Backfill` en Databricks repetidamente (`databricks jobs run-now`). El
primer intento pareció fallar por el mismo bug de mangling de rutas de MSYS que afectó otros
comandos de esta sesión (el archivo local donde se iba a guardar la respuesta nunca se creó) —
pero el **request a la API de Databricks sí se había enviado con éxito**: el job quedó
corriendo del lado de Databricks (run `221810619993260`, iniciado 20:48) sin que hubiera
ninguna confirmación visible localmente. La sesión asumió que el intento había fallado por
completo y siguió adelante con el backfill local (Decisión 030, arrancado ~21:59).

Resultado: **durante poco más de una hora, el job de Databricks (`Historic_ECMWF_CF` →
`Historic_ECMWF_PF`) y el backfill local (`cf` primero) corrieron en simultáneo**, ambos
pegándole a la misma cola de TIGGE/ECDS con la misma cuenta — exactamente la condición que la
Decisión 012 prohíbe. Se detectó al revisar `databricks jobs list-runs` sin filtro (no
`--job-id`) para chequear el estado del merge de Bronze de GEFS, y aparecer ahí una corrida de
`ECMWF_Forecast_Historic_Backfill` en estado `RUNNING` que no debía existir.

**Corrección aplicada:** se deshabilitó la tarea programada de Windows
(`Disable-ScheduledTask`), se mató el proceso local (`taskkill /T /F` sobre el PID del lock) y
se dejó correr únicamente el job de Databricks, que ya llevaba más de una hora de ventaja y
progreso real (`cf` completo, `pf` en curso). No se pudo determinar si la colisión causó algún
daño real (ej. throttling silencioso, cuota consumida) — no se evaluó como bloqueante porque
ambos procesos son resumibles por diseño (`batch_fully_landed()`/Bronze `MERGE`) y no hay
escritura destructiva en ningún punto.

**Lección operativa, para no repetir:** después de cualquier `databricks jobs run-now` (o
`submit`) cuyo resultado local no se pueda confirmar por un error de la propia sesión (no un
error de la API), verificar el estado real vía `databricks jobs list-runs` (sin `--job-id`,
trae las corridas más recientes de todo el workspace) **antes** de asumir que no se disparó y
de lanzar una vía alternativa que pueda competir por el mismo recurso. "No pude confirmarlo
localmente" no es lo mismo que "no pasó".

**Estado al cierre de esta sesión:** el backfill local de TIGGE queda con toda su
infraestructura lista (`run_tigge_backfill.py`, `tigge_lock.py`, `sync_to_databricks.py`,
Task Scheduler registrado pero deshabilitado) para retomarse en una sesión futura, una vez que
se confirme que el job de Databricks terminó o se decida cancelarlo explícitamente — no se
retoma automáticamente sin esa verificación previa, por la misma razón de este addendum.

---

## Decisión 031: Corrección del wrapper de Task Scheduler de TIGGE, parametro `format` deprecado, y hueco documentado por cinta danada de ECMWF

### Estado

`Aceptada` (2026-08-26), implementada y corriendo contra datos reales.

### Contexto

Al retomar la sesión, la tarea programada `TIGGE_Backfill_Download` (Decisión 030) llevaba
~9,5 horas fallando en silencio cada corrida horaria: exit code 1, log sin ninguna salida de
Python, lock huérfano (el `finally: lock.release()` nunca corría). El reporte de la sesión
anterior decía que la tarea había quedado deshabilitada (ver addendum arriba) — no era así: el
`Disable-ScheduledTask` de esa sesión no sobrevivió, o nunca se aplicó a esta tarea, y siguió
disparando sola cada hora sin que nadie lo supervisara.

### Causa raíz #1: `2>&1`/`*>>` de PowerShell sobre un comando nativo, con `$ErrorActionPreference = "Stop"`

`run_backfill_task.ps1` capturaba la salida de `python.exe` con el operador nativo de
redirección de PowerShell (`*>>`). `cdsapi` loguea mensajes informativos ("Request ID is...",
"status has been updated to...") por **stderr** en cada corrida, incluso exitosa. En
PowerShell 5.1, redirigir el stderr de un ejecutable externo así lo envuelve en un
`NativeCommandError` — con `$ErrorActionPreference = "Stop"` (ya seteado arriba en el script)
eso aborta el script **al instante**, antes de que Python imprima nada y sin pasar por el
`finally` de `tigge_lock.py`. Confirmado reproduciendo el wrapper exacto a mano: mismo exit
code 1, mismo log vacío.

Un primer intento de arreglo (`2>&1 | Out-File -Encoding utf8`, para además resolver que el
log mezclaba UTF-8 del header con UTF-16 de la salida de Python) tenía el mismo problema —
detectado probándolo a mano antes de confiarlo al scheduler. **Arreglo real:** redirigir vía
`cmd /c "... >> log 2>&1"` — la redirección ocurre a nivel de SO, sin que PowerShell
reinterprete el stderr del proceso nativo como un error propio.

Un segundo síntoma relacionado, ya con el fix de `cmd /c` puesto: una corrida murió con
`STATUS_CONTROL_C_EXIT` (`^C` literal en el log) exactamente en una ventana donde la sesión de
Claude Code estaba parando un proceso de prueba propio con comandos de PowerShell
(`Get-Process`, `TaskStop`) — indicio de que administrar procesos con el tool de PowerShell de
la sesión puede propagar una señal de Ctrl+C al proceso del scheduler. No se investigó el
mecanismo exacto; la mitigación aplicada fue dejar de usar el tool de PowerShell para
consultar/administrar procesos mientras hay una corrida real en curso (se usa `schtasks` desde
Bash para disparar la tarea, y sólo lectura de archivos para monitorear).

### Causa raíz #2 (secundaria, de bajo impacto): parámetro `format` deprecado por ECDS

`cdsapi` acepta hoy `"data_format"` en vez de `"format"` — corregido en los 4 scripts locales
(`historic_cf_tigge.py`, `historic_pf_tigge.py`, `landing_cf_tigge.py`, `landing_pf_tigge.py`).
Verificado que **no** es lo que rompe el job diario de Databricks (`ECMWF_Forecast_Daily_Incremental`,
últimas 5 corridas en `SUCCESS`) — los notebooks de Databricks siguen con `format` y no hace
falta sincronizar el cambio con urgencia.

### Causa raíz #3 (la que realmente bloqueaba el avance): cinta dañada en el archivo de ECMWF

Con las dos causas anteriores resueltas, el mismo lote (`cf` 2017-08-25..2018-08-24) seguía
fallando. El `print` de `_retrieve_batch` trunca el error a 300 caracteres; reproduciendo la
request a mano se obtuvo el mensaje completo:

```
AccessError: Requested data is on one or more damaged tape: J0018900.
https://confluence.ecmwf.int/display/UDOC/MARS+data+unavailability+in+ECMWF+tape+library
```

Es un problema de infraestructura de ECMWF (tape física dañada), no de la request ni de este
pipeline. Reintentar no sirve — por eso el mismo lote bloqueaba el orquestador desde ayer:
`run_source()` corta toda la fuente `cf` en el primer fallo, y como el lote más nuevo pendiente
siempre es el mismo (los lotes se recalculan desde hoy hacia atrás), cada disparo horario volvía
a chocar contra el mismo punto sin poder llegar a los lotes más viejos.

**Decisión del usuario:** este tramo (2006-2019) es sólo para calibrar el empalme GEFS/TIGGE
(Fase 4) — quedan otros ~12 años de solapamiento, así que perder este año no es crítico.
Se saltea explícitamente en vez de investigar si es parcialmente recuperable.

### Implementación del skip

* `historic_cf_tigge.py`: `KNOWN_UNAVAILABLE_RANGES` (lista de `(inicio, fin, motivo)`) y
  `_known_unavailable_reason(start, end)`, comparando por **solapamiento** contra una ventana
  generosa (2017-06-01..2018-11-30) — no por igualdad exacta, porque el rango exacto de cada
  lote corre ~1 día por día respecto de `date.today()` (`TIGGE_LAG_DAYS`/`BATCH_MONTHS`), así
  que una tupla de fechas fija dejaría de matchear al día siguiente. El `for` principal de
  `run()` saltea el lote (imprime el motivo, `continue`) en vez de tratarlo como fallo fatal.
* `run_tigge_backfill.py._pending_batches()`: sin excluir también acá los lotes marcados como
  no disponibles, el conteo de pendientes nunca llega a 0 y el `while True` de `run_source()`
  queda en loop infinito llamando a `module.run()` sin ningún progreso posible (bug encontrado
  antes de que llegara a producirse, al razonar la implementación — no se observó en una
  corrida real).
* **Alcance: sólo `cf`.** No se confirmó que `pf` pegue contra la misma cinta (todavía no llegó
  a pedir ese rango) — `historic_pf_tigge.py` no define `KNOWN_UNAVAILABLE_RANGES`, así que si
  el mismo problema aparece ahí se va a frenar igual que antes, no se saltea solo.

### Verificado contra datos reales

Corrida real disparada después del fix (2026-08-26 ~08:16): saltó los dos lotes que se
solapan con la cinta dañada (2016-2017 y 2017-2018, cada uno con el motivo impreso), y bajó de
verdad el siguiente lote real (2015-08-25..2016-08-24, 16,9 MB) — primera descarga histórica
nueva desde el 2026-08-25 12:36. Quedan ~7 lotes reales de `cf` (2006-2015).

### Consecuencias

* `docs/data_sources.md` §7.11/§9 (o donde corresponda documentar TIGGE) va a necesitar una
  nota sobre el hueco de cobertura 2017-06..2018-11 en `cf` cuando se cierre la Fase 4 —
  pendiente, no bloqueante.
* Si `pf` encuentra el mismo problema en el mismo rango, extender `KNOWN_UNAVAILABLE_RANGES` a
  `historic_pf_tigge.py` (o moverlo a `common_ecmwf.py` si termina siendo compartido) en vez de
  duplicar la lógica.


---

## Decisión 032: Los modelos de pronóstico numérico de Brasil (CPTEC/INPE) se evalúan y no se incorporan por ahora

### Estado

`Aceptada` (2026-08-26). Investigación cerrada con criterio de reapertura definido; sin código.

### Contexto

El usuario preguntó si Brasil tiene un sistema de pronóstico meteorológico propio, si es gratuito y
cómo se descargan datos actuales e históricos. La pregunta es pertinente porque la sub-cuenca de la
tesis (`alta_frontera`) está enteramente en Brasil y el pronóstico hoy sale sólo de ECMWF (TIGGE
`cf`/`pf`, Open Data `fc`) y de NOAA (GEFS Reforecast v12 para 2000-2019, Decisión 021).

### Qué se encontró (verificado contra los servidores reales el 2026-08-26)

* **CPTEC/INPE tiene un sistema NWP completo, abierto y sin registro**, servido por HTTP en
  `dataserver.cptec.inpe.br` (las URLs viejas de `ftp.cptec.inpe.br/modelos/tempo` redirigen ahí).
  Modelos con archivo: WRF 7 km (00Z, +180 h horario, GRIB2 ~204 MB/paso, **2023-01 → hoy**), Eta 8 km
  (00Z/12Z, +264 h, **2021-07 → hoy**), Eta 40 km (00Z, +264 h, GRIB1 12 MB/paso, **2020-07-16 → hoy**,
  el más largo), BAM 20 km global (recortes **2024-08 → hoy**), MONAN 10 km global pre-operativo
  (NetCDF de 4,3 GB por paso, continuo **2025-10 → hoy**). Detalle y patrones de URL en
  `data_sources.md` §9.5.
* WRF y Eta 8 km publican un `.inv` estilo `wgrib2` y el servidor acepta `Range`: se puede bajar sólo
  `APCP` (874 KB en vez de 204 MB por paso, verificado). `APCP` del WRF viene acumulado desde el inicio
  (como `tp` de TIGGE); el de Eta 8 km es incremento horario (como GEFS).
* **Lo que no existe:** ningún *reforecast* ni archivo anterior a 2020-07; ningún ensemble público
  vigente (el de BAM terminó en 2020-04 y CPTEC dejó de aportar a TIGGE alrededor de 2010); INMET no
  expone más el GRIB de COSMO (el FTP rechaza el login anónimo); ONS sólo distribuye pronósticos por
  cuenca a agentes registrados (SINtegre).

### Decisión

* **No se incorpora ningún modelo brasileño como `forecast_source` en esta etapa.** La Fase 4 sigue
  con TIGGE + GEFS: son las únicas fuentes que cubren 2000-2019, y el dataset arranca en 2000-01-01
  (Decisión 019 enmendada / 021). Un modelo que arranca en 2020 no reemplaza a ninguna de las dos.
* La investigación queda registrada en `data_sources.md` §9.5 para no repetirla.
* **Criterio de reapertura:** si en la etapa de modelado se quiere una comparación de habilidad entre
  sistemas de pronóstico sobre `alta_frontera` (material de tesis, no de ingeniería), la opción con
  historia útil es **Eta 40 km (2020 →, ~3 GB/día entero)** o **WRF 7 km (2023 →, sólo `APCP` por
  byte-range ≈ 160 MB/día)**, como tercera `forecast_source` sobre el tramo 2020-hoy, con el mismo
  patrón de landing local de GEFS. No como reemplazo.

### Justificación

Sumar una tercera familia de pronóstico ahora agrega volumen y trabajo de empalme sin resolver
ningún hueco del dataset: el problema de cobertura (2000-2006) ya lo cierra GEFS y el tramo
operativo ya lo cubre TIGGE. La comparación de habilidad es valiosa, pero es una pregunta de
modelado que conviene formular cuando exista el baseline, no antes.

### Consecuencias

* `roadmap.md` §5 registra la investigación D como cerrada y §6 deja el tema como *diferido*, no
  como *fuera de alcance*.
* Hallazgo lateral de la misma investigación: CPTEC publica además **observaciones en grilla** con
  historia larga (MERGE desde 1998, SAMeT desde 2000) — eso sí cierra una necesidad real y se
  incorpora por la Decisión 033.

---

## Decisión 033: MERGE (lluvia) y SAMeT (temperatura) de CPTEC/INPE entran como observación en grilla, con histórico local y camino diario Bronze → Silver → Gold en Databricks

### Estado

`Aceptada` (2026-08-26), implementación en la **Fase 9** de `roadmap.md` (corre en paralelo con las
demás fases). Verificación contra Databricks real al final de esta decisión.

### Contexto

Al investigar los modelos NWP de Brasil (Decisión 032) aparecieron dos productos **observados** de
CPTEC/INPE, gratuitos y con historia larga: **MERGE** (precipitación diaria 0,1°, satélite GPM-IMERG
V07B + pluviómetros, desde 1998-01-02) y **SAMeT** (temperatura TMAX/TMED/TMIN diaria 0,05°,
observaciones + ERA5 corregido por *lapse rate*, desde 2000-01-01). Hoy la lluvia y la temperatura
de `alta_frontera` en Gold salen de agregados por estación (ANA e INMET): dependen de qué estaciones
reportan cada día (`*_cobertura_pct`) y de la posición de la red. Una grilla observada que cubre el
100% de la sub-cuenca todos los días es una segunda medición de la misma variable, con cobertura
espacial completa. El usuario fijó tres requisitos: documentar la fuente, descargar **todo** el
archivo disponible y evaluarlo, y —lo más importante para la tesis y para operar— que el **dato del
día anterior esté disponible a diario para inferir**, no sólo para entrenar/testear; con el histórico
descargado en local y subido a Bronze, y el diario como pipeline en Databricks con todo el camino
Bronze → Silver → Gold.

### Qué se verificó antes de escribir código (regla de §10 de `data_sources.md`)

* **Latencia diaria (viabilidad del requisito operativo):** MERGE del día D aparece a las **02:39-02:40
  UTC de D+1** (seis días consecutivos medidos); SAMeT TMED/TMAX de D a las **03:02-03:08 UTC de D+1**
  y TMIN de D a las 17:06 UTC del mismo D. Todo antes de las 04:30 Montevideo de Gold. **Viable.**
* **Ventanas diarias:** MERGE acumula **12Z(D-1) → 12Z(D)** (paper Rozante 2024 y verificado sumando
  horarios de un día lluvioso: correlación 0,95 contra 0,62 del día calendario). SAMeT usa el **día
  calendario UTC**, igual que `temperature_daily` (verificado contra INMET horario de Bronze en 7
  estaciones de `alta_frontera`: MAE 0,15 °C en las tres variables; las ventanas 12Z dan 1-2,6 °C).
* **Regeneración posterior (el hallazgo que más condiciona el diseño):** CPTEC reescribe MERGE **en
  los primeros días del mes siguiente** (pluviómetros completos) y SAMeT **a los 7 días** (ERA5, lo dice
  su READ-ME); además ambas bases fueron reconstruidas enteras (MERGE 2025-05-04/06 con V07B, SAMeT
  2022-06-01). Medido con `Last-Modified` HTTP sobre archivos de distintas edades.
* **Formato:** MERGE es GRIB2 con empaquetado complejo con diferenciación espacial y *missing value
  management* (dos mensajes: precipitación etiquetada `rdp` y NEST —pluviómetros por punto— etiquetada
  `prmsl`); SAMeT es NetCDF4 (`tmed|tmax|tmin` + `nobs`). Decodificar GRIB2 en Databricks serverless con
  `cfgrib`/`eccodes` aborta el kernel (Decisión 013), así que **se probó `pygrib` en el workspace real
  antes de diseñar** (`run 496772049564049`, `SUCCESS`; `grib2io` no instala). `netCDF4` ya se usa en
  `Daily_ECMWF_CF` sin problema.
* **Cobertura espacial:** ambas grillas cubren la cuenca completa; SAMeT sólo tiene NaN en el océano de
  la esquina SE del bounding box, fuera de las tres sub-cuencas. Puntos por sub-cuenca: MERGE 566 /
  1.187 / 482, SAMeT 2.269 / 4.749 / 1.922.

### Decisión y diseño

1. **Histórico en local, diario en Databricks — mismo formato de aterrizaje.** `notebooks_local/cptec_obs/`
   descarga todo el archivo (MERGE 1998 →, SAMeT 2000 →) en paralelo, recorta al bounding box de las 3
   sub-cuencas y escribe **un Parquet por producto y día** (`MERGE_AAAA_MM_DD.parquet`,
   `SAMET_AAAA_MM_DD.parquet`). `Daily_CPTEC_Obs.ipynb` (Databricks serverless) produce exactamente el
   mismo archivo para D-1 y una ventana hacia atrás. Bronze no distingue de dónde vino cada archivo
   (mismo principio que el backfill de TIGGE, §7.11).
2. **Parquet, no JSON (desviación consciente del patrón GEFS/ECMWF):** SAMeT son ~20.300 puntos × ~9.700
   días ≈ 200 M de filas; en JSON aplanado serían ~25 GB, en Parquet ~3,3 GB. Spark lo lee nativo y el
   Landing diario lo escribe con `pyarrow`. MERGE pesa ~130 MB en total.
3. **Recorte espacial en dos pasos:** Landing baja el bounding box (sin geometría, como ECMWF/GEFS);
   Silver asigna cada punto a su sub-cuenca con **`weather.silver.grid_subcuenca`** (centros de celda
   dentro del polígono real, calculado en local con `geopandas` por `build_grid_subcuenca.py` y sembrado
   desde el Volume por el DDL). Es el equivalente en grilla de `estacion_subcuenca` (Decisión 024) y
   respeta la Decisión 011: la regla de negocio vive en Silver.
4. **Regeneración → versión explícita.** Cada registro lleva `source_last_modified` (Last-Modified HTTP).
   El Landing diario compara la cabecera del origen con el Parquet ya landeado y re-baja sólo lo que
   cambió (ventana de 45 días para MERGE, 14 para SAMeT); Bronze hace `MERGE` por
   `(fecha, latitude, longitude)` y **actualiza** cuando llega una versión más nueva; Silver recalcula la
   ventana incremental (60 días) y expone **`es_preliminar`** (MERGE: el archivo no fue tocado después de su publicación
   inicial, `source_last_modified < fecha + 2 días` — un umbral fijo por mes clasificaba mal los meses
   regenerados el día 1, como julio 2026; SAMeT: modificado antes de D+7). Gold propaga el flag. Así la inferencia a D+1 usa el dato preliminar
   —el único que existe— y lo declara; el entrenamiento, semanas después, ya ve el definitivo.
5. **Silver agrega por `(fecha, subcuenca, fuente)`:** media areal (`prec_media_mm`, `temp_media_c`,
   `temp_max_c`, `temp_min_c` como medias areales de las tres variables), máximos, `cobertura_pct`
   (= puntos con dato / puntos de la sub-cuenca, R8: cobertura como columna, sin portón), densidad de
   observaciones (`pluviometros`, `puntos_con_pluviometro`, `nobs_total`). Bronze tiene
   `CLUSTER BY (fecha)` y el `MERGE` acota por rango de fechas para podar.
6. **Gold suma 12 columnas de `alta_frontera`**, que **conviven** con las de estación (no las
   reemplazan): `lluvia_merge_alta_frontera_mm`, `_max_mm`, `_acum_3d_mm`, `_acum_7d_mm`, `_pluviometros`,
   `_cobertura_pct`, `_es_preliminar` y `temp_samet_alta_frontera_media_c`, `_max_c`, `_min_c`,
   `_cobertura_pct`, `_es_preliminar`. La ventana 12Z-12Z de MERGE queda declarada (los acumulados de
   3/7 días la vuelven irrelevante; el día puntual no).
7. **Jobs:** nuevo `CPTEC_Obs_Daily_Incremental` a las **03:40 Montevideo** (DDL → Landing → Bronze →
   Silver), después de la publicación de ambos productos y antes de Gold (04:30).
   `Silver_Gold_Initial_Load_v0` incorpora DDL + Bronze (full) + Silver (full) de CPTEC antes de Gold;
   `Silver_Gold_Daily_Incremental` incorpora Silver (incremental) antes de Gold. **CPTEC no entra en
   `Check_Bronze_Freshness`:** un corte del servidor de CPTEC no debe frenar Gold; la fila queda en
   `NULL` y `cobertura_pct`/`es_preliminar` lo declaran.
8. **Carga masiva a Bronze por ZIP:** con ~20.000 Parquet, un `databricks fs cp` por archivo tarda
   horas; `sync_to_databricks.py --bundle` sube ZIP sin compresión a `staging/` y
   `ETL_Bronze_CPTEC_Obs` los descomprime en `daily/` antes de leer.

### Justificación

Tener el histórico completo (28 años de lluvia, 26 de temperatura, sin huecos) en el mismo formato que
el diario elimina el problema clásico de "una fuente para entrenar y otra para operar". Exponer la
regeneración como columna (`es_preliminar`) en vez de esperar la versión final mantiene el requisito de
las 06:00 (Fase 5) sin mentir sobre la calidad del dato. Probar `pygrib` en el workspace real antes de
diseñar evitó repetir el callejón de la Decisión 013 y permitió cumplir el pedido de que el diario
corra en Databricks, no en local.

### Consecuencias

* Nuevas tablas: `weather.bronze.merge_precip_grid`, `weather.bronze.samet_temp_grid`,
  `weather.silver.grid_subcuenca`, `weather.silver.precip_grid_daily`, `weather.silver.temp_grid_daily`;
  Volume `weather.raw.cptec_volume`. 12 columnas nuevas en Gold (entran al diccionario de la Fase 6).
* `data_sources.md` §9.6/§9.7 documentan las fuentes; `docs/cptec_obs_evaluation.md` es el reporte
  generado por `evaluate_cptec_obs.py` sobre el archivo completo.
* Bug encontrado y corregido en el test local: sin reemplazar `missingValue` (9999) del *missing value
  management*, NEST daba "pluviómetro en todos los puntos". Está documentado en `common_cptec.py`.
* Desprolijidad encontrada al generar notebooks por script: nbformat exige `execution_count`/`outputs`
  en las celdas de código y Databricks rechaza el notebook si faltan ("may not be a valid notebook") —
  corregido antes de la primera corrida real.
* **Verificado contra Databricks real (2026-08-26):** histórico completo cargado (MERGE 58.645.115 filas
  1998-01-02→hoy, SAMeT 197.386.052 filas 2000-01-01→hoy, 0 huecos en ambos); `Silver_Gold` corrido en
  modo `full` tras agregar las 12 columnas con `DDL_Silver_Gold` (paso que se había olvidado ejecutar la
  primera vez — el `ALTER TABLE` vive en un notebook separado de `ETL_Gold_Training_Dataset_v0` y no se
  corre solo): **100% de las 9.732 filas de Gold (2000-01-01→2026-08-23) quedan con
  `lluvia_merge_alta_frontera_mm` y `temp_samet_alta_frontera_media_c` no nulos**. `Validate_Training_
  Dataset_v0` en verde. Reporte completo en `docs/cptec_obs_evaluation.md`: 0 días faltantes en el
  archivo completo de ambos productos; MERGE-estaciones correlación diaria 0,895 (mensual 0,898);
  SAMeT-INMET sesgo -0,05 °C en media (correlación 0,991). **Hallazgo abierto, no bloqueante:** el
  cociente lluvia anual MERGE/estaciones cae de ~0,9 a 0,71/0,48/0,58 en 2023-2025 sin que la cobertura
  de estaciones baje (sube de 0,13 a 0,20) — sugiere una estación ANA nueva con posible error de
  unidades, a investigar en la Fase 3, no en esta decisión.

---

## Decisión 039: `mlflow.pytorch.log_model` no se puede usar sin pandas — Rio_Search loguea modelos PyTorch como artefacto plano (state_dict), no con el flavor de alto nivel

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow real en la **Fase 0** de
`rio_search_plan.md` (run `smoke`, `/Users/joaquintschopp@gmail.com/rio_search/smoke`).

### Contexto

Decisión #9 de `rio_search_plan.md` prohíbe pandas como dependencia del backend de Rio_Search
(Polars en su lugar) y elige `mlflow-skinny` en vez de `mlflow` completo por lo mismo. El riesgo ya
estaba anticipado en la tabla de riesgos del plan (§6): *"`mlflow-skinny` no cubre algún camino (p. ej.
`log_model` o `MetaDataset`) sin pandas"*, con la mitigación *"el run `smoke` de la Fase 0 ejercita
exactamente esos caminos; si alguno falla, se aísla en un adaptador y se registra la Decisión"*. Este
es ese hallazgo.

### Qué se verificó

Con `mlflow-skinny==3.15.2` instalado (sin `pandas` en el entorno, `torch==2.6.0+cu124`,
`databricks-sdk==0.133.0`, todo vía `uv sync` en `rio_search/backend`):

* `import mlflow` y `mlflow.set_tracking_uri("databricks://joaquintschopp@gmail.com")` funcionan sin
  pandas.
* `from mlflow.data.meta_dataset import MetaDataset` y `from mlflow.data.uc_volume_dataset_source
  import UCVolumeDatasetSource` funcionan sin pandas — `MetaDataset` es exactamente lo que pedía la
  Decisión #11/§3.5 (nombre, digest y origen del dataset sin materializarlo).
* `import mlflow.pytorch` **falla** con `ModuleNotFoundError: No module named 'pandas'`: el archivo
  `mlflow/pytorch/__init__.py` hace `import pandas as pd` sin condicionar en el top-level del módulo
  (usado por el wrapper `pyfunc` que ese flavor genera). No es un camino interno opcional: cualquier uso
  de `mlflow.pytorch.log_model(...)` obliga a importar el submódulo completo.

### Decisión

**Rio_Search no usa `mlflow.pytorch.log_model` en ningún adaptador.** En su lugar, todo modelo PyTorch
se serializa con `torch.save(model.state_dict(), ...)` y se sube como artefacto plano vía
`mlflow.log_artifacts(tmp_dir, artifact_path="model")`, junto con metadatos propios en JSON
(arquitectura, hiperparámetros) que reemplazan al `MLmodel`/signature que generaría el flavor. Esto se
verificó en el run `smoke` de la Fase 0 (`infrastructure/tracking/smoke.py`): modelo de juguete
logueado en `model/model_state_dict.pth` + `model/architecture.json` + `model/README.md`, sin pandas en
el entorno (`test_no_pandas_in_env` en verde).

Consecuencia directa para la **Fase 3** (`rio_search_plan.md`, checklist de la fase): el ítem
*"`mlflow.pytorch.log_model` con *signature* y `code_paths`"* se reinterpreta como *"artefacto plano con
`torch.save` + metadatos propios (arquitectura, hiperparámetros) + `code/` para procedencia (§3.13),
sin el flavor `mlflow.pytorch`"*. `ModelAdapterPort.save`/`load` (§3.3) implementan esa serialización
directamente; el checkpoint sigue guardándose en CPU (`state_dict` con `map_location`) como ya preveía
§3.4. Si una versión futura de `mlflow`/`mlflow-skinny` corrige el import incondicional de pandas, se
puede reevaluar sin cambiar el dominio ni la aplicación (el adaptador es el único punto de contacto).

### Justificación

Instalar `pandas` sólo para destrabar `mlflow.pytorch.log_model` violaría la Decisión #9 en su propio
propósito (el punto del run `smoke` es probar que no hace falta) y además el propio
`test_no_pandas_in_env` de la Fase 0 lo bloquearía. El costo de no usar el flavor de alto nivel es
perder la generación automática de `signature`/`MLmodel`/entorno conda del modelo — funcionalidad que
Rio_Search puede reconstruir a mano (ya versiona `features/spec.json`, `preprocess/pipeline.pkl` y
`env/uv.lock` como artefactos propios, §3.5) sin depender de esa capa de MLflow.

### Consecuencias

* `rio_search/backend/rio_search/infrastructure/tracking/smoke.py` documenta el hallazgo en su
  docstring y sirve de referencia de implementación para el `ModelAdapterPort` real de la Fase 3.
* No cambia nada de `mlflow.sklearn` (Fase 9, modelos no-DL): a evaluar en su momento si el mismo
  problema aplica a ese flavor antes de usarlo.
* `MetaDataset` + `UCVolumeDatasetSource` sí funcionan sin pandas y se usan tal como estaban diseñados
  en §3.5, sin cambios.

---

## Decisión 040: Baselines naive con `sequence.lookback_days: 1` + historial completo inyectado — no pasan por `BuildFeatureMatrix`; skill vs. persistencia siempre contra el mismo adaptador registrado

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow real en la **Fase 2** de
`rio_search_plan.md` (3 búsquedas reales en `/Users/joaquintschopp@gmail.com/rio_search/baselines`:
`persistence`, `climatology`, `seasonal_naive`).

### Contexto

§3.3 del plan dice que los modelos naive (`persistence`, `climatology`, `seasonal_naive`) "usan la
misma interfaz" (`ModelAdapterPort`) que el resto de los modelos, construida alrededor de `Sequences`
(ventana `lookback_days` → tensor `(N, lookback, n_features)`, Fase 1). Pero los tres baselines de esta
fase no usan features en el sentido de la Fase 1 (§3.6): "los modelos naive no usan features, solo el
propio target rezagado" (aviso del agente principal al abrir esta fase). Encajarlos en el mismo
mecanismo de ventaneo que usará un BiLSTM (Fase 3) generó dos problemas reales, encontrados durante la
implementación:

1. **Colapso de anclas evaluables.** `BuildSplit` (Fase 1) filtra cada split (`train`/`val`/`test`) al
   `pl.DataFrame` completo cortado por fecha *antes* de ventanear, a propósito, para que ninguna ventana
   cruce el límite de su split (invariante de no-fuga). Con `rolling_365`, `val` y `test` tienen
   **siempre exactamente 365 filas** cada uno (se verifica algebraicamente a partir de las fórmulas de
   §3.6, independiente del `embargo_days`). Si `seasonal_naive` usara una ventana de 365 días
   (`lookback_days: 365`) para poder "mirar" el valor de hace un año dentro de la propia `Sequences.X`,
   `SequenceBuilder` produciría **una sola ancla** por split (`n_windows = 365 - 365 + 1 = 1`):
   inservible para calcular métricas por horizonte.
2. **Contaminación de fechas fuera de TRAIN.** El mismo truco aplicado a `climatology` (para reconstruir
   la serie diaria completa de TRAIN a partir de ventanas superpuestas) arrastraría ~364 días *antes* de
   `split.train_window.start` configurado, violando en la letra (aunque no en el espíritu: son datos
   pasados, no del futuro) la invariante de "el estadístico se ajusta solo con TRAIN" (§3.2).

### Decisión

Los tres YAML de baseline (`configs/experiments/{persistence,climatology,seasonal_naive}_baseline_v1.yaml`)
fijan **`sequence.lookback_days: 1`**: cada fila de un split es una ancla evaluable propia (cobertura
completa de `val`/`test`, sin pérdida de filas por ventaneo) y, para `climatology`, `train.anchor_dates`
+ `train.X[:, -1, 0]` cubren *exactamente* los días de TRAIN configurados, sin contaminación.

`seasonal_naive` (que sí necesita mirar 365 días atrás) no amplía la ventana: `RunSearch`
(`application/experiments/run_search.py::_full_history`) arma la serie diaria completa del target
(fecha, valor) a partir del **dataset completo sin recortar por split** — legítimo porque
`anchor + h − 365` es siempre anterior al propio `anchor` (margen ≥ 351 días para cualquier horizonte
≤ 14): nunca mira al futuro respecto de la fecha "as of" de la predicción, sea cual sea el split al que
pertenezca en el calendario (TRAIN/VAL/TEST son cortes arbitrarios sobre una misma serie ya observada;
la invariante de "solo TRAIN" protege el *ajuste* de estadísticos —climatology sí la respeta—, no que un
baseline sin estado deje de usar valores ya observados). Esa serie se entrega vía un método extra,
`set_history(dates, values)`, que **no** forma parte de `ModelAdapterPort` (Protocol, §3.3): Python
verifica conformidad estructuralmente, así que agregar un método extra no rompe nada, y `RunSearch` lo
invoca con `hasattr(adapter, "set_history")` para cualquier adaptador que lo declare, no solo este.
Consecuencia práctica: **los baselines naive no pasan por `BuildFeatureMatrix`** (Fase 1) — construyen
su `Sequences`/`Targets` directamente desde el split filtrado, con `feature_columns=[target.actual_column]`
(`caudal_actual_m3s` / `nivel_rio_actual_m`, nueva propiedad `TargetVariable.actual_column`). Por esto,
**el bug heredado de la Fase 1 en `transforms.build_expressions`** (el glob `"caudal_*"` sin resolver del
YAML de ejemplo `bilstm_baseline_v1.yaml`) **no se pisó en esta fase**: ningún YAML de baseline naive
declara `features.experimental_transforms`. Sigue pendiente para la Fase 3, que si reutiliza ese YAML de
ejemplo tal cual, lo va a encontrar.

Para el *skill score* (§3.7, `1 − RMSE_modelo / RMSE_persistencia`), `RunSearch` no recalcula la fórmula
de persistencia por separado: en cada trial instancia un `PersistenceAdapter` **del mismo
`ModelRegistry`** (`REFERENCE_MODEL_NAME = "persistence"`) y lo corre sobre los mismos `Sequences` de
`val`/`test` que el modelo evaluado. Cuando el modelo evaluado *es* `persistence`, el adaptador de
referencia y el evaluado producen arrays bit a bit idénticos (misma clase, misma entrada), y
`skill_score` da `0.0` exacto en punto flotante (`1 − x/x == 0.0` para `x != 0`) — no una aproximación.
Verificado contra las 3 corridas reales: `test/skill_vs_persistence/h01..h14` y `val/…` = `0.0` exacto
en los 16 valores del run `persistence` (run_id `e0d84e3e06aa4fa3b0ca0fbd5513abe8`), y valores no-nulos
y distintos de cero en `climatology` (`h01 = -0.354…`) y `seasonal_naive` (`h01 = -0.633…`), como se
espera de una serie con autocorrelación diaria alta.

También se fija la convención de `KGE` cuando la predicción es constante (`std(sim) == 0`, p. ej. un
modelo que predice siempre la media): la correlación de Pearson es matemáticamente indefinida (0/0); se
toma `r = 0` por convención de la literatura de KGE (Knoben et al. 2019), lo que reproduce el resultado
de referencia citado en el plan (§5): `KGE = 1 − √2 ≈ −0.41421`, verificado con test exacto
(`tests/test_metrics.py::test_kge_of_predicting_the_mean_is_minus_0_41`).

### Justificación

Forzar a los baselines a pasar por el mismo `BuildFeatureMatrix`/ventaneo largo que usará el BiLSTM
(Fase 3) hubiera sido más "uniforme" en apariencia, pero rompía la propiedad que el criterio de cierre
de esta fase exige verificar (métricas por horizonte reales, no un solo punto por split) y violaba en la
letra la invariante de TRAIN-only de climatology. `lookback_days: 1` + `set_history()` resuelve ambos
problemas sin tocar `SequenceBuilder`/`TargetBuilder`/`BuildSplit` (Fase 1, ya cerrada y testeada) ni el
contrato de `ModelAdapterPort`: los adaptadores futuros (Fase 9: `ridge`, `lightgbm`) que sí necesiten
`lookback_days` largo y features reales usan el camino completo (`BuildFeatureMatrix`) sin que este
diseño se los impida.

### Consecuencias

* `RunSearch` (Fase 2) **no** soporta todavía `horizon_strategy: per_horizon` (Fase 3, "en la
  aplicación", §3.3) ni el bloque `search:` de grid/random/tpe (Fase 3, Optuna): los tres YAML de
  baseline son búsquedas de un solo trial (`ExperimentConfig.trials()` devuelve `(self,)`).
* La Fase 3 (BiLSTM), al construir su propio YAML con `features.groups`/`experimental_transforms` reales,
  **va a pisar el bug de `transforms.build_expressions` con globs** (heredado de la Fase 1) si reutiliza
  `bilstm_baseline_v1.yaml` tal cual: tiene que resolver el glob `"caudal_*"` contra el catálogo de
  columnas antes de llamar a `build_expressions`, o reemplazarlo por una lista explícita en el YAML.
* Corrección de tooling menor: `pyproject.toml` (`[tool.pytest.ini_options]`) no tenía `addopts` para
  excluir `integration` por default — el comentario del propio marcador ("offline por defecto salvo
  estos") no se cumplía hasta que apareció el primer test marcado `integration`
  (`tests/test_run_search_integration.py`, esta fase): un `pytest` liso corría igual los tests contra
  Databricks real. Se agregó `addopts = "-m 'not integration'"`.

---

## Decisión 041: El glob `"caudal_*"` de `transforms.build_expressions` (heredado de la Fase 1) se resuelve expandiéndolo contra las columnas ya seleccionadas de `features.groups`

### Estado

`Aceptada` (2026-08-27), verificada offline (`tests/test_build_feature_matrix.py`) y contra
Databricks/MLflow real en la **Fase 3** de `rio_search_plan.md` (`RunSearch` con `bilstm`, family
`torch`, primera vez que un modelo que no es `naive` pasa por `BuildFeatureMatrix`).

### Contexto

Las Fases 1 y 2 (`decisions.md` 040) ya habían identificado y documentado el bug sin resolverlo:
`infrastructure/preprocess/transforms.py::build_expressions` construye una expresión Polars por
columna declarada en `ExperimentalTransformSpec.columns` (`pl.col(column)...`), y `pl.col("caudal_*")`
**no** es un glob para Polars — es un nombre de columna literal que no existe en
`weather.gold.training_dataset_v0`. El YAML de ejemplo del plan (`configs/experiments/
bilstm_baseline_v1.yaml`, §4.1) declara justamente `{name: log1p, columns: ["caudal_*",
"caudal_agregado_alta_frontera_m3s"]}`. Los baselines naive de la Fase 2 no lo pisaron porque
(Decisión 040) no pasan por `BuildFeatureMatrix`; el BiLSTM de la Fase 3 sí, y lo ejercitó de
inmediato al construir `configs/experiments/bilstm_baseline_v1.yaml` real.

### Decisión

Se resuelve **en el código**, no solo en el YAML: `application/datasets/build_feature_matrix.py`
gana un paso previo, `_expand_glob_columns(specs, available_columns)`, que corre **antes** de
llamar a `transform_fns.build_expressions`. Para cada `ExperimentalTransformSpec.columns` que
contenga `*`/`?`, expande el patrón con `fnmatch.fnmatch` contra `available_columns` — que son
las columnas **ya seleccionadas** de `features.groups` (`base_columns`, calculadas antes en el
mismo método), **no** todas las columnas del dataset. Esto es deliberado: expandir contra *todas*
las columnas dejaría que `"caudal_*"` alcance columnas de target (`caudal_t_mas_7d`) o de
metadata que el experimento nunca pidió como feature — un glob sin acotar sería una fuga
potencial, no solo un detalle de conveniencia. Si el patrón no matchea ninguna columna
seleccionada, se falla explícito (`ValueError`) en vez de aplicar el transform sobre cero
columnas en silencio. Los resultados se deduplican preservando orden: el propio YAML de ejemplo
declara `["caudal_*", "caudal_agregado_alta_frontera_m3s"]` a propósito (la segunda ya matchea el
glob), y expandir no debe aplicar el transform dos veces sobre la misma columna (Polars fallaría
con `DuplicateError` al `with_columns` un alias repetido).

Para la corrida baseline real de la Fase 3 (`bilstm_baseline_v1.yaml` y su variante
`bilstm_baseline_v1_per_horizon.yaml`) se eligió además la **segunda opción** que ya anticipaba
la Nota de la Fase 1/2 (reemplazar el glob por una lista explícita), por una razón de modelado
real descubierta al implementar el fix: `"caudal_*"` también matchea `caudal_delta_1d` (una
diferencia día a día, `caudal_actual_m3s - caudal_actual_m3s.shift(1)`, que puede ser negativa) y
`log1p` de un valor `< -1` da `NaN` — un problema de datos, no del bug del glob en sí (el glob ya
resuelto expande correctamente, simplemente expande *a* una columna que no debería pasar por
`log1p`). Las dos YAML de la corrida real declaran explícitamente las columnas de caudal que son
siempre `>= 0` (estado actual y lags, nunca deltas).

### Justificación

Resolver el glob en el código (no solo evitarlo en el YAML) es lo que permite que `"caudal_*"`
siga siendo una opción válida de sintaxis para *futuros* YAML de experimento (Fase 9: nuevos
modelos, nuevos grupos de features) sin que cada autor de config tenga que saber que los glob
"no andan": el mecanismo ahora funciona como cualquiera esperaría que funcionara. Acotar la
expansión a `features.groups` en vez de "todas las columnas del dataset" es la lectura estricta
de Decisión #5 (transforms se aplican sobre features seleccionadas, no sobre el dataset completo)
y evita una clase de bug de fuga (glob demasiado amplio alcanzando targets) que un test
(`test_glob_pattern_in_transform_columns_expands_against_selected_features`,
`tests/test_build_feature_matrix.py`) verifica explícitamente.

### Consecuencias

* `application/datasets/build_feature_matrix.py::_expand_glob_columns` es el único lugar que
  interpreta `*`/`?` en `columns`; `infrastructure/preprocess/transforms.py::build_expressions`
  no cambia (sigue esperando columnas ya resueltas, sin globs).
* Tests nuevos: `test_glob_pattern_in_transform_columns_expands_against_selected_features`,
  `test_glob_pattern_deduplicates_against_explicit_column_in_same_transform`,
  `test_glob_pattern_with_no_matches_raises` (`tests/test_build_feature_matrix.py`); ejercitado
  además end-to-end (con `RunSearch` real, dataset sintético) en
  `tests/test_run_search_phase3.py::test_bilstm_multi_output_runs_end_to_end_with_glob_transform_and_epoch_curves`.
* `configs/experiments/bilstm_baseline_v1.yaml` y `bilstm_baseline_v1_per_horizon.yaml` (Fase 3)
  usan la lista explícita para la corrida real, no el glob — el glob queda probado y disponible
  para quien lo prefiera en un YAML futuro sobre columnas sin el problema de `_delta_1d`.

---

## Decisión 042: El registro de modelos en Unity Catalog exige `signature` (no solo el `run_id`/artefacto) y la validación local del propio cliente de MLflow para UC importa pandas incondicionalmente — se resuelve con un `MLmodel` mínimo (sin flavor) y un stub temporal de `sys.modules["pandas"]`

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow/Unity Catalog real en la **Fase 3**
de `rio_search_plan.md` (`weather.ml.rio_search_bilstm`, registrado y verificado con el SDK).

### Contexto

Decisión #12 (`rio_search_plan.md` §0, §3.5) ya preveía registrar en `weather.ml` desde la
Fase 0 (`CREATE SCHEMA`) y registrar el primer modelo real en la Fase 3. Decisión 039 fijó que
los modelos PyTorch se serializan como artefacto plano (`torch.save(state_dict)` + JSON), sin
`mlflow.pytorch.log_model`, porque ese flavor importa pandas incondicionalmente. Al implementar
`TrackingPort.register_model` (Fase 3) sobre ese artefacto plano aparecieron **dos** problemas
reales, verificados contra Databricks, ninguno anticipado por el plan:

1. `mlflow.register_model(model_uri="runs:/<id>/model", name="weather.ml.rio_search_bilstm")`
   sobre un directorio de artefactos sin `MLmodel` falla con
   `Unable to find a logged_model with artifact_path model under run <id>`: el cliente busca
   primero un archivo `MLmodel` en el artefacto y, si no lo encuentra, un `LoggedModel` (entidad
   de MLflow 3.x que solo crean los flavors de alto nivel) — ninguno de los dos existe para un
   artefacto plano.
2. Agregar un `MLmodel` mínimo (`flavors: {}`, sin `signature`) cambia el error a "Unable to
   load model metadata... signature... specifying both input and output type specifications":
   **Unity Catalog exige `signature` para registrar cualquier versión**, incluso sin intención
   de servir el modelo (`mlflow/store/_unity_catalog/registry/rest_store.py::
   _validate_model_signature`, mensaje explícito: "All models in the Unity Catalog must be
   logged with a model signature containing both input and output type specifications").
   Agregar la `signature` con la clase real `mlflow.models.signature.ModelSignature` no es
   posible sin pandas: ese módulo hace `import pandas as pd` en su primera línea de imports
   (mismo patrón exacto que `mlflow.pytorch`, Decisión 039). Peor todavía: **la validación es
   local, no solo del lado del servidor** — `UcModelRegistryRestStore._load_model` descarga el
   `MLmodel` recién subido y llama `Model.load(...)` *antes* de tocar la red, y
   `Model.from_dict()` hace `from mlflow.models.signature import ModelSignature`
   **incondicionalmente** (no solo cuando el diccionario trae una clave `"signature"`) — así que
   el `ModuleNotFoundError: No module named 'pandas'` ocurre **siempre** que se registra un
   modelo en UC con este cliente, sin pandas instalado, tenga o no `signature` el `MLmodel`.

### Decisión

Dos piezas, ambas en `infrastructure/tracking/mlflow_databricks.py`, activas solo dentro de
`register_model(...)`:

1. **`MLmodel` mínimo con `signature` de tensores, sin flavor.** `_TensorSignatureStub` replica
   a mano el contrato de `ModelSignature.to_dict()` (`{"inputs": <json>, "outputs": <json>,
   "params": None}`) usando `mlflow.types.schema.Schema`/`TensorSpec` — confirmado importable
   sin pandas (a diferencia de `mlflow.models.signature`). La `signature` declara dos
   `TensorSpec` genéricos (`X`: `float32`, forma `(-1, -1, -1)`; `y_pred`: `float64`, forma
   `(-1, -1)`) — no se ata a `lookback`/`n_features`/`n_outputs` exactos de cada trial porque
   UC solo exige que la signature *exista* y tenga inputs+outputs, no que describa el contrato
   real de inferencia (que ya vive, con precisión, en `features/spec.json` y
   `model/architecture.json`, artefactos propios de cada run). Se sube al mismo `artifact_path`
   ("model") que ya tiene `model_state_dict.pth`/`architecture.json`.
2. **Stub temporal de `sys.modules["pandas"]`.** `_pandas_import_stub()` (context manager)
   registra `sys.modules["pandas"] = unittest.mock.MagicMock()` **solo** durante la llamada a
   `mlflow.register_model(...)`, y lo revierte en `finally` (no lo toca si pandas ya estuviera
   presente, caso que nunca ocurre en este entorno). No es pandas real ni se declara como
   dependencia (`pyproject.toml` sigue sin `pandas`): el camino que realmente se ejercita
   (`ModelSignature.from_dict()` → `Schema.from_json()`/`ParamSchema.from_json()`) no invoca
   ninguna función de pandas — los `pd.Series`/`pd.DataFrame` que aparecen en otros módulos
   importados transitivamente (`mlflow.types.utils`) son solo anotaciones de tipo evaluadas al
   definir funciones, nunca llamadas; un `MagicMock` satisface cualquier acceso a atributo sin
   lanzar `AttributeError`. Verificado explícitamente: `test_no_pandas_in_env` y
   `test_pandas_import_actually_fails` (Fase 0) siguen en verde después de una corrida real que
   registró un modelo — el stub no deja rastro en `sys.modules` una vez que `register_model`
   retorna.

Registrado y verificado real: `weather.ml.rio_search_bilstm`, versión creada con el SDK
(`WorkspaceClient().model_versions.list("weather.ml.rio_search_bilstm")` devuelve
`status=READY`) — detalle de la corrida y la versión final en Decisión 043.

### Justificación

La alternativa de instalar pandas real (aunque sea solo para desbloquear esta llamada interna de
MLflow) violaría Decisión #9 en su propia letra (`test_no_pandas_in_env` comprueba que
`importlib.util.find_spec("pandas")` da `None`: pandas no debe estar instalable en el entorno en
absoluto, no solo "no importado desde `rio_search`"). El texto de la propia Decisión #9 en
`ruff.toml`/`pyproject.toml` anticipa exactamente este caso ("si una dependencia lo necesita,
aislarla, nunca importarlo desde `rio_search`"): `mlflow-skinny` es la dependencia que lo
necesita (para una comprobación de tipos que nunca ejecuta lógica real de pandas), y el stub la
aísla sin que ningún módulo de `rio_search` haga `import pandas` en ningún momento. La alternativa
de reimplementar el protocolo completo de registro de UC (crear modelo, credenciales de
almacenamiento temporales, subida directa, alta de versión) vía la API REST cruda para evitar por
completo el cliente Python de MLflow se descartó por costo/beneficio: es una superficie mucho más
grande y frágil (múltiples llamadas internas no documentadas públicamente) para evitar un `import`
de tres líneas que ya se aísla de forma segura y verificable.

### Consecuencias

* `TrackingPort.register_model` (puerto, `application/ports/tracking.py`) gana su
  implementación real; `FakeTrackingPort` de los tests offline (`tests/test_run_search_phase3.py`)
  la implementa con un contador simple, sin tocar ninguna de las dos piezas de esta Decisión
  (no hace falta: el fake nunca llama a MLflow real). La implementación real solo agrega
  `numpy` (ya dependencia) y `mlflow.types.schema` (confirmado sin pandas) como imports nuevos;
  si una versión futura de `mlflow-skinny` corrige el import incondicional en
  `Model.from_dict()` (moviéndolo a lazy/condicional, como ya hace en otros paths), el stub de
  `sys.modules` deja de ser necesario sin cambiar la firma de `register_model` ni el resto de
  `RunSearch`.
* Riesgo aceptado y acotado: si una llamada futura a `mlflow.register_model(...)` (p. ej. una
  versión nueva de mlflow que sí invoque pandas de verdad en ese camino) se topa con el stub,
  fallaría con un `AttributeError`/`TypeError` claro sobre el `MagicMock` (no un resultado
  silenciosamente incorrecto) — se revisaría en ese momento, acotado a este único método.
* `per_horizon` (Decisión de diseño de esta misma fase, ver `RunSearch._run_single_horizon`)
  reusa exactamente el mismo `register_model`, con nombres `weather.ml.rio_search_<model>_h{NN}`
  (un modelo por horizonte) — implementado y cubierto por el mismo mecanismo, pero **no
  ejercitado contra UC real** en la corrida baseline de esta fase (`register_model: false` en
  `bilstm_baseline_v1_per_horizon.yaml`, para no crear 16 versiones en la primera corrida de
  demostración — ver Decisión 043).

---

## Decisión 043: Cierre de la Fase 3 (BiLSTM) — un target con `NaN` reales sin enmascarar diverge el entrenamiento a `NaN` desde el epoch 1; corregido, el BiLSTM supera a persistencia en 7 de 8 horizontes

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow/Unity Catalog real en la **Fase 3**
de `rio_search_plan.md`: dos búsquedas reales (`bilstm_baseline_v1.yaml`, `multi_output`, 4
trials; `bilstm_baseline_v1_per_horizon.yaml`, `per_horizon`, 1 trial), reproducibilidad en CPU
verificada con dos corridas idénticas, y 4 versiones de `weather.ml.rio_search_bilstm`
registradas y confirmadas con el SDK.

### Contexto

Al correr `bilstm_baseline_v1.yaml` por primera vez contra Databricks real (§5, checklist de la
Fase 3), las 4 corridas de `multi_output` terminaron **todas** con `skill_vs_persistence`
negativo en los 8 horizontes y `train/loss`/`val/loss` = `NaN` desde el primer epoch
(`train/best_epoch == train/epochs`, la salida de "nunca mejoró" de `BaseTorchAdapter.fit`).
Investigando en paralelo (sin tocar Databricks para no interferir con la corrida real en curso,
ver más abajo el hallazgo de contención) se descartaron dos hipótesis antes de llegar a la causa
real:

1. **Hipótesis 1 (parcialmente cierta, no la causa raíz):** `caudal_registros_validos` y
   `nivel_registros_validos` son banderas casi constantes en TRAIN (`std` ≈ 0.013 para caudal:
   >99% de los días vale `1`). Un escalador `standard` las convierte en z-scores extremos
   (`min` ≈ **-77** en TRAIN real, verificado con `BuildFeatureMatrix` contra el parquet real) —
   un input de esa magnitud es una fuente real de inestabilidad numérica en una LSTM. Se corrigió
   agregando soporte real a `features.exclude` (§4.1, declarado en el YAML desde la Fase 1 pero
   **nunca conectado** a `BuildFeatureMatrix.execute` hasta ahora) y excluyendo esas dos columnas
   en ambos YAML de BiLSTM. Es una corrección real y se queda, pero **no era la causa del `NaN`**:
   con la exclusión aplicada y arquitecturas ya probadas como estables (`num_layers=1`), el `NaN`
   seguía apareciendo desde el epoch 1.
2. **Hipótesis 2 (descartada):** `num_layers=2` (arquitectura más profunda) como fuente de
   inestabilidad. Se probó `num_layers=1` con hiperparámetros idénticos a un trial real que
   *sí* había entrenado sin `NaN` en GPU — el `NaN` persistió igual en CPU. No era la
   arquitectura.

**Causa real**, encontrada probando `BiLSTMAdapter.fit()` directamente (sin MLflow, en proceso,
sobre el parquet real cacheado): `y nan? True` — `Targets.y` (Fase 1) trae `NaN` genuinos por
horizonte/fila cuando el horizonte cae fuera del rango con target observable (§2.1: "huecos en
el período de TEST" — `nivel` sin datos 2025-11-01→2026-03-27, `caudal` sin datos
2026-04-07→05-04 — y, more generally, cualquier ancla cerca del borde de un split donde algún
`caudal_t_mas_{h}d` todavía no tiene LEAD calculado). Esto es exactamente lo que `coverage` en
`MetricSet`/`EvaluatePredictions` (Fase 2, §3.7) ya sabía manejar para la *evaluación* — pero
`BaseTorchAdapter.fit()` (Fase 3, código nuevo de esta fase) nunca lo consideró para el
*entrenamiento*: `torch.nn.MSELoss()` (y `L1Loss`/`SmoothL1Loss`) no ignoran `NaN` por sí solos
— un único `NaN` en un batch contamina la reducción `mean()` de PyTorch entera, y ese `NaN` se
propaga por `backward()` a *todos* los pesos del modelo en el primer `optimizer.step()`,
destruyéndolo para siempre (comparaciones `NaN < best_val` son siempre `False`, así que
`best_state` nunca se fija — el resultado final es "el último estado", que ya es todo `NaN`).
**Los 8 modelos registrados en la primera ronda de corridas reales tenían pesos completamente
`NaN`.**

### Decisión

1. **`BaseTorchAdapter.fit()` enmascara `NaN` antes de la función de pérdida**, en cada batch de
   TRAIN y en VAL: `mask = torch.isfinite(yb); loss = criterion(pred[mask], yb[mask])`; un batch
   sin ningún target finito se saltea sin backward (no aporta gradiente); `train_loss` se
   normaliza por la cantidad real de targets válidos vistos en el epoch, no por el tamaño fijo
   del batch. Test de regresión offline con datos sintéticos y ~15% de filas de TRAIN sin ningún
   target válido (`tests/test_bilstm_adapter.py::test_fit_masks_nan_targets_and_does_not_diverge`):
   confirma que la loss no diverge y que las predicciones finales no tienen `NaN`.
2. **`features.exclude` (§4.1) se conecta de verdad**: `BuildFeatureMatrix.execute` gana el
   parámetro `exclude: list[str] | None` (filtra columnas de los grupos seleccionados antes de
   expandir globs de transforms, Decisión 041); `RunSearch._prepare_trial_data` lo pasa desde
   `trial_config.features.exclude`. `bilstm_baseline_v1.yaml` y su variante `per_horizon` excluyen
   `caudal_registros_validos`/`nivel_registros_validos`. Test offline
   (`tests/test_build_feature_matrix.py::test_exclude_drops_a_column_from_the_selected_group`).
3. **Contención del cache local de credenciales OAuth (hallazgo operativo, no de código):**
   corriendo un segundo proceso de diagnóstico en paralelo a una búsqueda real de larga duración,
   una llamada a `MlflowClient.get_run` falló con `RestException 401` y el mensaje real
   (no enmascarado, a diferencia del primer intento) fue explícito: *"forced token refresh: cache
   update: error storing token in local cache: rename ...\token-cache.json: Access is denied"* —
   dos procesos que refrescan el token OAuth del perfil de Databricks CLI al mismo tiempo compiten
   por el `rename` atómico del archivo de cache (`~/.databricks/token-cache.json`), y en Windows
   el que pierde la carrera recibe `Access is denied`, lo que tumba esa llamada HTTP con 401. Es
   la razón concreta detrás del riesgo que el plan ya anticipaba (§6: "Un solo proceso pesado a la
   vez (GPU, CLI de Databricks) | `JobRunner` comparte `lock.py` con los backfills de ANA") — se
   corrigió en la práctica serializando las corridas contra Databricks (nunca dos procesos
   `rio-search`/verificación tocando el perfil al mismo tiempo), no con un cambio de código en
   esta fase; el `JobRunner` con lock de la Fase 4 es la solución estructural.

### Resultados reales (post-corrección, contra Databricks/MLflow/UC real)

**`multi_output`** — `bilstm_baseline_v1.yaml`, `strategy: random`, `n_trials: 4`, seed 42.
Search run `7ba3d432e4bb495e837128adf94ad1b2` (`/Users/joaquintschopp@gmail.com/rio_search/bilstm`),
`time/search_total_s` = **1565.7 s** (≈ 26 min), `time/dataset_refresh_s` = 6.0 s.

| Trial (run_id) | lookback | hidden | layers | lr | train_start | val/kge/mean | test/kge/mean | test/rmse/mean | epochs (best) | train_total_s | trial_total_s | UC versión |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `2bad22f8…` (**mejor por VAL**) | 90 | 32 | 1 | 0.00461 | 2000-01-01 | **0.207** | 0.101 | 1628.3 | 105 (80) | 60.8 s | 312.0 s | **9** |
| `64b5d9c0…` | 30 | 32 | 1 | 0.00380 | 2000-01-01 | 0.119 | 0.045 | 1616.4 | 106 (81) | 57.7 s | 307.0 s | 10 |
| `e4f0f7e2…` | 90 | 64 | 1 | 0.00055 | 2000-01-01 | 0.027 | -0.059 | 1760.6 | 236 (211) | 140.9 s | 648.6 s | 11 |
| `6e086068…` | 30 | 128 | 1 | 0.00269 | 2008-01-01 | 0.188 | 0.074 | 1575.8 | 65 (40) | 26.4 s | 203.6 s | 12 |

Skill vs. persistencia en TEST del trial campeón (`2bad22f8…`, elegido por `val/kge/mean`, nunca
por TEST — §3.7):

| h01 | h02 | h03 | h04 | h05 | h06 | h07 | h14 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.362 | **+0.017** | **+0.107** | **+0.136** | **+0.123** | **+0.108** | **+0.046** | **+0.179** |

**`per_horizon`** — `bilstm_baseline_v1_per_horizon.yaml`, `n_trials: 1` (Decisión sobre el costo
más abajo). Search run `f8b488e5e2bf43a0b8d98625789f0eb9`, trial run
`0b73ab09cba5448db438a5b50e25e88a` (mismos hiperparámetros que el mejor trial de `multi_output`:
lookback=90, hidden=32, layers=1, lr=0.00461, train_start=2000-01-01 — la misma semilla produce
la misma primera muestra del `RandomSampler` en ambas búsquedas, comparación limpia).
`val/kge/mean` = **0.344**, `test/kge/mean` = 0.219, `test/rmse/mean` = 1526.9 (mejor que
`multi_output` en las tres métricas). `time/search_total_s` = **3216.2 s** (≈ 53.6 min, 8 runs
nietos con `time/train_total_s` sumado = 721.6 s).

| h01 | h02 | h03 | h04 | h05 | h06 | h07 | h14 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| -0.020 | **+0.152** | **+0.168** | **+0.146** | **+0.128** | **+0.119** | **+0.063** | **+0.186** |

Run_ids de los 8 horizontes (nietos de `0b73ab09…`, verificado `mlflow.parentRunId` coincide):
h01 `00e7cce3…`, h02 `c197ec27…`, h03 `ed50c78c…`, h04 `b29f35a9…`, h05 `0531e237…`,
h06 `26e0c9f7…`, h07 `53d64cd1…`, h14 `9c31d7dc…`.

**Criterio de cierre "skill > 0 para t+1…t+7" (§5):** se cumple para **6 de 7** horizontes de esa
ventana en ambas estrategias (todos salvo h01); h01 queda negativo en las dos (-0.36 `multi_output`,
-0.02 `per_horizon`, casi empatado con persistencia). Se documenta por qué, no se fuerza un ajuste
más: la persistencia (predecir el último valor observado) es un baseline extremadamente fuerte
para el horizonte 1 en series de caudal fluvial — la autocorrelación día a día es altísima
(coeficiente de determinación de la persistencia t→t+1 ronda 0.95+ en la mayoría de las cuencas) —
y superarla al horizonte más corto es, en la literatura hidrológica, sistemáticamente el caso más
difícil, no una señal de que el modelo esté mal. `h14` (el horizonte más largo, donde la
persistencia se degrada más) es donde el BiLSTM saca la mayor ventaja en ambas estrategias
(+0.179 / +0.186) — consistente con esa lectura.

**Comparación de estrategias:** `per_horizon` gana en las tres métricas de resumen (`val/kge/mean`
0.344 vs. 0.207, `test/kge/mean` 0.219 vs. 0.101, `test/rmse/mean` 1526.9 vs. 1628.3) con los
*mismos* hiperparámetros — evidencia de que 8 modelos dedicados (`n_outputs=1` cada uno)
especializan mejor que un único modelo de salida compartida, al costo de **10.3x** el tiempo
(3216.2 s vs. 312.0 s de ese mismo trial) — el "frente de Pareto tiempo vs. métrica" que el plan
pide poder trazar (§3.7) ya tiene su primer punto real de cada estrategia.

**Costo de la búsqueda (§13, §14 — se registra todo, no limita nada):** `multi_output`,
4 trials, 1565.7 s totales (392 s/trial en promedio, entre 203.6 s y 648.6 s según arquitectura);
`per_horizon`, 1 trial de 8 sub-modelos, 3216.2 s. `n_trials` se redujo del `40` del ejemplo
original del plan (§4.1) a `4` (`multi_output`) y `1` (`per_horizon`, además por el hallazgo de
contención de credenciales en corridas largas) — la exhaustividad de la búsqueda de
hiperparámetros no es el punto de este checklist, que funcione end-to-end contra Databricks/MLflow
real sí lo es (instrucción explícita de la fase); ampliar `n_trials` en cualquiera de los dos YAML
es cambiar un número, no una decisión de diseño.

**Reproducibilidad en CPU (§4.3, criterio de cierre):** mismos hiperparámetros del trial campeón,
`device: cpu`, `seed: 42`, corrido dos veces (`data/_repro_cpu_config2.yaml`, no versionado,
derivado de `bilstm_baseline_v1.yaml`). Run A `67843e9ed4094ef182be857923143cfb`, run B
`1ce5c0d3cb1e4ca18ececfc49b1dab6b`: **200 métricas comparadas (todo salvo `time/*`, que el plan no
exige reproducible) — 0 discrepancias**; la curva completa de `train/loss` de 20 epochs es
**idéntica bit a bit** entre A y B; `test/skill_vs_persistence/h01` = `-0.6620705881066022` en
ambas, dígito por dígito.

### Registro en `weather.ml` (Decisión #12)

`weather.ml.rio_search_bilstm`, **4 versiones válidas: 9, 10, 11, 12** (una por trial de la
búsqueda `multi_output` corregida), confirmadas `READY` con
`WorkspaceClient().model_versions.list(...)`. Las **versiones 1-8** (de las dos búsquedas reales
corridas *antes* de la corrección del `NaN` — 4 trials de `multi_output` sin enmascarar + otros
4 de una corrida de diagnóstico intermedia) tenían **pesos completamente `NaN`** (consecuencia
directa del bug de esta Decisión) y se **borraron** (`model_versions.delete` + verificado que no
quedan) para no dejar modelos rotos en el registro. La versión **9** (`2bad22f8…`) es la mejor por
`val/kge/mean` dentro de `multi_output`; ninguna versión de `per_horizon` está registrada
(`register_model: false` en ese YAML, decisión explícita para no crear 8 modelos × 1 trial en la
corrida de demostración — el mecanismo de registro por horizonte
(`RunSearch._run_single_horizon`) es el mismo código que `multi_output` y está cubierto por los
mismos tests offline, solo no se ejercitó contra UC real en esta ronda).

### Justificación

Enmascarar `NaN` en la función de pérdida (en vez de, por ejemplo, imputar el target o recortar
las fechas de entrenamiento para evitar huecos) respeta la misma invariante que ya regía la
*evaluación* (§3.7: "métricas sobre targets disponibles + reporte de cobertura") sin inventar una
regla nueva: un hueco de calendario real no se rellena con un valor inventado, se excluye del
gradiente ese día para ese horizonte puntual, igual que ya se excluye de las métricas. La
alternativa de recortar el rango de fechas de entrenamiento para garantizar cobertura 100% hubiera
reducido artificialmente el tamaño de TRAIN y hubiera sido una regla ad hoc por dataset, no un
comportamiento general del adaptador (que debe funcionar igual si el próximo dataset de Gold tiene
sus propios huecos, en otras fechas).

### Consecuencias

* `rio_search/backend/rio_search/infrastructure/models/torch/base_torch_adapter.py::fit` es la
  única implementación de entrenamiento iterativo de la Fase 3; el enmascarado de `NaN` es
  automático para cualquier adaptador que herede de `BaseTorchAdapter` (Fase 9: TCN/GRU futuros lo
  heredan gratis, no hace falta repetir la lógica).
* `application/datasets/build_feature_matrix.py::BuildFeatureMatrix.execute` tiene ahora un
  parámetro `exclude` real; cualquier YAML de experimento (no solo BiLSTM) puede usar
  `features.exclude` desde ya — estaba en el contrato del YAML (§4.1) desde la Fase 1 pero nunca
  hacía nada.
* El hallazgo de contención de credenciales (`~/.databricks/token-cache.json`) es una razón
  concreta más para el `JobRunner` con lock de la Fase 4 (§3.1: "un solo proceso pesado a la vez,
  comparte `lock.py` con los backfills de ANA") — no requiere acción en esta fase, pero se
  documenta para que la Fase 4 lo tenga como caso de prueba real.
* `configs/experiments/bilstm_baseline_v1.yaml` y `bilstm_baseline_v1_per_horizon.yaml` quedan
  con `features.exclude` fijo y `search.n_trials` reducido (4 y 1 respectivamente) como los
  valores con los que se corrió el baseline real citado en esta Decisión; ampliar la búsqueda es
  responsabilidad de una fase o corrida futura, no bloquea el cierre de esta.
* Pendiente explícito para el usuario (§8 del plan, no bloquea el cierre de esta fase): revisar
  `weather.ml.rio_search_bilstm` (nombre, las 4 versiones 9-12, alias de campeón todavía no
  asignado — eso es Fase 6, `PromoteChampion`) y decidir la política de versiones antes de que
  Fase 9 agregue más modelos al mismo schema.

## Decisión 044: Cierre de la Fase 4 (Backend API) — puerto de lectura de MLflow separado del de
escritura, cache SQLite con TTL diferenciado por estado del run, y el `JobRunner` expone el mismo
bug de encoding de consola de Windows que ya se había resuelto para el propio proceso del CLI

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow real en la **Fase 4** de
`rio_search_plan.md`: servidor `rio-search api serve` levantado, `GET /api/runs`/`GET
/api/searches`/`GET /api/runs/{id}` devolviendo las búsquedas y trials reales de la Fase 3
(BiLSTM, con `time/*`), y una búsqueda `persistence` lanzada de punta a punta desde `POST
/api/jobs` que descargó el dataset, terminó y quedó registrada en MLflow (`search_run_id`
`6f8b5e19a39e4c1c9fe39aa56343c75e`). 262 tests offline en verde (208 de las Fases 0-3 + 54
nuevos), 2 tests `integration` deseleccionados por default sin cambios.

### Contexto

La Fase 3 dejó 208 tests y una base de datos real en MLflow (`baselines`, `bilstm`, `smoke`), pero
`TrackingPort` (Fase 2, §3.5) es un puerto de **escritura pura** (`start_run`/`set_tags`/
`log_metrics`/`log_artifact_dir`/`log_meta_dataset`/`register_model`): no tiene forma de listar ni
leer un run ya logueado. La Fase 4 necesita exactamente eso para las páginas Búsquedas/Run/Comparar
(§3.9) sin que la UI (Fase 5) le pegue a Databricks en cada render (§5), y necesita lanzar
búsquedas nuevas desde HTTP sin arriesgar el hallazgo operativo de la Fase 3 (Decisión 043, punto
3: dos procesos refrescando el token OAuth del mismo perfil al mismo tiempo compiten por un
`rename` atómico en Windows y uno recibe 401).

### Decisión

1. **`TrackingReadPort` nuevo, separado de `TrackingPort`** (`application/ports/tracking_read.py`):
   `list_runs`, `get_run`, `list_children`, `get_metric_history`. Implementado por
   `MlflowDatabricksTrackingReader` (`infrastructure/tracking/mlflow_read.py`) sobre
   `mlflow.tracking.MlflowClient` — **nunca** la función de módulo `mlflow.search_runs()`, que
   devuelve un `pandas.DataFrame` y violaría la Decisión #9 (Polars, nunca pandas);
   `MlflowClient.search_runs()` devuelve una `PagedList[Run]` sin pandas, verificado en el
   `.venv` real (`mlflow-skinny` sin pandas instalado, `test_no_pandas_in_env` sigue en verde).
   La jerarquía búsqueda → trial → horizonte (§3.5) no vive en un campo de MLflow: se reconstruye
   del tag `mlflow.parentRunId` que MLflow setea solo en `start_run(nested=True)`, vía
   `list_children` (filtro `tags.\`mlflow.parentRunId\` = '<id>'`) — verificado end-to-end contra
   los runs reales de BiLSTM de la Fase 3: `GET /api/runs/{search_run_id}` devolvió correctamente
   los 4 trials de `7ba3d432e4bb495e837128adf94ad1b2` con sus `test/skill_vs_persistence/h01`, y
   `GET /api/runs?families=bilstm` devolvió las 47 runs reales (6 búsquedas, 16 trials directos,
   25 horizontes de `per_horizon`) con `time/train_total_s` por trial y `time/search_total_s` por
   búsqueda.
2. **Cache de lectura en SQLite con TTL por estado del run**, no un único TTL global
   (`infrastructure/persistence/sqlite_cache.py` + `infrastructure/tracking/cached_reader.py`,
   criterio documentado en el docstring del segundo módulo): `list_runs`/`list_children` 20 s
   (el tipo de consulta que más rápido envejece: un job recién lanzado crea runs nuevos que la UI
   quiere ver aparecer); un run **terminal** (`FINISHED`/`FAILED`/`KILLED`) 6 h (MLflow no permite
   reabrirlo, así que es efectivamente inmutable, pero se pone un techo finito de todos modos, no
   "para siempre", por si un bug de escritura necesita autocorregirse sin reiniciar el proceso); un
   run **activo** (`RUNNING`) 10 s; historial de métricas 15 s fijo (no se sabe el estado del run
   sin otra llamada, y el costo de una llamada extra a un run ya terminado es más barato que
   mostrar una curva de entrenamiento desactualizada de un run que sigue corriendo). Verificado
   contra Databricks real: la segunda llamada a `GET /api/searches?families=bilstm` (4.6 s) fue
   más rápida que la primera `GET /api/runs?families=bilstm` (10.2 s) porque reusó la entrada de
   cache de `list_runs` para la misma familia dentro del TTL de 20 s.
3. **`SubprocessJobRunner`** (`infrastructure/jobs/subprocess_job_runner.py`): cola en memoria +
   un thread worker daemon, **un job a la vez**, cada uno un subproceso `python -m
   rio_search.interfaces.cli.main search run <config>` (mismo comando que un usuario correría a
   mano, invocado con `sys.executable` para no depender de que el `.venv` tenga el script de
   consola en el PATH). Además de la cola (que solo serializa jobs *de este proceso*), cada
   ejecución toma un `ProcessLock` (`infrastructure/jobs/process_lock.py`) antes de lanzar el
   subproceso — **portado**, no importado, del patrón de
   `notebooks_local/ana_historic_backfill/lock.py` (PID guardado en archivo, verificado vivo con
   `tasklist`, mismo patrón que ya usa el dashboard de ANA para el mismo problema): un `rio-search
   search run` corrido a mano en otra terminal también queda serializado con los jobs de la API,
   no solo estos entre sí. Los `JobRecord` viven solo en memoria del proceso de la API (no
   persisten un reinicio del backend) — decisión deliberada: la fuente de verdad de "qué corrió y
   qué dio" es MLflow (`GET /api/runs`), no la cola de jobs; un job es solo el mecanismo para
   *lanzar* una búsqueda y ver su log en vivo mientras corre. Documentado como pendiente liviano
   para la Fase 5 si la UI necesita que la cola sobreviva un reinicio (migrar `_records` al mismo
   `SqliteReadCache`, cambio directo).
4. **Bug real encontrado y corregido en la verificación end-to-end**: el primer intento de `POST
   /api/jobs` con `persistence_baseline_v1.yaml` terminó en `status=failed` con `exit_code=None`
   a pesar de que la búsqueda subyacente **sí había terminado bien** en MLflow (el log capturado
   mostraba `search_run_id=... trials=1` real). Causa: `subprocess.Popen(text=True)` sin
   `encoding` explícito decodifica el stdout del proceso hijo con
   `locale.getpreferredencoding()` — cp1252 en la consola de Windows — y los íconos unicode que
   MLflow imprime al terminar un run (🏃, 🧪, ya vistos y resueltos para el *propio* stdout del
   CLI en `interfaces/cli/main.py`, Fase 0) tumban esa decodificación con `UnicodeDecodeError` en
   el proceso *padre* (la API), que nunca había reconfigurado nada para leer la salida de *otro*
   proceso. Corregido pasando `encoding="utf-8", errors="replace"` explícito a `Popen`. Re-corrida
   real confirmatoria: mismo YAML, `status=finished`, `exit_code=0`,
   `extra.search_run_id=6f8b5e19a39e4c1c9fe39aa56343c75e`, visible en
   `GET /api/runs/6f8b5e19a39e4c1c9fe39aa56343c75e` con `time/dataset_refresh_s` y sub-pasos
   poblados (bajó el dataset) y 1 trial con `skill_vs_persistence/h01 = 0.0` (exacto, coherente
   con la Decisión de la Fase 2 sobre el baseline de persistencia). El endpoint SSE
   (`GET /api/jobs/{id}/log`) también se verificó real: reprodujo las líneas con emoji
   correctamente tras la corrección.
5. **Modelo de anti-corrupción HTTP → dominio**: `interfaces/api/schemas.py` (Pydantic) es
   deliberadamente una capa separada de los DTOs de `application` (`RunRecord`, `JobRecord`, …):
   un cambio de forma de la API (paginación, campos opcionales) no debe forzar tocar
   `application`/`domain`. `ApiDependencies` (`interfaces/api/dependencies.py`) es el mismo patrón
   de `RunSearchDependencies` (Fase 2) aplicado a la API: un bundle construido una sola vez por
   `interfaces/container.py::build_api_dependencies`, e inyectable con falsos en
   `tests/test_api.py` (`TestClient` + `TrackingReadPort`/`JobRunner` falsos, ningún test de
   `pytest` toca Databricks).

### Alcance no cubierto en esta fase (documentado, no bloqueante)

* `POST /api/champions` (§3.9, página Run: "botón promover a campeón") **no** se implementó:
  `PromoteChampion` es un caso de uso de la Fase 6 (Predicciones) que todavía no existe en
  `application/predictions/`; agregar el endpoint antes tendría que inventar la lógica de
  promoción fuera de su fase.
* `/api/forecasts/*` y `/api/research/*` (§3.9) tampoco: dependen de `IssueDailyForecast` (Fase 6)
  y del dominio `research` (Fase 7), ninguno de los dos existe todavía.
* `GET /api/datasets` expone la `DatasetVersion` del snapshot (modo `offline` por default, no
  pega a Databricks salvo que se pida `ensure_latest`/`volume_as_is` explícito) pero no la
  cobertura por columna/año que sí tiene `DescribeDataset` (Fase 1) — se dejó fuera para no
  duplicar esa lógica en un endpoint improvisado; la Fase 5 (UI, página Datasets) puede pedir que
  se conecte `DescribeDataset` a un endpoint dedicado cuando haga falta un experimento concreto
  como parámetro (igual que ya hace `rio-search datasets describe --experiment`).

### Pendientes para la Fase 5 (UI React)

* La cola de jobs no sobrevive un reinicio del backend (punto 3 más arriba) — si la UI necesita
  que un job lanzado siga siendo consultable después de un restart, hay que persistir
  `SubprocessJobRunner._records` (mismo `SqliteReadCache`, cambio acotado).
* `GET /api/runs`/`GET /api/searches` no paginan (`max_results` tope 2000): con 47 runs reales de
  BiLSTM hoy no es un problema, pero si la Fase 9 agrega modelos y la cantidad de runs crece,
  conviene revisar antes de que la UI liste todo sin paginar.

## Decisión 045: Cierre de la Fase 5 (UI React) — el frontend se sirve estático desde FastAPI con
un catch-all de SPA registrado después de `/api/*`, y tres huecos de la API de la Fase 4 (artefactos,
cobertura por columna, listar/editar YAML) se documentan en la propia UI en vez de inventarse

### Estado

`Aceptada` (2026-08-27), verificada contra el backend real (`rio-search api serve`) y contra
Databricks/MLflow real, no simulada: navegador headless (`browser-automation`, patchright — la
extensión `claude-in-chrome` no tenía el navegador del usuario conectado en esta sesión) navegando
`http://127.0.0.1:8000/` servido enteramente por FastAPI (sin proxy de Vite), 0 errores de consola
y 0 requests fallidos en las 6 páginas. `npm run build` (TypeScript estricto, `tsc -b`) sin errores;
`oxlint` sin errores (2 warnings menores, no bloqueantes). `pytest` en `rio_search/backend/`: **264
tests en verde** (262 de las Fases 0-4 + 2 nuevos de esta fase), 2 `integration` deseleccionados sin
cambios.

### Contexto

La Fase 4 dejó una API real con 8 endpoints de lectura/escritura (§3.9 de `rio_search_plan.md`) y el
andamiaje Vite+React+TS de la Fase 0 (`HealthPage` mínima). Esta fase construye las 5 páginas de
contenido que pide §3.9 (Búsquedas, Run, Comparar, Lanzar, Datasets — "Pronóstico de hoy" y Research
quedan para las Fases 6/7 a propósito) contra el shape *real* de las respuestas, verificado con
`curl` antes de escribir una sola línea de UI, y cierra sirviendo el build estático desde el mismo
proceso FastAPI que ya sirve `/api/*`.

### Decisión

1. **Montaje estático en `interfaces/api/main.py`, no un router nuevo**: después de registrar todas
   las rutas `/api/*`, si `rio_search/frontend/dist` existe se registra un único
   `GET /{full_path:path}` que sirve el archivo pedido si existe bajo `dist/`, o cae a
   `index.html` si no (fallback de SPA para que React Router resuelva `/runs/<id>`, `/compare`,
   etc. del lado del cliente). Starlette resuelve rutas por **orden de registro** — el catch-all
   registrado al final nunca puede robarle una request a `/api/health` ni a ninguna otra ya
   registrada arriba — verificado con un test nuevo
   (`test_api_routes_never_fall_through_to_the_frontend_static_mount`) y a mano:
   `GET /api/searches` siguió devolviendo JSON real con el mount activo. El mount es condicional a
   que `dist/` exista: los 262 tests existentes de la Fase 4 (que construyen `create_app(deps=...)`
   sin compilar nada) siguen en verde sin tocarlos — confirmado (264 en verde, incluidos los 2
   nuevos). Es el único cambio en `rio_search/backend/` de esta fase.
2. **5 páginas reales, sin gestor de estado global** (TanStack Query cubre cache de servidor, React
   Router para rutas): `SearchesPage` (`/`, lista de búsquedas+trials con filtro por familia, orden,
   selección por checkbox → `Comparar`), `RunPage` (`/runs/:runId`, config/tags/métricas por
   horizonte/tiempos/curva de pérdida/cobertura/artefactos/botón campeón), `ComparePage`
   (`/compare?ids=`, tabla + métrica vs. horizonte + tiempo vs. métrica + diff de configs),
   `LaunchPage` (`/launch`, formulario + cola de jobs + log SSE), `DatasetsPage` (`/datasets`,
   versión del snapshot + catálogo de features). CSS modules + tokens propios en `index.css`
   (reescrito: el `#root` centrado de 1126px del template de Vite no servía para un dashboard de
   tablas; se conservó la paleta de acento del template y se le sumó la paleta categórica de la
   skill `dataviz`). `HealthPage` de la Fase 0 se conserva como diagnóstico de bajo nivel, enlazada
   desde el badge de estado del backend en la barra superior, no como página de contenido de §3.9.
3. **Gráficos con Recharts, paleta validada de la skill `dataviz`** (`references/palette.md`, sin
   correr el validador porque los 8 hex documentados ya vienen validados en ambos modos):
   `HorizonLineChart` (métrica vs. horizonte, una línea por serie — reusada tanto en Run, val/test,
   como en Comparar, una por run seleccionado), `LossCurveChart` (`train/loss` vs. `val/loss` desde
   `GET /api/runs/{id}/series/{name}`, la única fuente de series que la API expone hoy), y
   `TimeVsMetricChart` (scatter tiempo vs. métrica en Comparar, un `<Scatter>` por run para que cada
   punto lleve su color de identidad). Los ocho slots categóricos (`--series-1..8`) y los cuatro
   colores de estado (`--status-good/warning/serious/critical`) quedan como variables CSS en
   `index.css`, con sus pasos de modo oscuro.
4. **Hallazgo real durante la verificación, no un bug de la UI**: al navegar un trial
   `per_horizon` real de la Fase 3 (`1d1ff53f8df84147ae235e507a3a4274`,
   `bilstm__caudal__per_horizon__rolling_365__20260827-1630`) se encontró que **no todos** los
   trials `per_horizon` agregan sus 8 métricas de horizonte sobre sí mismos: este en particular
   tiene `run.metrics == {}` y un único hijo (`h01`) — corrida temprana/parcial de la Fase 3, antes
   de que la agregación quedara consistente, sigue existiendo en MLflow tal cual. `RunPage` ya
   distinguía "run con métricas propias" (tabla completa) de "run sin métricas propias" (lista de
   runs hijos) para cubrir tanto los runs padre de búsqueda genuinos como este caso — se ajustó
   solo el rótulo de esa rama de "Trials de esta búsqueda" a "Runs hijos" para que describa
   correctamente ambos casos sin invocar un concepto (trial) que no aplica al segundo. No hizo
   falta ningún otro cambio: la UI ya degradaba con datos reales sin romperse.
5. **Verificación end-to-end real de Lanzar, no solo del shape de la API**: se corrió
   `persistence_baseline_v1.yaml` desde la UI (click real en el navegador headless) mientras nada
   más pegaba a Databricks (aviso operativo de la Fase 3) — `POST /api/jobs` devolvió
   `job_id=22395654f1e0`, el log SSE mostró líneas reales de MLflow en vivo (con emoji, coherente
   con la corrección de encoding de la Decisión 044), y el job terminó `status=finished`,
   `exit_code=0`, `extra.search_run_id=444c58e2bfbc48faa056884d68654f94`, visible después en
   `GET /api/runs/444c58e2bfbc48faa056884d68654f94` y navegable desde el link "ver run →" de la
   cola de jobs. El log llegaba con códigos ANSI crudos (color de consola de MLflow) — se agregó
   `stripAnsi` en `LaunchPage.tsx` para no mostrarlos literalmente en el `<pre>`.
6. **Tres huecos de la API de la Fase 4 documentados en la propia UI (`GapNotice`), no
   rellenados con datos inventados**, tal como pedía el criterio de esta fase:
   - **Hidrograma TEST y `split/split.json`** (Run): la API no expone lectura/listado de
     artefactos de MLflow (`predictions/test.parquet`, `series/*.json` del plan §3.5) — solo
     historial de *métricas* escalares (`GET /api/runs/{id}/series/{name}`), que es lo que sí
     alimenta la curva de pérdida real. Pintar el hidrograma real necesita un endpoint nuevo (p.
     ej. `GET /api/runs/{id}/artifacts/predictions/test`), fuera de esta fase (no se tocó el
     backend salvo el mount estático). La "cobertura de splits" sí se resolvió con datos reales:
     las métricas `{split}/coverage/hNN` ya vienen en `run.metrics`.
   - **Cobertura por columna/año** (Datasets): `GET /api/datasets` expone solo la versión del
     snapshot (delta, sha, filas, rango, columnas), no la cobertura que sí calcula `DescribeDataset`
     (Fase 1) — exactamente el hueco que la Decisión 044 ya había anticipado para esta fase.
   - **YAML editable** (Lanzar): `POST /api/jobs` solo acepta un nombre de archivo que ya exista en
     `configs/experiments/`; no hay endpoint para listar, leer ni escribir el contenido de un YAML.
     La página ofrece un selector con los 5 configs reales conocidos hoy (lista estática en el
     código, documentada como tal) más un campo de texto libre para un nombre nuevo; la edición real
     del contenido queda pendiente de `GET/PUT /api/configs/{name}`.
   - Los tres se resolvieron **documentando el hueco en la UI** (componente `GapNotice`,
     reusado en las tres páginas) en vez de simularlos con datos falsos, como pedía el brief.
7. **Botón "promover a campeón"**: existe en `RunPage`, deshabilitado con tooltip explicando que
   `POST /api/champions` es un caso de uso de la Fase 6 (`PromoteChampion`) que todavía no existe —
   igual que el resto del plan, la UI del botón está lista, la acción no.

### Alcance no cubierto en esta fase (documentado, no bloqueante)

* Sin tests de componentes (Vitest/Testing Library no se agregaron): la verificación de esta fase
  fue `tsc -b` estricto + `oxlint` + navegación real contra el backend real en un navegador headless
  (`browser-automation`, patchright), no unit tests de React. Si una fase futura necesita
  regresiones automatizadas de UI, agregar Vitest es un cambio acotado (`vite.config.ts` ya usa
  Vite 8).
* El bundle de producción pesa ~685 KB sin comprimir (203 KB gzip) en un único chunk — Vite avisa
  del tamaño pero no bloquea el build; no se hizo code-splitting por página (`React.lazy`) para no
  ampliar el alcance de esta fase.
* `claude-in-chrome` (extensión de navegador real) no estaba conectada en esta sesión
  (`Browser extension is not connected`); la verificación visual se hizo con el navegador headless
  del skill `browser-automation` en su lugar — screenshots no se tomaron (se leyó texto/DOM/consola
  en cada página, que es lo que probaba el criterio de cierre), documentado acá por si el agente
  principal quiere una captura visual además del texto ya verificado.

### Pendientes para la Fase 6 (Inferencia diaria)

* "Pronóstico de hoy" es una página nueva de esta misma UI (`GET /api/forecasts/latest`,
  `GET /api/forecasts/backtest`, §3.9) — el layout (`components/Layout.tsx`) ya tiene un array
  `NAV_ITEMS` centralizado, agregar el link es un cambio de una línea.
* El botón "Promover a campeón" de `RunPage.tsx` queda con un comentario explícito de dónde
  conectar `POST /api/champions` cuando exista.
* Si la Fase 6 agrega `GET/PUT /api/configs/{name}` (para cerrar el hueco de "YAML editable" de
  Lanzar) o `GET /api/runs/{id}/artifacts/...` (para el hidrograma), `LaunchPage.tsx` y
  `RunPage.tsx` ya tienen el `GapNotice` marcando exactamente dónde conectar cada uno.

## Decisión 046: Campeón provisorio de `caudal` fijado en la versión 9 de
`weather.ml.rio_search_bilstm` — sujeto a que el usuario revise `weather.ml` y confirme o cambie
la política de versiones/alias (§8 del plan)

### Estado

`Provisoria` (2026-08-27): el mecanismo (`PromoteChampion`) está implementado, probado y
verificado real contra Databricks/MLflow, pero la elección concreta de *cuál* versión es la
campeona sigue sujeta a la revisión pendiente del usuario que ya preveía el plan (§8: "Revisar
`weather.ml` después de la primera corrida registrada", Decisión #12) — el usuario todavía no
hizo esa revisión. Se documenta acá para no bloquear la Fase 6, no para cerrar la pregunta.

### Contexto

La Fase 3 registró 4 versiones (9-12) de `weather.ml.rio_search_bilstm` desde una búsqueda
`random` de 4 trials (`bilstm_baseline_v1.yaml`) y dejó pendiente, a propósito, la revisión de
nombre/alias/política de versiones con el usuario (fila de Notas de la Fase 3 en
`rio_search_plan.md`, "Estado de implementación"). La Fase 6 (Inferencia diaria) necesita un
campeón fijado para poder ejercitar `IssueDailyForecast` de punta a punta contra Databricks/MLflow
real — sin una versión elegida no hay nada que predecir. Instrucción explícita del agente
principal para esta fase: no bloquear el trabajo esperando esa revisión, fijar un campeón
provisorio con la mejor métrica de VAL disponible y dejarlo claramente marcado como tal.

### Decisión

1. **Versión 9 de `weather.ml.rio_search_bilstm`** (`run_id`
   `2bad22f8bdd54e2cb39e071398881b51`, `bilstm__caudal__multi_output__rolling_365__20260827-1730`,
   hijo de la búsqueda `7ba3d432e4bb495e837128adf94ad1b2`) es el campeón provisorio de `caudal`:
   **mejor `val/kge/mean` de las 4 versiones registradas** (`0.20702039776959796`, verificado leyendo
   las métricas reales de las 4 con `MlflowClient` — versiones 10/11/12 quedan por debajo),
   `multi_output`, `lookback_days=90`, `hidden_size=32`, `num_layers=1`,
   `split.train_window.start=2000-01-01`, dataset `delta_version=268`. Selección por VAL, nunca
   TEST (§3.7, ya decidido).
2. **Fijado con el mecanismo real de esta fase**: `rio-search champions set --run
   2bad22f8bdd54e2cb39e071398881b51 --target caudal` (`PromoteChampion`) — alias
   `champion_caudal` fijado en Unity Catalog sobre `weather.ml.rio_search_bilstm` v9 (verificado
   con `MlflowClient.get_model_version_by_alias`, devuelve versión 9) y copia local en
   `data/champions.sqlite3`, con `note` explícito: *"campeon provisorio, pendiente de revision
   del usuario (weather.ml, Decision #12 / Fase 3 -- version 9 = mejor val/kge/mean=0.207 segun
   el reporte de la Fase 3, comparacion no confirmada con el usuario todavia)"* — visible en la
   UI ("Pronóstico de hoy") y en cualquier consulta de `GET /api/champions`.
3. **Nada de esto es una decisión de nombres/aliases/política de versiones** (eso sigue siendo la
   pregunta abierta de §8): es solo la elección operativa mínima para poder cerrar el criterio de
   la Fase 6 con una corrida real. Si el usuario, al revisar, decide otra versión/modelo como
   campeón, `rio-search champions set` vuelve a correrse con el `run_id` correcto — no hace falta
   tocar código, el mecanismo ya soporta reemplazar el campeón vigente en cualquier momento
   (`ChampionStorePort.set` es upsert por target, `champion_history` guarda el rastro de todas las
   promociones anteriores).

## Decisión 047: `preprocess/pipeline.pkl` (§3.5 del plan) nunca se logueó en la Fase 2/3 —
`IssueDailyForecast` reconstruye el `ImputerStats`/`ScalerStats` de forma determinista desde
`split/split.json` del propio run campeón, sin tocar `RunSearch`

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow real: `IssueDailyForecast` cargó el
campeón real de la Decisión 046 y predijo un pronóstico real, verificado bit-idéntico entre CUDA y
CPU (ver Decisión 048).

### Contexto

El plan (§3.5, lista de artefactos de un trial) dice que cada run loguea `preprocess/pipeline.pkl`
(imputador + escalador ajustados con TRAIN). Al implementar `IssueDailyForecast` (§3.8, paso 2:
"carga el campeón — `run_id` → `model/`, `preprocess/pipeline.pkl`, `features/spec.json` —
exactamente los artefactos del run, nada se recalcula distinto") se encontró que **ese artefacto
nunca se implementó**: `application/experiments/run_search.py` (Fase 2/3, ya cerrada y con 264
tests en verde) calcula `ImputerStats`/`ScalerStats` en memoria (`BuildFeatureMatrix.execute`,
Fase 1) pero nunca los serializa a MLflow — se verificó listando los artefactos reales del run
campeón (`2bad22f8bdd54e2cb39e071398881b51`): `code/`, `config/`, `features/`, `model/`,
`predictions/`, `split/`, `timings/`, sin ningún `preprocess/`. Sin ese artefacto, cargar "los
mismos artefactos del run, nada recalculado distinto" tal como pide literalmente el paso 2 es
imposible.

### Decisión

1. **No se modificó `RunSearch` ni `BuildFeatureMatrix`** (Fase 1-3, ya cerradas y testeadas):
   agregar el logueo de `preprocess/pipeline.pkl` ahí es un cambio válido para una fase futura,
   pero esta fase evita tocar código ya cerrado cuando existe una alternativa sin ese riesgo — y
   además no hubiera resuelto el problema para las versiones **ya registradas** (9-12), que de
   todos modos no tienen el artefacto.
2. **`IssueDailyForecast` reconstruye el pipeline de preprocesamiento de forma determinista**,
   usando artefactos que sí existen en todo run real: descarga `split/split.json` (fechas exactas
   de TRAIN del propio run: `2000-01-01..2024-07-12` para el campeón de la Decisión 046) y
   `config/experiment.yaml` (grupos de features, transforms, método de escalado — el YAML
   completo tal como corrió), recorta el dataset **actual** (recién refrescado, §3.6) a ese mismo
   rango de fechas de TRAIN, y vuelve a correr `BuildFeatureMatrix.execute` (el mismo código de
   la Fase 1, sin tocarlo) sobre ese recorte — obteniendo el mismo `ImputerStats`/`ScalerStats`
   que el entrenamiento original, siempre que Gold no reescriba datos históricos (solo agregue
   días nuevos, que es como se comporta hoy). Implementado en
   `application/predictions/issue_daily_forecast.py::IssueDailyForecast._build_inference_window`.
3. **Riesgo documentado, no observado hasta ahora**: si alguna vez Gold corrige un valor histórico
   (no solo agrega días), esta reconstrucción dejaría de ser idéntica al pipeline que efectivamente
   entrenó el modelo — divergencia silenciosa, no hay forma de detectarla sin el `pipeline.pkl`
   real para comparar. Mitigación futura natural: agregar el logueo de `preprocess/pipeline.pkl`
   en `RunSearch` (Fase 9 o antes) para que los *próximos* campeones no dependan de esta
   reconstrucción — la Fase 6 no lo hizo para no ampliar su propio alcance sobre código ya cerrado.
4. **Hallazgo relacionado, mismo mecanismo**: `_load_champion_model` (mismo archivo) no puede
   asumir que todo adaptador serializa igual — `BaseTorchAdapter.save/load` (Decisión 039) escribe
   `model_state_dict.pth`/`architecture.json` y **ignora** el nombre de archivo que recibe (usa
   `path.parent`), mientras que los adaptadores naive (`PersistenceAdapter`, etc.) escriben/leen
   literalmente el archivo que reciben — y `run_search.py` siempre llama
   `adapter.save(tmp_dir / "model_state.json")` para cualquier familia. Pasar exactamente ese mismo
   nombre (`model_state.json`) a `adapter_cls.load(...)`, y resolver `adapter_cls` desde el tag
   `rio_search.model` del run (nunca desde `architecture.json`, que solo existe para adaptadores
   torch) reproduce el contrato real de cualquier adaptador sin que `IssueDailyForecast` necesite
   conocerlo — encontrado escribiendo el test offline con el adaptador `persistence` como campeón
   de prueba (`tests/test_issue_daily_forecast.py`), antes de correr contra el campeón real.

## Decisión 048: Cierre de la Fase 6 (Inferencia diaria) — `IssueDailyForecast` verificado real
contra Databricks/MLflow con el campeón provisorio de la Decisión 046, CUDA y CPU reproducen el
mismo pronóstico bit a bit, Task Scheduler probado y desregistrado

### Estado

`Aceptada` (2026-08-27), verificada contra Databricks/MLflow real (no simulada): dos corridas
reales de `rio-search predict run --target caudal` (una en CUDA por default, una forzada en
`--device cpu`) contra el campeón provisorio de la Decisión 046, con el mismo `dataset_delta_version=268`,
mismo `as_of=2026-08-23` y **predicciones bit-idénticas** en los 8 horizontes entre ambos
dispositivos (t+1=1514.76 ... t+14=1503.67, verificado comparando los valores exactos logueados en
cada run de MLflow). UI ("Pronóstico de hoy") verificada con navegador headless
(`browser-automation`) contra el backend real: 0 errores de consola, 0 requests fallidos, los 8
puntos del pronóstico, `as_of`, `data_lag_days`, `dataset_delta_version`, `champion_run_id`,
`device` y el panel de tiempos visibles con datos reales; el botón "Promover a campeón" de
`RunPage.tsx` (que quedó deshabilitado al cierre de la Fase 5) se probó real haciendo click en el
navegador headless y re-promovió el campeón con éxito (`POST /api/champions` real, verificado con
`GET /api/champions` después del click). Tarea de Task Scheduler `RioSearch_Daily_Forecast`
registrada, verificada (`Get-ScheduledTask`: trigger diario a las 06:30, acción apuntando al
wrapper correcto) y **desregistrada** al terminar la prueba — no queda ninguna tarea programada
real corriendo en la máquina del usuario sin que lo haya pedido. 302 tests offline en verde (264
de las Fases 0-5 + 38 nuevos de esta fase), 2 `integration` deseleccionados sin cambios; `ruff
check` limpio; `npm run build` (`tsc -b` estricto) y `oxlint` limpios (mismo warning preexistente
de `LaunchPage.tsx`, no de esta fase).

### Contexto

La Fase 4/5 dejaron el botón "Promover a campeón" deshabilitado y el ítem de navegación
"Pronóstico de hoy" sin agregar, ambos marcados explícitamente como pendientes de esta fase
(Decisión 045, "Pendientes para la Fase 6"). El plan (§3.8) pide el protocolo completo de
inferencia diaria: refresco del dataset, resolución de device (Decisión #6, también en cada
re-ejecución de predicción), carga del campeón exactamente como se guardó (Decisión 039),
`AsOfPolicy`, predicción t+1…t+7/t+14, persistencia local (SQLite + parquet) y un run corto en
`daily_forecast` con sus tiempos — más Task Scheduler a las 06:30 Montevideo y la página "Pronóstico
de hoy" en la UI.

### Decisión

1. **Dominio nuevo** `domain/predictions/` (`Champion`, `Forecast`/`ForecastPoint`,
   `AsOfPolicy`) y **aplicación nueva** `application/predictions/` (`PromoteChampion`,
   `IssueDailyForecast`, `BacktestRecent`), con sus puertos (`ChampionStorePort`,
   `ForecastRepositoryPort`, `ModelAliasPort`, `ArtifactRepositoryPort`, `VolumePublisherPort`) e
   infraestructura (`SqliteChampionStore`, `SqliteForecastRepository`,
   `MlflowArtifactRepository`, `MlflowModelAlias`, `DatabricksVolumePublisher` — este último sobre
   un método `upload` nuevo, aditivo, en `DatabricksVolumeFiles`) — mismo patrón Onion+DDD que el
   resto del backend, sin tocar `domain`/`application` de fases anteriores.
2. **`PromoteChampion`** valida el run real contra `TrackingReadPort` (tags `rio_search.model`/
   `rio_search.target`, métrica pedida presente), fija el alias `champion_<target>` en Unity
   Catalog (si el run registró un modelo) y persiste en SQLite con historial append-only por
   target. Usado para fijar la Decisión 046.
3. **`IssueDailyForecast`** (ver Decisión 047 para el hallazgo del `pipeline.pkl` faltante):
   `RefreshDataset` (mismo stopwatch compartido que `RunSearch`, patrón idéntico) → resuelve
   device → descarga `config/`, `split/`, `features/`, `model/` del campeón → reconstruye el
   pipeline → `AsOfPolicy` (ffill acotado **sin** relleno por mediana, para no fabricar el dato
   del día más reciente — a diferencia de la imputación de entrenamiento) → predice una única
   ventana → guarda `Forecast` (SQLite + parquet) → loguea un run corto en
   `/Users/<profile>/rio_search/daily_forecast` con tags (`as_of`, `dataset_delta_version`,
   `champion_run_id`, `device`, procedencia) y `time/{dataset_refresh_s,model_load_s,
   preprocess_s,predict_s,total_s}` (más los sub-pasos de `dataset_refresh_s`, §3.12) —
   verificado real en ambos runs (CUDA: `total_s=70.9s`, dominado por `model_load_s=44.3s` y
   `dataset_refresh_s=26.3s` porque disparó `dataset_gold_version_s`; CPU: `total_s=48.5s`, sin
   volver a pegarle a la Statement API para la versión de Gold — el manifest ya estaba fresco).
   Soporta `per_horizon` (un `_PerHorizonEnsemble` que carga los N modelos de horizonte) aunque no
   se ejerció contra un campeón real `per_horizon` (el campeón provisorio es `multi_output`) —
   cubierto solo por tests offline.
4. **`rio-search predict run` toma el mismo `ProcessLock`** que `SubprocessJobRunner`/`rio-search
   search run` (Decisión 044): la tarea diaria y una búsqueda lanzada a mano o desde la API nunca
   compiten por el cache de tokens OAuth. No estaba pedido explícitamente por el criterio de
   cierre, pero es la forma directa de cerrar el aviso operativo que el propio encargo de esta
   fase señalaba como relevante.
5. **`--publish` implementado, no ejercitado contra Databricks real** (instrucción explícita del
   agente principal para esta fase): sube el parquet de un `Forecast` a
   `/Volumes/weather/raw/gold_export_volume/forecasts/` vía `DatabricksVolumeFiles.upload`
   (método nuevo, `client.files.upload(path, io.BytesIO(contents), overwrite=True)`). Cubierto por
   tests offline (`FakeVolumePublisher`) únicamente.
6. **Task Scheduler**: `scheduler/run_daily_forecast_task.ps1` (wrapper que activa el `.venv`
   propio de `rio_search/backend` y corre `rio-search predict run --target caudal`) +
   `scheduler/register_tasks.ps1` (`New-ScheduledTaskTrigger -Daily -At "06:30"`, distinto del
   patrón de redisparo horario de los backfills de ANA/TIGGE porque esta corrida no tiene estado
   que retomar) — **adaptado**, no importado, del patrón de
   `notebooks_local/*/scheduler/register_tasks.ps1`, viviendo enteramente dentro de
   `rio_search/backend/scheduler/` (nada fuera de `rio_search/`). Registrado, verificado con
   `Get-ScheduledTask` (trigger/acción/descripción correctos) y **desregistrado** en la misma
   sesión — no queda ninguna tarea programada real corriendo.
7. **UI**: página `ForecastPage.tsx` (`/forecast`, agregada a `NAV_ITEMS` de `Layout.tsx`) —
   campeón vigente, abanico t+1…t+14 (Recharts), `as_of`/`data_lag_days`/`dataset_delta_version`/
   `champion_run_id`/`device`/`issued_at`/`forecast_run_id`/publicación, backtest reciente
   (`BacktestRecent`, con estado "pendiente" para `target_date` sin observado todavía) e historial
   de pronósticos. El botón "Promover a campeón" de `RunPage.tsx` (Fase 5, deshabilitado a
   propósito) ahora llama `POST /api/champions` de verdad con `useMutation` de TanStack Query,
   deriva el `target` del tag `rio_search.target` del propio run e invalida las queries de
   campeón/pronóstico para que "Pronóstico de hoy" quede al día sin recargar.
8. **API**: `POST /api/champions`, `GET /api/champions`, `GET /api/forecasts/{latest,history,
   backtest}` — de solo lectura o escritura liviana (SQLite + alias UC), **`IssueDailyForecast` no
   se expone por HTTP a propósito**: es la corrida pesada que corre por CLI/Task Scheduler, exponerla
   como endpoint duplicaría la cola de exclusión mutua que ya resuelve el `ProcessLock` del punto 4
   sin necesidad real para el criterio de cierre.

### No cubierto en esta fase (documentado, no bloqueante)

* `preprocess/pipeline.pkl` real (Decisión 047) sigue sin loguearse desde `RunSearch` — los
  *próximos* campeones seguirán dependiendo de la reconstrucción determinista hasta que se agregue
  (cambio acotado, fuera del alcance de esta fase para no tocar código ya cerrado).
* `--publish` no ejercitado contra Databricks real (punto 5 de arriba) — implementado y testeado
  offline, a la espera de que el usuario decida activarlo en el wrapper del Task Scheduler.
* Campeón `per_horizon` real no ejercitado (punto 3) — el mecanismo existe y está testeado offline,
  pero el campeón provisorio de la Decisión 046 es `multi_output`.
* La revisión de `weather.ml` (§8 del plan, nombre/alias/política de versiones) sigue pendiente del
  usuario — la Decisión 046 es explícitamente provisoria hasta esa revisión.

## Decisión 049: Cierre de la Fase 7 (Research) — biblioteca de documentos sin LLM, notas por
sección en Markdown, BibTeX real verificado con `latexmk`, y un hallazgo de `bibtex` clásico con
bytes no-ASCII antes de la primera entrada

### Estado

`Aceptada` (2026-08-27), verificada de punta a punta con el mecanismo real, no simulada: 3
documentos reales (referencias bibliográficas temáticamente pertinentes a la tesis — LSTM,
LSTM aplicado a lluvia-escorrentía y la métrica KGE que Rio_Search usa para seleccionar campeón)
cargados **desde la UI real** (`browser-automation`, Playwright, sin pegarle a la API a mano) con
subida de PDF, tags y notas por sección incluida una vinculación real a `Decisión 043`;
`rio_search/thesis/common/references.bib` generado con las 3 entradas desde el botón "Exportar
BibTeX"; un `.tex` mínimo (`rio_search/thesis/common/smoke_references.tex`) que los cita **compiló
con `latexmk` real** (MiKTeX 24.1), con las 3 entradas resueltas en el `.bbl` y
`Output written on ... smoke_references.pdf (1 page, 87018 bytes)` sin citas indefinidas. 362 tests
offline en verde (302 de las Fases 0-6 + 60 nuevas de esta fase), 2 `integration` deseleccionados
sin cambios; `ruff check` limpio; `npm run build` (`tsc -b` estricto) limpio, `oxlint` sin errores
(solo el mismo tipo de warning `set-state-in-effect` ya preexistente en `LaunchPage.tsx`, ahora
también en `ResearchPage.tsx`, no bloqueante).

### Contexto

El plan (§3.10, Decisión #3 de las decisiones cerradas antes de escribir el plan) pide una
biblioteca de investigación **sin LLM**: catálogo de documentos, notas de lectura por sección y
exportación a BibTeX, con persistencia legible y versionable (YAML + Markdown) para que el propio
repo sea la base — sin base de datos. Es la fase que cierra el bloque de la aplicación antes de
entrar a la Fase 8 (Tesis LaTeX), que arranca pidiéndole al usuario el trabajo con formato ya
validado.

### Decisión

1. **Dominio nuevo** `domain/research/` (`Tag`, `DocumentType`, `Link`/`LinkKind`, `BibEntry`,
   `Document`, `Note`) y **aplicación nueva** `application/research/` (`AddDocument`, `UpdateNote`,
   `TagDocument`, `ExportBibtex`), con sus puertos (`DocumentStorePort`, `BibliographyExportPort`)
   e infraestructura (`YamlCatalog`, `FileSystemDocumentStore`, `FileBibtexExporter`) — mismo
   patrón Onion+DDD que el resto del backend, sin tocar `domain`/`application` de fases anteriores.
   `Note` vive con `to_markdown`/`from_markdown` en el propio dominio (texto puro, sin I/O, mismo
   criterio que `Forecast.as_tags()`): 6 secciones fijas (`methodology`, `models`,
   `windows_splits`, `metrics`, `results`, `takeaways` — etiquetas visibles en español) más una
   sección `## Enlaces` con líneas estructuradas `- Decisión: Decisión NNN` / `` - Run: `run_id` ``
   que hacen round-trip exacto de vuelta a `Link` al releer el archivo.
2. **Endpoints** `GET/POST /api/research/documents`, `GET /api/research/documents/{slug}`, `PUT
   .../{slug}/tags`, `PUT .../{slug}/notes`, `GET .../{slug}/file`, `POST /api/research/export-bib`
   — el subconjunto de la tabla del plan (§3.9) se amplió con las lecturas (`GET .../{slug}`,
   `.../file`) y la escritura de tags separada de la de notas porque el plan ya modela `TagDocument`
   como su propio caso de uso; ninguno toca Databricks/MLflow (Decisión #3). `POST
   /api/research/documents` es `multipart/form-data` (requiere `python-multipart`, agregado a
   `pyproject.toml`) para poder subir el PDF en la misma request que los metadatos.
3. **CLI** `rio-search research add <pdf> --title ... --authors "A;B" --year ... [--type ...]
   [--venue ...] [--tags a,b] [--slug ...]` y `rio-search research export-bib`, tal como especifica
   §4.2 del plan.
4. **UI**: página `ResearchPage.tsx` (`/research`, agregada a `NAV_ITEMS` de `Layout.tsx`) —
   formulario de alta con subida de PDF, tabla de documentos con tags y link al archivo, panel de
   edición (tags, notas por sección con textarea por sección, alta/baja de enlaces estructurados a
   Decisión/run) y panel de exportar BibTeX con el resumen real (`output_path`, `entry_count`,
   `keys`) devuelto por el propio endpoint.
5. **Hallazgo real, no trivial**: el `bibtex` clásico que trae MiKTeX (no `bibtex8`/`biber`) **no es
   Unicode-aware** — un carácter no-ASCII en el archivo `.bib` *antes* de la primera entrada
   (probado con `§`, bytes UTF-8 `0xC2 0xA7`, en el comentario de cabecera que generaba
   `FileBibtexExporter`) descoloca su lexer y hace que reporte silenciosamente **0 entradas**, sin
   ningún error visible, aunque el archivo tenga las entradas bien formadas — `bibtex` seguía
   diciendo "Warning--I didn't find a database entry" para los 3 `\cite{}` aunque
   `references.bib` los tuviera. Corregido: `FileBibtexExporter._HEADER` es ASCII puro y el archivo
   se escribe con `newline="\n"` explícito (antes usaba el `\r\n` por defecto de `Path.write_text`
   en Windows) — ambos cambios documentados como salvaguardas, aunque el bloqueo real de esta
   verificación resultó ser un problema **separado y ambiental**: correr `latexmk` a través de Git
   Bash (MSYS) reescribe `BIBINPUTS`/`BSTINPUTS` a rutas estilo `/c/Users/...` que el `bibtex.exe`
   nativo de MiKTeX no interpreta, y sólo se resolvió corriendo `latexmk` desde PowerShell nativo
   (mismo intérprete, mismo `.tex`, mismo `.bib`: 0 citas indefinidas, `.bbl` con las 3 entradas
   completas). **Queda anotado para la Fase 8**: compilar la tesis con `latexmk` desde PowerShell,
   no desde Git Bash, en esta máquina.
6. **Limitación conocida, no resuelta a propósito**: `BibEntry.to_bibtex()` no escapa caracteres
   no-ASCII en campos de entrada (títulos/autores con acentos que sí puede tener un documento real,
   a diferencia de los 3 de prueba). Si aparece en una fase futura, hace falta o bien `bibtex8`/
   `biber` en vez de `bibtex` clásico, o escapar a secuencias LaTeX (`\'{e}`, etc.) en el propio
   `to_bibtex()` — fuera de alcance de esta fase.
7. **PDFs de prueba**: no se descargaron PDFs reales de internet (fuera del alcance pedido, "no
   hace falta... investigación bibliográfica real exhaustiva"); se generó un PDF mínimo válido por
   documento (estructura PDF 1.4 escrita a mano, sin librerías — `reportlab`/`fpdf` no están en el
   entorno) con el título como placeholder de texto, documentado acá en vez de en el repo.
8. **Referencias usadas** (temáticamente reales, no aleatorias): Hochreiter & Schmidhuber (1997,
   *Long Short-Term Memory*, slug `hochreiter-1997-lstm`) — el trabajo fundacional del LSTM que usa
   el baseline de la Fase 3; Kratzert et al. (2018, *Rainfall-runoff modelling using LSTM
   networks*, HESS, slug `kratzert-2018-lstm-rainfall-runoff`) — aplicación directa de LSTM a
   caudales; Gupta et al. (2009, *Decomposition of the mean squared error and NSE performance
   criteria*, J. Hydrology, slug `gupta-2009-kge`) — el paper que introduce KGE, métrica que
   Rio_Search usa para seleccionar campeón (§3.7 del plan, `val/kge/mean`).

### Pendiente para el agente principal

Al cierre de esta fase corresponde pedirle al usuario **el trabajo con formato LaTeX ya validado**
para `rio_search/research/templates/` (insumo de la Fase 8, §8 del plan) — este sub-agente no
puede pedírselo directamente.

---

## Decisión 050: Cierre de la Fase 8 (Tesis LaTeX) — clase propia extraída del modelo del
usuario, dos documentos que compilan real con `latexmk`, y `rio-search thesis export` como puente
verificado con MLflow real

### Estado

`Aceptada` (2026-08-27), verificada de punta a punta con el mecanismo real: los dos documentos
(`rio_search/thesis/proyecto/main.tex`, `rio_search/thesis/tesis/main.tex`) compilan con
`latexmk -pdf -outdir=build` corrido **desde PowerShell nativo** (Decisión 049), 0 referencias y 0
citas indefinidas en ambos `build/main.log`, con salida real: `proyecto/build/main.pdf` (11
páginas, 263.596 bytes) y `tesis/build/main.pdf` (15 páginas, 325.601 bytes). `rio-search thesis
export --run 6e086068c9ef41a3afd8209518bf26a2 --compare f3738cdae71f4007b02ad98955b2e65e` corrió
contra Databricks/MLflow real (experimentos `/rio_search/bilstm` y `/rio_search/baselines`) y
generó `thesis/tables/metrics_6e086068c9ef.tex`, `thesis/tables/compare_6e086068c9ef.tex` y
`thesis/figures/metric_vs_horizon_6e086068c9ef.{pdf,tex}`, los tres con el/los `run_id` real(es)
en un comentario LaTeX; el capítulo de Resultados de `thesis/tesis/` los incluye con `\input` y
compiló junto con el resto del documento (`(../figures/metric_vs_horizon_6e086068c9ef.tex)
[10 <.../metric_vs_horizon_6e086068c9ef.pdf>]` en el log). 367 tests offline en verde (362 de las
Fases 0-7 + 5 nuevas de esta fase), 2 `integration` deseleccionados sin cambios; `ruff check`
limpio; `npm run build` (`tsc -b` estricto + Vite) limpio, sin tocar el frontend.

### Contexto

El plan (§3.11, Decisión #8 de las decisiones cerradas antes de escribir el plan) pide extraer el
formato de un trabajo ya presentado y validado por el usuario
(`rio_search/research/templates/FINAL-G1-TSCHOPP-JOAQUIN-2025.tex`, proyección de calidad de agua
en el embalse de Salto Grande — otro tema, misma carrera) y replicarlo en `thesis/common/` para dos
documentos nuevos (`proyecto/`, `tesis/`) de la tesis de Río Uruguay, más un puente
`rio-search thesis export` que genere figuras/tablas desde runs reales de MLflow.

### Decisión

1. **Clase LaTeX propia** `rio_search/thesis/common/riosearch.cls` (`\LoadClass[11pt]{report}`)
   en vez de reusar el `.tex` del modelo tal cual: reproduce exactamente su conjunto de paquetes
   (`inputenc[utf8]`, `babel[spanish]`, `fontenc[T1]`, `lmodern`, `geometry` con márgenes de 3cm,
   `setspace`+`onehalfspacing`, `hyperref`, `longtable`, `booktabs`, `graphicx`, `subcaption`,
   `enumitem`, `apacite`+`natbib` juntos — combinación no recomendada por `apacite` pero es la que
   el modelo del usuario ya probó y compiló, `research/templates/*.bbl` existe) y su estilo de
   portada (escudo + Universidad de Buenos Aires + Facultad de Ciencias Exactas y Naturales +
   Maestría en Explotación de Datos y Descubrimiento de Conocimiento), pero parametrizado por
   comandos (`\riosearchstage`, `\riosearchtitle`, `\riosearchauthor`, `\riosearchdirector`,
   `\riosearchyear`, `\makeriosearchcover`, `\riosearchbibliography`) para poder reusarla en los
   dos documentos con título/autor/fecha de Río Uruguay. El escudo (`img/escudo_uba.png`) se copió
   de `research/templates/Imagenes/` a `thesis/common/img/` — el archivo del usuario en
   `research/templates/` no se tocó.
   **Pendiente de confirmación del usuario** (§8 del plan): la institución/carrera de la portada
   se copió tal cual asumiendo que es el mismo programa de esta tesis — si no lo es, ajustar
   `\riosearchinstitution`/`\riosearchfaculty`/`\riosearchprogram` en `riosearch.cls`.
2. **Dos documentos**, capítulos en archivos separados, `\input` desde `main.tex`:
   `thesis/proyecto/` (`chapters/01_introduccion.tex` … `04_plan_de_trabajo.tex`) y `thesis/tesis/`
   (`chapters/01_introduccion.tex` … `05_conclusiones.tex`) — contenido real y específico del
   proyecto (dataset, `ana_74100000`, decisiones citadas por número, resultado preliminar del
   BiLSTM), no relleno genérico; no es la tesis terminada, es el esqueleto que el criterio de
   cierre pide (que compile, no que esté completo). El capítulo de Metodología de ambos documentos
   cita explícitamente las Decisiones 018, 019, 021, 033, 039, 042, 043 y 046 (`docs/decisions.md`)
   como justificación de cada elección de diseño, tal como pide §3.11 del plan.
3. **Hallazgo real de compilación, no anticipado por el plan**: `latexmk -outdir=build` cambia el
   directorio de trabajo a `build/` **solo** para invocar `bibtex` (no para `pdflatex`, que recibe
   `-output-directory` sin cambiar de directorio) — así que una ruta relativa fija en
   `\bibliography{...}` no puede servir a la vez para el chequeo previo de latexmk (que resuelve
   la ruta relativa al directorio del `.tex` principal) y para la ejecución real de `bibtex` (que
   la resuelve relativa a `build/`, un nivel más abajo). Se resolvió sacando la ruta de
   `\bibliography{references}` (sin ruta) y agregando `thesis/common/` a la variable de entorno
   `BIBINPUTS` en un `.latexmkrc` por documento (`thesis/proyecto/.latexmkrc`,
   `thesis/tesis/.latexmkrc`, cada uno resuelve `../common` a ruta absoluta con `Cwd::abs_path`
   antes de que `latexmk` cambie de directorio) — con eso, un nombre sin ruta lo encuentra
   `kpathsea` sin importar el directorio de trabajo real en cada paso. Documentado en un comentario
   extenso en `riosearch.cls` para que no se repita el diagnóstico si se agrega un tercer documento.
4. **`rio-search thesis export --run <run_id> [--compare <run_id> ...]`** (CLI nuevo,
   `interfaces/cli/main.py`, `thesis_app`): `application/thesis/export_thesis_artifacts.py`
   (`ExportThesisArtifacts`) reusa el mismo `TrackingReadPort` cacheado en SQLite de la Fase 4 (sin
   puerto nuevo) para leer `RunRecord.metrics` (`{split}/{metrica}/hNN`, el mismo formato jerárquico
   que loguea `MetricSet.as_mlflow_metrics` desde la Fase 2) y delega el renderizado a
   `infrastructure/thesis/latex_export.py`: tablas LaTeX (`booktabs`) y una figura `matplotlib`
   (backend `Agg`, sin GUI) con NumPy/listas puras — **nunca `pandas`**, ni siquiera `polars` hace
   falta porque los datos ya llegan como `dict[str, float]` desde MLflow, no como artefacto
   parquet. Cada archivo generado (`thesis/tables/metrics_<id>.tex`,
   `thesis/tables/compare_<id>.tex` si se pasa `--compare`,
   `thesis/figures/metric_vs_horizon_<id>.{pdf,tex}`) lleva el/los `run_id` de origen en un
   comentario `%` al inicio — el `.tex` de la figura es el que un capítulo hace `\input`; el `.pdf`
   además lleva los `run_id` en sus metadatos (`Subject`). Un run sin métricas `{split}/<m>/hNN`
   (p. ej. el run padre de una búsqueda) levanta `ThesisExportError` con un mensaje explícito en
   vez de escribir una tabla vacía.
5. **`matplotlib>=3.8` agregado a `pyproject.toml`** (única dependencia nueva de la fase): no
   arrastra `pandas` (verificado — `test_no_pandas_in_env` sigue en verde tras `uv sync`), así que
   no viola la Decisión #9.

### Consecuencias

* `rio_search/thesis/common/riosearch.cls` es la única fuente del formato de portada/bibliografía
  para cualquier documento LaTeX futuro de la tesis — si el usuario aporta una versión corregida
  del modelo o cambia de programa/carrera, el cambio se hace en un solo archivo.
* Los archivos generados por `rio-search thesis export` (`thesis/figures/*.{pdf,tex}`,
  `thesis/tables/*.tex`) se versionan en git como entregable de la tesis (§3.1 del plan los lista
  en el árbol del repositorio); solo `thesis/**/build/` (la salida de compilar los documentos) está
  gitignorado — un futuro `rio-search thesis export --run <otro_id>` no pisa los archivos de este
  ejemplo porque el nombre incluye el prefijo del `run_id`.
* El ejemplo real usado (`run_id=6e086068c9ef41a3afd8209518bf26a2`, BiLSTM `multi_output`, vs.
  `run_id=f3738cdae71f4007b02ad98955b2e65e`, persistencia) confirma en TEST lo ya documentado en la
  Decisión 043: la persistencia es difícil de superar en `t+1`, pero el BiLSTM iguala o supera su
  KGE a partir de `t+2`.
* Queda pendiente, no bloqueante: escribir el contenido completo de ambos documentos (hoy son
  esqueletos reales pero parciales) y decidir, junto con el usuario, si la institución/carrera de
  la portada extraída del modelo aplica igual a esta tesis.
