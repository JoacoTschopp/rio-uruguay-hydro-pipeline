# Inventario actual del pipeline

## 1. Objetivo del documento

Este documento registra el estado actual del pipeline de datos implementado en Databricks para el proyecto de tesis.

El objetivo es dejar documentado qué procesos existen, qué fuentes cubren, qué notebooks intervienen y cuáles son los próximos componentes necesarios para construir el dataset de entrenamiento.

## 2. Estado general

Actualmente existen jobs en Databricks orientados a la ingesta diaria y carga en capa Bronze de algunas fuentes iniciales.

A partir de las capturas revisadas, el patrón general del pipeline es:

`notebook de extracción diaria -> notebook de ETL Bronze`

Este patrón es adecuado como primera etapa para sostener una arquitectura incremental basada en capas.

## 3. Jobs existentes en Databricks

### 3.1. Job: `All_Estacoes_ANA_Daily`

Secuencia observada:

`Daily_ANA -> ETL_Bronze_ANA`

Descripción inicial:

Este job parece estar orientado a la descarga o actualización diaria de datos provenientes de ANA, asociados a estaciones hidrológicas.

Tareas observadas:

| Tarea              | Descripción inicial                                                 | Capa estimada |
| ------------------ | -------------------------------------------------------------------- | ------------- |
| `Daily_ANA`      | Notebook de extracción o landing de datos diarios de estaciones ANA | Landing       |
| `ETL_Bronze_ANA` | Notebook de transformación y carga hacia capa Bronze                | Bronze        |

Modo de ejecución observado:

`Serverless`

Uso esperado dentro del dataset de tesis:

* Inventario de estaciones.
* Datos de referencia para fuentes hidrológicas.
* Posible soporte para selección espacial de estaciones relevantes.

---

### 3.2. Job: `Nivel_ANA_Target`

Secuencia observada:

`Daily_Nivel_ANA -> ETL_Bronze_Nivel_ANA`

Descripción inicial:

Este job parece estar orientado a la descarga o actualización diaria de niveles hidrométricos desde ANA.

Tareas observadas:

| Tarea                    | Descripción inicial                                                    | Capa estimada |
| ------------------------ | ----------------------------------------------------------------------- | ------------- |
| `Daily_Nivel_ANA`      | Notebook de extracción o landing de niveles diarios/hidrométricos ANA | Landing       |
| `ETL_Bronze_Nivel_ANA` | Notebook de transformación y carga de niveles hacia capa Bronze        | Bronze        |

Modo de ejecución observado:

`Serverless`

Uso esperado dentro del dataset de tesis:

* Fuente principal para variables de nivel del río.
* Posible fuente para construir la variable objetivo.
* Base para generar rezagos, diferencias y ventanas móviles.

---

### 3.3. Job: `Temperature_Airport_Brasil`

Secuencia observada:

`Daily_Temp_Aeroport -> ETL_Bronze_Temp_Aeroport`

Descripción inicial:

Este job parece estar orientado a la descarga o actualización diaria de datos de temperatura provenientes de aeropuertos de Brasil.

Tareas observadas:

| Tarea                        | Descripción inicial                                                   | Capa estimada |
| ---------------------------- | ---------------------------------------------------------------------- | ------------- |
| `Daily_Temp_Aeroport`      | Notebook de extracción o landing de temperatura diaria de aeropuertos | Landing       |
| `ETL_Bronze_Temp_Aeroport` | Notebook de transformación y carga hacia capa Bronze                  | Bronze        |

Modo de ejecución observado:

`Serverless`

Uso esperado dentro del dataset de tesis:

* Variables meteorológicas asociadas a temperatura.
* Features agregadas por estación, ciudad o región.
* Soporte para variables explicativas relacionadas con clima.

---

## 4. Patrón actual de procesamiento

El pipeline actual se puede resumir de la siguiente manera:

`Fuente externa -> Landing diario -> Bronze`

Este flujo permite comenzar a mantener datos actualizados diariamente.

Sin embargo, para construir el dataset de entrenamiento de tesis todavía faltan las siguientes capas:

`Bronze -> Silver -> Gold -> Training Dataset`

## 5. Capas requeridas

### 5.1. Landing

La capa Landing almacena datos obtenidos desde las fuentes externas con la menor transformación posible.

Propósito:

* conservar archivos o respuestas originales;
* facilitar reprocesamiento;
* auditar cambios de formato;
* desacoplar descarga de transformación.

### 5.2. Bronze

La capa Bronze organiza los datos crudos en tablas o estructuras iniciales.

Propósito:

* estructurar datos provenientes de Landing;
* preservar la mayor cantidad posible de campos originales;
* agregar metadatos de carga;
* permitir consultas iniciales de calidad y cobertura.

### 5.3. Silver

La capa Silver deberá contener datos limpios, normalizados y alineados temporalmente.

Propósito:

* normalizar fechas;
* resolver tipos de datos;
* deduplicar registros;
* unificar nombres de columnas;
* alinear fuentes a granularidad diaria;
* generar tablas por dominio: niveles, lluvias, temperatura, pronósticos y evaporación.

Tablas candidatas:

`silver.river_levels_daily`

`silver.rainfall_daily`

`silver.temperature_daily`

`silver.forecast_precipitation_daily`

`silver.forecast_temperature_daily`

`silver.evaporation_daily`

### 5.4. Gold

La capa Gold deberá construir datasets analíticos listos para modelado.

Propósito:

* unir fuentes limpias;
* construir variables derivadas;
* generar rezagos y ventanas móviles;
* construir targets;
* consolidar la granularidad `fecha + punto_prediccion`.

Tabla candidata inicial:

`gold.training_dataset_v0`

## 6. Brecha actual

La principal brecha actual no parece estar en la ingesta diaria, sino en la construcción de las capas analíticas posteriores.

Brecha principal:

`Bronze existe parcialmente, pero falta consolidar Silver y Gold para entrenamiento`

En términos prácticos, el próximo avance debería ser construir una primera versión de:

`gold.training_dataset_v0`

a partir de las fuentes ya disponibles.

## 7. Próximos notebooks sugeridos

Para avanzar de manera ordenada, se sugieren los siguientes notebooks o módulos:

`03_Silver/ETL_Silver_ANA_Level`

`03_Silver/ETL_Silver_Temperature_Airport`

`04_Gold/Build_Training_Dataset_v0`

`05_Quality/Validate_Training_Dataset_v0`

La prioridad inicial debería ser:

1. Normalizar niveles del río en una tabla Silver diaria.
2. Normalizar temperatura en una tabla Silver diaria.
3. Definir los puntos de predicción.
4. Construir un primer dataset Gold con target y features básicas.
5. Validar completitud, rango temporal y consistencia.

## 8. Inventario pendiente

Estado actualizado tras la ejecución del EDA Bronze (`notebooks/03_EDA/EDA_in_Bronze.ipynb`) y la redacción del catálogo de fuentes (`docs/data_sources.md`):

| Elemento                           | Estado                                                                 |
| ---------------------------------- | ---------------------------------------------------------------------- |
| Nombres reales de tablas Bronze    | Resuelto: `weather.bronze.ana_rio_uruguai`, `weather.bronze.nivel_ana`, `weather.bronze.metar` |
| Rutas reales de Landing            | Resuelto: ver `data_sources.md` secciones 3.5, 4.5, 5.5                |
| Esquemas de columnas               | Resuelto en EDA (`DESCRIBE` + campos clave en `data_sources.md`)       |
| Fecha mínima y máxima por fuente | Resuelto en EDA (cobertura temporal por tabla y por estación/icaoId) |
| Cantidad de registros por tabla    | Resuelto en EDA                                                        |
| Porcentaje de valores faltantes    | Resuelto parcialmente: faltantes diarios calculados; faltantes por columna pendiente |
| Frecuencia original de cada fuente | Resuelto en EDA (`analizar_frecuencia` por estación)                  |
| Reglas actuales de transformación | Resuelto: dedupe `(codigoestacao, Data_Hora_Medicao)` en Bronze ANA; MERGE Delta; sin tipado en Bronze |
| Dependencias entre notebooks       | Resuelto: ver sección 3 de este documento                              |
| Estado de jobs diarios             | Resuelto: 3 jobs serverless activos                                    |
| Estaciones objetivo confirmadas    | Pendiente: hay candidatas (`2751083`, `2751037`, `2752032`, `2751066`, `2753044`) pero falta cerrar mapeo a `punto_prediccion` (decisión 005) |
| Tipado numérico en Bronze         | Pendiente: `Cota_Adotada`, `Chuva_Adotada` siguen como string con coma decimal — se resuelve en Silver |

## 9. Consultas mínimas sugeridas para auditoría

Para completar este inventario, se deberían ejecutar consultas de auditoría sobre cada tabla Bronze y Silver disponible.

Ejemplo conceptual:

`cantidad de registros`

`fecha mínima`

`fecha máxima`

`cantidad de estaciones`

`cantidad de valores nulos por columna`

`duplicados por clave lógica`

`frecuencia temporal observada`

## 10. Decisión operativa inicial

Se mantiene Databricks como entorno principal de procesamiento.

La prioridad inmediata no es migrar a PostgreSQL ni montar un entorno Spark local completo, sino documentar y consolidar el pipeline existente hasta obtener una primera tabla Gold entrenable.

Decisión:

`Mantener Databricks + documentar pipeline + construir training_dataset_v0`

## 11. Resultado esperado de la próxima etapa

La próxima etapa debería producir:

`gold.training_dataset_v0`

con granularidad:

`fecha + punto_prediccion`

y con al menos:

* niveles actuales del río;
* rezagos de nivel;
* variaciones de nivel;
* temperatura diaria;
* alguna agregación meteorológica inicial;
* targets futuros para 1 a 14 días o para horizontes seleccionados.
