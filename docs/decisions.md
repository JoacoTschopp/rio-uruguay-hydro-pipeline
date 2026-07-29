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
