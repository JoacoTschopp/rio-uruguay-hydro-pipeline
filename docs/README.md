# Índice de documentación

Documentación del proyecto **Río Uruguay – Hydro Pipeline** (tesis de Maestría en Ciencia de Datos).

La documentación tiene tres funciones separadas, y cada archivo cumple una sola:

| Función | Archivos |
| --- | --- |
| **Qué queremos construir y cómo seguimos** | `roadmap.md` (dataset), `rio_search_plan.md` (modelado: app Rio_Search, research, tesis) |
| **Cómo se ejecuta la búsqueda de modelos** | `protocolo_busqueda_modelos.md` + `../rio_search/experiments/matrix.yaml` |
| **Qué métrica se optimiza y de dónde sale** | `funcion_ganancia_regimen.html` (especificación de G-RAL) |
| **Bibliografía de la tesis** | `../research/` — catálogo, notas y `references.bib` generado |
| **Por qué se eligió cada enfoque** | `decisions.md` |
| **Qué existe hoy** | `dataset_definition.md`, `data_sources.md`, `current_pipeline_inventory.md`, `silver_gold_implementation_status.md` |

Los planes intermedios anteriores (`thesis_dataset_roadmap.md`, `rating_curve_discharge_plan.md`,
`silver_gold_jobs_plan.md`, `sg_rainfall_ingestion_plan.md`) fueron retirados: lo que tenían de conocimiento
consolidado quedó absorbido en `decisions.md` y en los documentos de estado.

## Orden de lectura recomendado

1. `roadmap.md` — alcance de la tesis, estado al corte y las 8 fases pendientes con su criterio de cierre.
2. `dataset_definition.md` — qué dataset queremos construir: target, granularidad, features candidatas.
3. `data_sources.md` — catálogo de fuentes ingestadas y candidatas: APIs, rutas, tablas Bronze, frecuencias, estado.
4. `current_pipeline_inventory.md` — qué hay hoy en Databricks: notebooks, jobs, capas, brechas.
5. `silver_gold_implementation_status.md` — estado real desplegado de jobs, tablas y validaciones Silver/Gold.
6. `decisions.md` — log de decisiones técnicas y metodológicas (ADR-style), Decisiones 001–045. Sin decisiones abiertas al 2026-09-05.
7. `rio_search_plan.md` — plan de implementación de **Rio_Search** (Decisión 038): arquitectura Onion + DDD, MLflow en Databricks, BiLSTM baseline, UI React, `research/` y `thesis/`, 10 fases con criterio de cierre.
8. `funcion_ganancia_regimen.html` — especificación de **G-RAL**, la función de ganancia por régimen: qué es, cómo funciona el modulador que produce τ, qué parámetros se pueden mover, las decisiones tomadas con sus consecuencias, y el fundamento bibliográfico (§09).
9. `protocolo_busqueda_modelos.md` — procedimiento normativo para **ejecutar** la búsqueda de modelos: reglas invariantes, ciclo de 7 fases, cómo se lee un resultado, cuándo se para y qué se re-corre cuando cambia el dataset. Su catálogo de combinaciones es `rio_search/experiments/matrix.yaml`.

## Mapa rápido

| Documento | Pregunta que responde |
| --- | --- |
| `roadmap.md` | ¿Cuál es el alcance del dataset y qué hago próximo, en qué orden? |
| `rio_search_plan.md` | ¿Cómo se construye la app de modelado (Rio_Search), la biblioteca de research y la tesis, y en qué orden? |
| `dataset_definition.md` | ¿Qué quiero predecir y con qué grano? |
| `data_sources.md` | ¿De dónde vienen los datos y qué tablas existen? |
| `current_pipeline_inventory.md` | ¿Qué procesos corren hoy y qué falta? |
| `silver_gold_implementation_status.md` | ¿Qué quedó desplegado y validado en Databricks? |
| `protocolo_busqueda_modelos.md` | ¿Cómo corre un agente la búsqueda, cómo lee cada resultado y cuándo la da por cerrada? |
| `decisions.md` | ¿Por qué se eligió cada enfoque? |
| `funcion_ganancia_regimen.html` | ¿Qué métrica se optimiza, cómo funciona y de dónde sale? |
| `../research/` | ¿Qué papers sostienen cada decisión metodológica? |
| `dataset_caudal_report.html` | Informe visual del estado del dataset (se actualiza al concluir el roadmap) |

## Estado actual del pipeline

* **Alcance de la tesis**: sub-cuenca `alta_frontera` (cuenca alta) únicamente — Decisión 018. La ingesta sigue cubriendo toda la cuenca.
* **Landing + Bronze**: operativo para ANA (nivel/lluvia), METAR aeropuertos, Salto Grande y ECMWF.
* **Silver**: niveles, temperatura, lluvia, ECMWF y caudal diario materializados. Lluvia y temperatura quedan excluidas de Gold v0 por un portón de calidad que se reemplaza en la Fase 3 del roadmap (Decisión 019, enmienda · R8).
* **Gold**: `weather.gold.training_dataset_v0` implementado y validado para `ana_74100000`, sin duplicados ni mismatches de target. Arranca en 2000-01-01 (Decisión 019, enmienda); la serie de nivel desde 1941 queda en `weather.silver.river_levels_daily`.
* **Caudal**: conversión nivel → caudal por curva de aforo vigente, 210.106 filas para las 22 estaciones de la cuenca alta.
* **Descargas largas**: backfill histórico de ANA y barrido de curvas de aforo de toda la cuenca, ambos **completos**.

## Próximo entregable

* Dataset (`roadmap.md`): Fase 4 (pronóstico TIGGE + GEFS) y Fase 5 (cadena diaria), en curso.
* Modelado (`rio_search_plan.md`): Fase 0 — cimientos de Rio_Search (entorno `uv`, snapshot de Gold con 83 columnas, run `smoke` en MLflow).

## Convenciones

* Catálogo Unity: `weather`.
* Schemas: `raw`, `bronze`, `silver`, `gold`.
* Volumes: `/Volumes/weather/raw/ana_volume/` y `/Volumes/weather/raw/noaa_volume/`.
* Notebooks numerados por capa: `00_Landing/`, `01_DDL/`, `02_Bronze/`, `03_EDA/`, `04_Silver/`, `05_Gold/`, `06_Quality/`.
* Toda decisión técnica se registra en `decisions.md` antes o junto con el código que la implementa.
