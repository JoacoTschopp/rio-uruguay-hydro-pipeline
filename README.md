📌 Proyecto Final Bootcamp – Pipeline End-to-End
🎯 Objetivo

El objetivo de este proyecto es construir un pipeline de datos end-to-end en Databricks aplicando arquitectura Medallion, modelado dimensional y orquestación mediante Workflows.

Adicionalmente, este proyecto funciona como puntapié inicial para el armado del dataset de mi tesis de Maestría en Ciencia de Datos.

🌎 Problema de Investigación

Se busca analizar la siguiente pregunta:

¿Las temperaturas en grandes ciudades de Brasil influyen en la generación y descarga de agua en el Río Uruguay, generando aumentos en su nivel?

Para ello se integran múltiples fuentes públicas:

Temperaturas históricas de ciudades brasileñas

Niveles y caudales del Río Uruguay aguas abajo de represas

Registros de lluvias en la región

🏗 Arquitectura

El pipeline sigue arquitectura Medallion:

Bronze: datos crudos provenientes de APIs públicas

Silver: limpieza, tipado, validaciones y deduplicación

Gold: modelo dimensional (Star Schema) con:

Dimensiones: tiempo, ubicación, fuente

Tabla de hechos: niveles diarios del río con métricas climáticas asociadas

📊 Modelo Dimensional

Granularidad de la fact table:

Una fila representa el nivel del río en un punto de medición específico en un día determinado.

Métricas principales:

Nivel del río (m)

Caudal (m³/s)

Lluvia (mm)

Temperatura promedio (°C)

⚙ Orquestación

El pipeline está implementado mediante Databricks Workflows:

DDL → Bronze → Silver → Dimensiones → Fact

El proceso es idempotente y scheduleado.

🚀 Próximos pasos (Extensión Tesis)

Incorporación de más estaciones meteorológicas

Series temporales con lags

Modelos predictivos

Análisis de correlación y causalidad
