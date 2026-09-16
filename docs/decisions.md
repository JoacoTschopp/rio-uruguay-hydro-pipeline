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

## Decisión 047: `repartition()` antes de `toPandas()` en el Silver de ECMWF

**Problema.** Desde el 2026-09-08 el job `ECMWF_Forecast_Daily_Incremental` (job_id
756555076983243) fallaba todos los días en `ETL_Silver_ECMWF_CF`; el último éxito había sido el
2026-09-07. El error era `ArrowInvalid` dentro de `chunk_df.toPandas()`.

La causa no es el volumen de datos: Bronze devuelve los `RecordBatch` de Arrow con **nullability
distinta para `run_date` según el parquet de origen**. Los archivos escritos por la ruta
histórica y los escritos por la ruta diaria no coinciden en ese detalle del esquema, y al
concatenar los batches en el driver Arrow rechaza la unión.

**Decisión.** Una línea, en los dos notebooks Silver de ECMWF (`_CF` y `_PF`):

```python
pdf = chunk_df.repartition(8).toPandas()
```

`repartition()` fuerza un shuffle, y el shuffle re-serializa: todos los batches salen con el
mismo esquema y la concatenación deja de fallar. El costo es un shuffle sobre un chunk ya
acotado a 60 días.

**Por qué no se arregló el esquema de Bronze.** Reescribir el parquet histórico para uniformar
la nullability es una reescritura de ~900 GB para corregir un detalle que solo importa en el
borde Arrow→pandas. La alternativa barata resuelve el mismo problema sin tocar el dato.

**Nota.** Los notebooks se publicaron con `databricks workspace import --format JUPYTER
--overwrite` y se verificaron re-exportando: `bundle deploy` **no** actualiza el contenido de un
notebook ya publicado, solo la definición del job.


## Decisión 048: el pronóstico se agrega por sub-cuenca en Silver y colapsa a un número en Gold

**Problema.** Bronze guarda el pronóstico punto a punto: para `pf` son 436 puntos × 16 pasos ×
50 miembros por día, ~1.100 millones de filas en el histórico. Ningún modelo hidrológico agregado
consume eso, y no había ninguna tabla entre Bronze y `training_dataset_v0`.

**Decisión.** Dos saltos, con una división de trabajo deliberada.

**En Silver** (`weather.silver.ecmwf_forecast_{cf,pf}_subcuenca`, notebook
`ETL_Silver_ECMWF_Subcuenca`): una fila por `(run_date, run_time, step_hours, miembro,
sub-cuenca)`.

- **Se promedian los puntos** de cada sub-cuenca. La media areal es la entrada natural de un
  modelo agregado. `n_puntos` viaja en la fila: sin él, un día con cobertura parcial da una media
  sesgada hacia la parte de la cuenca que sí llegó y nada lo delata.
- **Se conservan los 50 miembros.** Promediarlos acá borraría la dispersión del ensemble, que es
  la única medida de incertidumbre que aporta `pf` — y sería irreversible sin reprocesar Bronze.
- **Se mantienen las tres sub-cuencas.** En Silver está todo; el recorte es de Gold.

**En Gold** (`training_dataset_v0`): solo `alta_frontera` (Decisión 018), y el ensemble colapsa a
un número. `tp_mm_medio` viene **acumulado** desde el inicio del pronóstico (así lo entrega
TIGGE), así que la lluvia del día de adelanto `d` es la diferencia entre el paso `24d` y el
`24(d-1)`: publicar el acumulado crudo daría 15 columnas fuertemente colineales y ninguna en la
unidad "mm que caen ese día".

**La métrica sobre los miembros es la media, y es provisional.** Promediar el ensemble tira
justamente la dispersión por la que se bajó. Está elegida para cerrar el pipeline hasta Gold, no
porque sea la correcta; el reemplazo (P90, máximo, fracción de miembros sobre umbral) se
implementa cambiando un `F.avg` en el notebook de Gold, sin tocar nada aguas arriba. Ese es el
punto de conservar los miembros en Silver.

**La fuente del agregado es Bronze + `weather.silver.punto_subcuenca`, no `*_basin`.** Los dos
caminos aplican el mismo point-in-polygon; la diferencia es el costo. `ETL_Silver_ECMWF_{CF,PF}`
lo recalcula con `toPandas()` + geopandas sobre todas las filas; el mapa tiene **436 puntos** y
el agregado se resuelve con un JOIN. Medido: el agregado de `pf` sobre 1.175 días corrió en **20
segundos**. `punto_subcuenca` se deriva de `*_basin` justamente para que el tageo tenga una sola
fuente de verdad y las dos tablas Silver no puedan divergir.

**Por qué el job de pronóstico vuelve a materializar Gold.** `Silver_Gold_Daily_Incremental`
corre 04:30 America/Montevideo (07:30 UTC) y `ECMWF_Forecast_Daily_Incremental` a las 08:00 UTC:
media hora después. Sin un segundo pase de Gold al final del job de pronóstico, el dataset
publicaría siempre el pronóstico del día anterior. La ventana de Gold es `delete` + `append` sobre
un rango, o sea idempotente: correrlo dos veces por día no duplica ninguna fila.

**Por qué `pf` no tiene task de Landing en el job diario.** El ensemble lo baja el backfill local
continuo (`run_tigge_backfill.py`), cuya grilla de lotes ya llega hasta `date.today() -
TIGGE_LAG_DAYS`. Agregar una descarga de `pf` en Databricks pondría un segundo cliente contra la
misma cola de ECDS — exactamente lo que prohíbe la Decisión 012.

**Cobertura conocida.** `pf` arranca en 2006-10 y Gold en 2000-01-01, así que las columnas de
pronóstico quedan en NULL para los primeros ~6 años del dataset. Es por construcción, no un
defecto de carga.

**Verificación** (2026-09-14, sobre el estado real de las tablas):

| tabla | días | filas | control |
|---|---|---|---|
| `bronze.ecmwf_forecast_cf` | 6.706 | 115.561.080 | — |
| `silver.ecmwf_forecast_cf_subcuenca` | 6.706 | 321.003 | = 6.706×16×3 − 59×5×3 |
| `bronze.ecmwf_forecast_pf` | 3.138 | 2.710.692.000 | — |
| `silver.ecmwf_forecast_pf_subcuenca` | 3.138 | 7.529.700 | = 3.138×16×50×3 − 1.500 (día parcial 2019-10-17) |

Los dos agregados igualan a Bronze día por día. El de `pf` —1.963 días nuevos, ~1.700 millones
de filas de entrada— corrió en **3,6 minutos**.

**Traza de un día completo** (`run_date = 2026-09-11`, bajado ese mismo 2026-09-14 a las 02:52
UTC), capa por capa:

| capa | filas |
|---|---|
| Bronze (bounding box) | 17.280 = 1.080 puntos × 16 pasos |
| Silver `*_basin` (dentro de la cuenca) | 6.976 = 436 × 16 |
| Silver `*_subcuenca` | 48 = 3 × 16 |
| Silver, solo `alta_frontera` | 16 |
| Gold | 1 fila |

`ecmwf_cf_tp_mm_d1` de Gold da **53,997476**, y reconstruirlo a mano desde Silver
(`tp` del paso 24h menos el del paso 0h) da **53,997476**. Diferencia 0.

**La acumulación quedó confirmada empíricamente**, que era el supuesto del que dependía todo el
cálculo: el `tp` promedio de `alta_frontera` para una corrida cualquiera crece monótonamente de
0,0 mm en el paso 0 a 192,4 mm en el paso 360. `UNIT_TO_MM_FACTOR = 1.0` es correcto (kg/m² = mm).

**Anomalía menor registrada, sin corregir.** 34 de 29.530 incrementos muestreados dan un valor
negativo, con mínimo **−0,0027 mm**. Es ruido de empaquetado del GRIB en el campo acumulado, no
un error del cálculo — la magnitud lo demuestra. No se recorta a cero porque eso cambia valores
del dataset, y qué entra en el dataset es una decisión que no toma la capa medallón.


## Decisión 049: bisección del lote fallido y registro de días que la fuente no entrega

**Problema.** La grilla alineada al calendario de la Decisión 044 destapó un hueco que la grilla
solapada anterior venía salteando sin que nadie lo notara: el pedido `2016-09-02..2016-12-31`
devolvía `400` de ECDS, cortaba `cf` y, por el encadenamiento de `run_tigge_backfill.py`, dejaba
`pf` bloqueado. **48 fallos idénticos, dos días sin bajar nada.**

La primera hipótesis —la cinta dañada J0018900 (Decisión 031)— era **falsa**: una sonda en vivo
demostró que el dato estaba disponible. Sondeando por tamaño de rango (3, 30 y 45 días pasaban;
46 y 121 fallaban) el problema se acotó a **un solo día malo, `2016-12-29`**.

**Decisión.** Dos piezas en `common_ecmwf.py`:

1. **`retrieve_bisecting(retrieve, raw_path_for, start, end)`** — ante un fallo, parte el rango
   en dos y reintenta cada mitad, hasta rangos de un día. Un día que la fuente no sirve deja de
   costar el lote entero.
2. **Registro de días no disponibles** (`tigge_unavailable_days.json`, escrito atómicamente vía
   `.tmp` + `replace`): cuando falla un pedido de **un solo día**, se anota con su motivo.
   `missing_span()` los excluye del cálculo de pendientes.

El registro no es cosmético: sin él, `_pending_batches()` nunca llega a 0 para ese lote y el
`while True` de `run_source()` queda pidiendo en bucle un día que la fuente jamás va a entregar.

**Resultado.** De los 121 días del lote se recuperaron **120**; queda registrado `2016-12-29`
como no disponible.

**Lección.** El corte ante el primer fallo (Decisión 030) evita bombardear una cola con rate
limit, pero convierte cualquier día malo en un bloqueo total. La bisección es lo que distingue
"la fuente está caída" de "este día puntual no existe" — y solo el primero justifica parar.

## Decisión 050: el cupo de lotes por llamada se baja a 1 para que el frente diario no se muera de hambre

**Problema.** El 2026-09-15 `pf` estaba **8 días atrasado** (último día en cualquier lado:
2026-09-05) mientras el backfill seguía trabajando en 2017-08. No era un fallo: nada estaba
roto, ningún log tenía un error.

La reconstrucción de lo que pasó:

- El proceso arrancó el **2026-09-07 18:17**. Tres minutos después bajó el frente — los JSON
  `2026_09_02..05` tienen mtime `09-07 18:20`.
- Desde entonces retrocedió por el histórico y **no volvió a mirar el frente nunca más**.

La causa está en el reparto de responsabilidades entre `run()` y `run_source()`: `run()` arma su
lista de lotes **una sola vez** al entrar y la recorre hasta agotar `max_batches_per_run`; recién
cuando vuelve, `run_source()` recalcula qué falta. Con el cupo en **25** y un ritmo medido de
**11,6 h por lote**, una sola llamada dura **~12 días**, y en todo ese tiempo los días nuevos no
se piden aunque encabecen la grilla.

Lo agravaba un segundo detalle: el `ExecutionTimeLimit` de 6 h de Task Scheduler mata al wrapper
de PowerShell pero **no al hijo de Python**, así que el proceso quedó huérfano. La tarea figuraba
como "Listo", los redisparos horarios encontraban el lock tomado por un PID vivo y salían sin
hacer nada, y el huérfano siguió moliendo hacia atrás sin re-evaluar.

**Decisión.** `--max-batches-per-call 25` → **1**, y `--sync-every-calls 3` → **1**.

Con cupo 1 se recalcula la lista después de **cada** lote. Como `iter_batches_calendar_backward`
ordena del mes más reciente hacia atrás, el frente se sirve siempre antes que el histórico, y
cuando está completo la llamada sigue con el lote viejo que toque. **No cambia cuántos requests
se hacen ni su tamaño** — solo cada cuánto se re-prioriza, y eso es gratis.

Bajar el sync a 1 es consecuencia: con un lote por llamada, sincronizar cada 3 dejaría ~26 GB de
JSON en `C:` y hasta 35 h hasta que el día llegue al Volume.

El arreglo también inmuniza contra el huérfano: aunque el wrapper muera a las 6 h, el hijo sigue
con cupo 1 y re-evalúa el frente en cada vuelta.

**Costo de aplicarlo.** Hubo que matar el proceso huérfano (PID 342888) para que el cambio
tomara efecto — con el cupo viejo faltaban ~19 lotes, o sea ~25 días más de frente parado. Se
perdió el request de 2017-08 que estaba en vuelo; se vuelve a pedir. `tigge_lock.py` limpia solo
el lock del PID muerto (`_pid_is_running` vía `tasklist`), no hubo que tocarlo.

**Nota de diagnóstico.** `tasklist /FI "PID eq N"` desde Git Bash necesita
`MSYS2_ARG_CONV_EXCL="*"`: sin eso, MSYS convierte `/FI` en una ruta y el comando falla con
"Argumento u opción no válido", que a simple vista parece "el proceso no existe". El proceso
estaba vivo y además corría como `python3.12.exe`, no `python.exe`, así que filtrar por
`IMAGENAME eq python.exe` tampoco lo mostraba.

## Decisión 051: los lotes de `pf` pasan a trimestres calendario

**Problema.** Al 2026-09-15, `pf` tenía 3.323 de 7.288 días (46%) y quedaban **131 lotes
mensuales**. Al ritmo medido de **11,6 h por lote** eso son **63 días — 9 semanas**, hasta
mediados de noviembre.

La medición es lo que define el problema: 16 requests en 174,6 h de reloj, con una transferencia
real de ~10 s para 72 MB. **El costo es casi todo cola de ECDS, no descarga.** Por lo tanto el
tiempo total lo fija la *cantidad* de requests, no su tamaño — y ahí es donde se puede ganar.

**Decisión.** `BATCH_MONTHS = 1` → **3** en `historic_pf_tigge.py`. La grilla pasa de 240 lotes
mensuales a 80 trimestrales, y los pendientes de **131 a 45**.

**Por qué 3 y no más.** Un trimestre son 91 × 16 × 50 = **~72.800 fields**: 3× el request
mensual que ya demostró funcionar (24.800) y por debajo del límite documentado de otros datasets
CDS (ERA5 horario: 120.000). Un lote anual serían 292.000, fuera de escala — y en la Decisión
044 los tres `400 Client Error` observados cayeron justamente en los lotes anuales de `cf`.

**Por qué recién ahora.** Cuando se fijó `BATCH_MONTHS = 1`, un lote grande que fallara costaba
el lote entero y bloqueaba la cadena. `retrieve_bisecting` (Decisión 049) cambió eso: un
trimestre fallido se parte en mitades hasta aislar el día que la fuente no entrega. La red que
faltaba para animarse a lotes grandes ya está puesta.

**Verificación previa al cambio** (dry-run, sin tocar la API):

- 80 lotes totales, **45 pendientes**.
- El frente `2026-07-01..2026-09-13` encabeza la grilla; `missing_span` lo recorta a los 8 días
  que faltan.
- Los trimestres ya bajados (`2026-04-01..2026-06-30` y anteriores) se detectan **completos**:
  cambiar el tamaño de lote **no re-pide nada**, porque la grilla está alineada al calendario
  (Decisión 044) y cada lote se recorta a los días faltantes.

**Efecto esperado.** 45 lotes × 11,6 h = **22 días** en vez de 63. Si la cola creciera
proporcionalmente al tamaño del request —lo que no se puede saber sin medirlo— el piso sería
igual ~32 días, la mitad del camino anterior. Hay que **volver a medir** el ritmo con unos pocos
trimestres antes de dar el número por bueno.

**Reversión.** Poner `BATCH_MONTHS = 1`. No hay migración ni re-descarga de por medio.

**Alcance.** Solo `pf`. `cf` ya está completo y queda en 12.

## Decisión 052: el archivado a `D:` se dispara solo después de cada sync, y no bloquea la descarga

**Problema.** No había **nada** que moviera archivos de `C:` a `D:`. `sync_to_databricks.py` solo
sube —ni una línea de `unlink`, `move` o `rename`—, no existe ninguna tarea programada de
archivado, y `ARCHIVE_DIRS` en `common_ecmwf.py` se usa **solo para leer** (`already_landed()`
mira ahí para no re-pedir un día ya archivado). La migración `W:` → `D:` de 2.861 archivos fue
manual y de una sola vez.

O sea que `C:` acumulaba sin drenar. Al 2026-09-15: **123 GB de JSON de pf** (462 archivos) con
296 GB libres. Con lotes mensuales (~9 GB) tardaba en notarse; con los trimestrales de la
Decisión 051 son **~26 GB de golpe**, o sea **~11 lotes de los 45 pendientes** hasta repetir el
`No space left on device` de la Decisión 042. El cambio a trimestres aceleró el problema 3×.

**Decisión.** Un comando `catalogo.py archivar [--fuente X] [--dry-run]`, disparado
automáticamente después de cada sync desde `run_tigge_backfill.py`.

**El orden de los pasos es lo que hace la operación segura ante una interrupción:**

1. **Confirmar el destino** — se copia a `.tmp` y se verifica que el tamaño en destino coincida
   con el origen. Recién ahí el archivo existe completo de los dos lados.
2. **Asentar en el registro** — se actualiza `ubicacion` en el catálogo y se hace commit.
3. **Mover** — recién entonces se borra el origen.

Cortarse entre 2 y 3 deja el archivo duplicado, que es inofensivo y lo corrige el próximo
`escanear`. Cortarse antes de 2 deja un `.tmp`, que se limpia al arrancar. En ningún punto
intermedio se pierde el dato — y además está en el volumen, que es la precondición para siquiera
considerar el archivo.

**Dos guardas que no son opcionales:**

- **Solo se mueve lo que el catálogo confirma en el volumen con `bytes_volumen = bytes`.** Si no
  coinciden es una subida truncada (el chequeo `TRUNCADOS` del reporte) y borrar el local sería
  destruir la única copia buena.
- **Se re-consulta el tamaño real en disco antes de tocar el archivo.** El descargador puede
  estar escribiéndolo justo en ese momento; si el tamaño real no es el que registró el catálogo,
  se saltea.

**No bloquea.** El archivado se lanza *detached* (`subprocess.Popen` sin `wait`) y el backfill
sigue con el lote siguiente de inmediato. Mover ~26 GB a un disco externo por USB tarda, y lo
único que el backfill necesita del archivado es que *eventualmente* libere espacio, no que ya lo
haya liberado. Tampoco hace falta sincronizar los disparos: `archivar` tiene su propio lock por
PID, así que un segundo disparo mientras el primero corre sale sin hacer nada en vez de pisarlo.

Que el archivado falle **nunca** puede cortar una descarga en curso: el `Popen` va envuelto en
`try/except` y el error se imprime, no se propaga.

**Ejecución manual inicial** (2026-09-16): 502 archivos, **133,8 GB**, 0 salteados en el
`--dry-run` previo. Los 502 estaban confirmados en el volumen con tamaño byte a byte idéntico.

