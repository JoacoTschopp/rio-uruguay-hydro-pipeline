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
