# Definición del dataset de tesis

## 1. Objetivo predictivo

El objetivo del dataset es construir una base diaria para entrenar modelos de aprendizaje automático orientados a predecir el nivel del río Uruguay en los próximos 1 a 14 días.

La predicción se enfocará inicialmente en dos puntos críticos:

1. Zona de frontera Brasil/Argentina.
2. Zona aguas abajo asociada a la represa de Salto Grande.

Este dataset será utilizado como insumo principal para el desarrollo experimental de la tesis de maestría.

## 2. Variable objetivo

La variable objetivo será el nivel futuro del río en los puntos críticos seleccionados.

Se consideran inicialmente los siguientes horizontes de predicción:

* Nivel del río a 1 día.
* Nivel del río a 3 días.
* Nivel del río a 7 días.
* Nivel del río a 14 días.

Las variables objetivo candidatas podrían nombrarse como:

`nivel_rio_t_mas_1d`

`nivel_rio_t_mas_3d`

`nivel_rio_t_mas_7d`

`nivel_rio_t_mas_14d`

La definición final dependerá de la disponibilidad, calidad y continuidad de los datos históricos.

## 3. Granularidad

La granularidad objetivo del dataset será diaria.

Cada fila del dataset representará una fecha y un punto de predicción.

La clave lógica esperada será:

`fecha + punto_prediccion`

Ejemplo:

| fecha      | punto_prediccion          | nivel_rio_actual | nivel_rio_t_mas_1d |
| ---------- | ------------------------- | ---------------: | -----------------: |
| 2024-01-01 | frontera_brasil_argentina |             8.35 |               8.42 |
| 2024-01-01 | salto_grande_aguas_abajo  |             7.10 |               7.18 |

## 4. Fuentes de datos

Las fuentes candidatas para construir el dataset son:

* Registros de niveles del río en Brasil.
* Registros de niveles del río en Argentina.
* Registros de lluvias en Brasil.
* Registros de lluvias en Argentina.
* Registros de temperatura en grandes ciudades.
* Registros de temperatura en aeropuertos.
* Pronósticos de precipitación.
* Pronósticos de temperatura.
* Registros o estimaciones de evaporación.

La versión inicial del dataset debería incorporar la mayor cantidad posible de estas fuentes, siempre que puedan integrarse con granularidad diaria y con un proceso reproducible.

## 5. Features candidatas

Las variables predictoras se construirán a partir de las fuentes disponibles.

### 5.1. Niveles del río

* Nivel actual del río.
* Niveles rezagados.
* Variación diaria del nivel.
* Promedios móviles.
* Máximos y mínimos móviles.
* Tendencias de corto y mediano plazo.

Ejemplos de variables:

`nivel_rio_t`

`nivel_rio_lag_1d`

`nivel_rio_lag_3d`

`nivel_rio_lag_7d`

`nivel_rio_media_3d`

`nivel_rio_media_7d`

`nivel_rio_delta_1d`

### 5.2. Lluvias

* Lluvia diaria.
* Lluvia acumulada en ventanas temporales.
* Lluvia promedio por región.
* Lluvia máxima por región.
* Lluvia acumulada aguas arriba.

Ejemplos de variables:

`lluvia_dia`

`lluvia_acum_3d`

`lluvia_acum_7d`

`lluvia_acum_14d`

`lluvia_max_region_7d`

### 5.3. Temperatura

* Temperatura media diaria.
* Temperatura mínima diaria.
* Temperatura máxima diaria.
* Promedios móviles de temperatura.
* Diferencias de temperatura entre regiones.

Ejemplos de variables:

`temp_media_dia`

`temp_min_dia`

`temp_max_dia`

`temp_media_7d`

### 5.4. Pronósticos

* Precipitación pronosticada.
* Temperatura pronosticada.
* Agregaciones espaciales sobre grillas de pronóstico.
* Acumulados pronosticados para distintos horizontes.

Ejemplos de variables:

`precip_pronostico_1d`

`precip_pronostico_3d`

`precip_pronostico_7d`

`temp_pronostico_1d`

### 5.5. Evaporación

* Evaporación diaria.
* Promedios móviles de evaporación.
* Evaporación acumulada.

Ejemplos de variables:

`evaporacion_dia`

`evaporacion_media_7d`

`evaporacion_acum_14d`

## 6. Criterios de inclusión

Una fuente podrá incorporarse al dataset si cumple con los siguientes criterios:

* Puede alinearse a granularidad diaria.
* Tiene relación hidrológica o meteorológica con los puntos de predicción.
* Presenta suficiente cobertura histórica.
* Tiene un proceso de extracción y transformación reproducible.
* Puede integrarse al flujo Bronze, Silver y Gold del proyecto.
* Permite documentar claramente su origen, frecuencia, campos y limitaciones.

Para datos de pronóstico en grilla, se considera inicialmente una resolución espacial de referencia de 0,25° x 0,25°.

## 7. Criterios de exclusión o postergación

Una fuente podrá excluirse o postergarse si:

* No puede alinearse razonablemente a granularidad diaria.
* Tiene una cobertura histórica insuficiente para el objetivo inicial.
* Presenta demasiados faltantes o inconsistencias.
* Su extracción histórica es demasiado lenta o costosa para la primera versión.
* No puede asociarse de forma clara con los puntos críticos definidos.
* Introduce riesgo de fuga de información respecto de la variable objetivo.
* No puede reproducirse o documentarse adecuadamente.

## 8. Período histórico esperado

El objetivo es contar con un período histórico mínimo de 25 años.

Si existen fuentes con mayor cobertura histórica y calidad suficiente, podrán incorporarse para ampliar la base de entrenamiento.

Se reconoce como limitación inicial que los datos más antiguos pueden tener menor disponibilidad, menor granularidad espacial o menor cantidad de fuentes asociadas.

## 9. Limitaciones conocidas

Las principales limitaciones iniciales son:

* Los registros más antiguos pueden tener menos fuentes disponibles.
* La granularidad espacial puede variar entre fuentes.
* Los datos históricos de pronóstico anteriores a los últimos 6 meses pueden ser lentos o difíciles de obtener.
* Algunas fuentes pueden tener frecuencia subdiaria y requerir agregación diaria.
* Algunas fuentes pueden tener faltantes, duplicados o cambios de formato.
* Puede existir diferencia de cobertura entre fuentes de Brasil y Argentina.
* La asociación espacial entre estaciones, ciudades, aeropuertos, grillas y puntos de predicción requiere criterios explícitos.

## 10. Versión inicial del dataset

La primera versión del dataset se denominará:

`training_dataset_v0`

Esta versión deberá priorizar la construcción de una tabla entrenable, estable y reproducible.

No se exigirá que la primera versión resuelva completamente la incrementalidad diaria ni que incorpore todas las fuentes posibles.

El objetivo de esta versión es permitir:

* Entrenar modelos iniciales.
* Evaluar la viabilidad predictiva.
* Analizar calidad y cobertura de datos.
* Detectar fuentes de mayor valor.
* Identificar problemas de datos antes de ampliar el pipeline.

## 11. Salida esperada

La salida esperada será una tabla Gold con granularidad diaria.

Nombre candidato:

`gold.training_dataset_v0`

Grano esperado:

`fecha + punto_prediccion`

Estructura conceptual:

| fecha      | punto_prediccion          | features_hidrologicas | features_meteorologicas | features_pronostico | target |
| ---------- | ------------------------- | --------------------- | ----------------------- | ------------------- | ------ |
| 2024-01-01 | frontera_brasil_argentina | ...                   | ...                     | ...                 | ...    |
| 2024-01-01 | salto_grande_aguas_abajo  | ...                   | ...                     | ...                 | ...    |

## 12. Decisiones pendientes

Quedan pendientes las siguientes decisiones:

* Definir los nombres exactos de los dos puntos críticos de predicción.
* Definir si se entrenará un modelo único para todos los puntos o un modelo por punto.
* Confirmar los horizontes finales de predicción.
* Definir si los horizontes serán 1, 3, 7 y 14 días, o todos los días entre 1 y 14.
* Definir cómo se agregarán espacialmente las variables de lluvia y temperatura.
* Definir cómo se utilizarán las grillas de pronóstico de 0,25° x 0,25°.
* Definir si los datos de pronóstico se usarán para entrenamiento histórico o solo para predicción incremental reciente.
* Definir reglas de imputación de datos faltantes.
* Definir métricas mínimas de calidad del dataset.
* Definir convenciones finales de nombres para tablas, columnas y notebooks.
