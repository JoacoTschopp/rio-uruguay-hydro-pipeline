# Roadmap del dataset de tesis

## 1. Objetivo del roadmap

Este documento define una hoja de ruta para avanzar desde el pipeline actual de ingesta y capa Bronze hacia un dataset Gold entrenable para la tesis.

El propósito es evitar dispersión técnica y priorizar entregables concretos.

El objetivo principal es construir una primera versión reproducible del dataset:

`gold.training_dataset_v0`

Luego, sobre esa base, se podrá extender el pipeline para actualización incremental diaria y nuevas fuentes.

## 2. Principio de trabajo

El proyecto tiene dos objetivos relacionados, pero no deben resolverse al mismo tiempo desde el inicio.

### Objetivo 1: Dataset de entrenamiento para tesis

Prioridad inicial.

Busca construir una tabla estable, reproducible y documentada para:

* entrenar modelos;
* evaluar desempeño predictivo;
* analizar calidad de datos;
* escribir resultados de tesis;
* detectar las fuentes más relevantes.

### Objetivo 2: Dataset incremental diario

Prioridad posterior.

Busca mantener la actualización diaria del dataset y permitir incorporar nuevas fuentes en el tiempo.

Este objetivo se abordará después de validar la estructura inicial del dataset de entrenamiento.

## 3. Fases de trabajo

## Fase 1: Definición del dataset

### Objetivo

Definir el contrato inicial del dataset de tesis.

### Entregables

* `docs/dataset_definition.md`
* Definición de variable objetivo.
* Definición de granularidad.
* Definición de puntos críticos de predicción.
* Definición de fuentes candidatas.
* Definición de criterios de inclusión y exclusión.

### Resultado esperado

Una descripción clara del dataset que se quiere construir.

### Estado

`En progreso`

---

## Fase 2: Inventario del pipeline actual

### Objetivo

Relevar el estado actual del pipeline implementado en Databricks.

### Entregables

* `docs/current_pipeline_inventory.md`
* Listado de jobs existentes.
* Listado de notebooks utilizados.
* Identificación de capas existentes.
* Identificación de tablas, rutas y fuentes disponibles.
* Brechas entre Bronze, Silver, Gold y dataset final.

### Resultado esperado

Un inventario mínimo que permita saber qué ya existe y qué falta construir.

### Estado

`En progreso`

---

## Fase 3: Auditoría de fuentes disponibles

### Objetivo

Medir la cobertura, calidad y utilidad de las fuentes disponibles.

### Entregables

* Resumen de tablas actuales.
* Cantidad de registros por fuente.
* Fecha mínima y máxima por fuente.
* Cantidad de estaciones o puntos geográficos.
* Porcentaje de faltantes.
* Duplicados por clave lógica.
* Frecuencia temporal observada.
* Campos disponibles por fuente.

### Resultado esperado

Una matriz de fuentes que permita decidir qué entra en `training_dataset_v0`.

### Estado

`Pendiente`

### Tabla candidata de auditoría

| Fuente                     | Capa          | Tabla/Ruta | Desde     | Hasta     | Registros | Frecuencia       | Calidad   | Uso inicial     |
| -------------------------- | ------------- | ---------- | --------- | --------- | --------- | ---------------- | --------- | --------------- |
| ANA estaciones             | Bronze        | Pendiente  | Pendiente | Pendiente | Pendiente | Diaria           | Pendiente | Referencia      |
| ANA niveles                | Bronze        | Pendiente  | Pendiente | Pendiente | Pendiente | Diaria/subdiaria | Pendiente | Target/features |
| Temperatura aeropuertos    | Bronze        | Pendiente  | Pendiente | Pendiente | Pendiente | Diaria           | Pendiente | Features        |
| Lluvias                    | Bronze/Silver | Pendiente  | Pendiente | Pendiente | Pendiente | Diaria           | Pendiente | Features        |
| Pronóstico precipitación | Pendiente     | Pendiente  | Pendiente | Pendiente | Pendiente | Diaria/grilla    | Pendiente | Features        |
| Evaporación               | Pendiente     | Pendiente  | Pendiente | Pendiente | Pendiente | Diaria           | Pendiente | Features        |

---

## Fase 4: Construcción de capa Silver

### Objetivo

Normalizar las fuentes disponibles en tablas limpias, tipadas y alineadas a granularidad diaria.

### Entregables

Tablas Silver candidatas:

* `silver.river_levels_daily`
* `silver.rainfall_daily`
* `silver.temperature_daily`
* `silver.forecast_precipitation_daily`
* `silver.forecast_temperature_daily`
* `silver.evaporation_daily`

### Reglas mínimas

Cada tabla Silver debería resolver:

* normalización de fechas;
* tipado de columnas;
* deduplicación;
* estandarización de nombres;
* agregación diaria si la fuente es subdiaria;
* preservación de metadatos de origen;
* control básico de valores faltantes;
* clave lógica documentada.

### Resultado esperado

Fuentes principales listas para ser integradas en una tabla Gold.

### Estado

`Pendiente`

---

## Fase 5: Construcción de dataset Gold v0

### Objetivo

Construir la primera versión entrenable del dataset de tesis.

### Entregable principal

`gold.training_dataset_v0`

### Grano esperado

`fecha + punto_prediccion`

### Contenido mínimo esperado

* nivel actual del río;
* niveles rezagados;
* variaciones de nivel;
* promedios móviles;
* variables de temperatura;
* variables de lluvia si ya están disponibles;
* target futuro para horizontes definidos.

### Horizontes candidatos

* 1 día;
* 3 días;
* 7 días;
* 14 días.

También se evaluará si conviene construir todos los horizontes entre 1 y 14 días.

### Resultado esperado

Una tabla entrenable y reproducible para iniciar experimentos de modelado.

### Estado

`Pendiente`

---

## Fase 6: Validación del dataset

### Objetivo

Verificar que `training_dataset_v0` tenga calidad suficiente para iniciar entrenamiento.

### Entregables

* Reporte de calidad del dataset.
* Conteo de registros.
* Rango temporal total.
* Cobertura por punto de predicción.
* Porcentaje de faltantes por columna.
* Revisión de duplicados.
* Revisión de discontinuidades temporales.
* Revisión de fuga de información.
* Diccionario preliminar de columnas.

### Resultado esperado

Confirmar si el dataset es apto para modelado inicial o si requiere correcciones.

### Estado

`Pendiente`

---

## Fase 7: Baseline de modelado

### Objetivo

Entrenar modelos iniciales simples para validar que el dataset tiene señal predictiva.

### Modelos candidatos

* Baseline naive temporal.
* Regresión lineal.
* Random Forest.
* LightGBM.

### Métricas candidatas

* MAE.
* RMSE.
* MAPE, si los valores del target lo permiten.
* Error por horizonte.
* Error por punto de predicción.

### Resultado esperado

Primeros resultados cuantitativos para orientar la tesis.

### Estado

`Pendiente`

---

## Fase 8: Incrementalidad diaria

### Objetivo

Extender el pipeline para actualizar diariamente las capas necesarias y mantener el dataset Gold.

### Flujo esperado

`Landing diaria -> Bronze -> Silver incremental -> Gold incremental`

### Entregables

* Jobs diarios revisados.
* Actualización incremental de tablas Silver.
* Actualización incremental de `gold.training_dataset`.
* Validaciones automáticas básicas.
* Registro de errores o faltantes por corrida.
* Estrategia de reprocesamiento.

### Resultado esperado

Un pipeline capaz de mantener continuidad diaria en el tiempo.

### Estado

`Pendiente`

---

## 4. Priorización inicial

La prioridad inmediata es avanzar en este orden:

1. Cerrar definición del dataset.
2. Completar inventario del pipeline actual.
3. Auditar fuentes disponibles.
4. Construir Silver mínimo para niveles y temperatura.
5. Construir `gold.training_dataset_v0`.
6. Validar calidad.
7. Entrenar baseline.
8. Recién después profundizar incrementalidad y nuevas fuentes.

## 5. Criterio de avance

Una fase se considera avanzada si produce un entregable concreto versionado en el repositorio o una tabla trazable en Databricks.

No se considera avance suficiente:

* probar notebooks sin salida documentada;
* agregar fuentes sin integrarlas;
* modificar código sin registrar decisiones;
* generar tablas sin validar su granularidad;
* automatizar jobs antes de definir el dataset final.

## 6. Riesgos principales

| Riesgo                                                 | Impacto                              | Mitigación                                                   |
| ------------------------------------------------------ | ------------------------------------ | ------------------------------------------------------------- |
| Intentar incorporar demasiadas fuentes desde el inicio | Retrasa el dataset v0                | Priorizar fuentes ya disponibles                              |
| Enfocarse demasiado en infraestructura                 | Demora resultados de tesis           | Mantener Databricks como entorno principal                    |
| No definir bien el target                              | Impide entrenar modelos consistentes | Cerrar variable objetivo e horizontes                         |
| Datos antiguos con baja cobertura                      | Reduce período entrenable           | Documentar cobertura por fuente                               |
| Pronósticos históricos difíciles de obtener         | Puede bloquear features de forecast  | Postergar o separar dataset histórico de dataset incremental |
| Falta de documentación                                | Dificulta continuidad                | Registrar decisiones y estado del pipeline                    |

## 7. Definición de éxito inicial

La primera meta exitosa del proyecto será contar con:

`gold.training_dataset_v0`

con:

* al menos 25 años de histórico si la disponibilidad lo permite;
* granularidad diaria;
* dos puntos críticos de predicción;
* target futuro para uno o más horizontes;
* features hidrológicas básicas;
* features meteorológicas iniciales;
* proceso reproducible;
* documentación mínima asociada.

## 8. Próximo paso operativo

El próximo paso operativo después de este roadmap es completar la auditoría de fuentes disponibles.

Para eso se necesita relevar:

* tablas existentes;
* rutas de datos;
* esquemas;
* mínimos y máximos de fecha;
* cantidad de registros;
* cantidad de estaciones;
* faltantes;
* duplicados;
* frecuencia temporal real.
