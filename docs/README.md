# Índice de documentación

Documentación del proyecto **Río Uruguay – Hydro Pipeline** (tesis de Maestría en Ciencia de Datos).

La documentación tiene tres funciones separadas, y cada archivo cumple una sola:

| Función | Archivos |
| --- | --- |
| **Qué queremos construir y cómo seguimos** | `roadmap.md` |
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
6. `decisions.md` — log de decisiones técnicas y metodológicas (ADR-style), Decisiones 001–022. Sin decisiones abiertas al 2026-08-21.

## Mapa rápido

| Documento | Pregunta que responde |
| --- | --- |
| `roadmap.md` | ¿Cuál es el alcance y qué hago próximo, en qué orden? |
| `dataset_definition.md` | ¿Qué quiero predecir y con qué grano? |
| `data_sources.md` | ¿De dónde vienen los datos y qué tablas existen? |
| `current_pipeline_inventory.md` | ¿Qué procesos corren hoy y qué falta? |
| `silver_gold_implementation_status.md` | ¿Qué quedó desplegado y validado en Databricks? |
| `decisions.md` | ¿Por qué se eligió cada enfoque? |
| `dataset_caudal_report.html` | Informe visual del estado del dataset (se actualiza al concluir el roadmap) |

## Estado actual del pipeline

* **Alcance de la tesis**: sub-cuenca `alta_frontera` (cuenca alta) únicamente — Decisión 018. La ingesta sigue cubriendo toda la cuenca.
* **Landing + Bronze**: operativo para ANA (nivel/lluvia), METAR aeropuertos, Salto Grande y ECMWF.
* **Silver**: niveles, temperatura, lluvia, ECMWF y caudal diario materializados. Lluvia y temperatura quedan excluidas de Gold v0 por un portón de calidad que se reemplaza en la Fase 3 del roadmap (Decisión 019, enmienda · R8).
* **Gold**: `weather.gold.training_dataset_v0` implementado y validado para `ana_74100000`, sin duplicados ni mismatches de target. Arranca en 2000-01-01 (Decisión 019, enmienda); la serie de nivel desde 1941 queda en `weather.silver.river_levels_daily`.
* **Caudal**: conversión nivel → caudal por curva de aforo vigente, 210.106 filas para las 22 estaciones de la cuenca alta.
* **Descargas largas**: backfill histórico de ANA y barrido de curvas de aforo de toda la cuenca, ambos **completos**.

## Próximo entregable

Fase 1 del roadmap: exportador local del dataset Gold (`notebooks_local/gold_export/export_gold_dataset.py`),
que deja el dataset en disco como Parquet con manifiesto de reproducibilidad.

## Convenciones

* Catálogo Unity: `weather`.
* Schemas: `raw`, `bronze`, `silver`, `gold`.
* Volumes: `/Volumes/weather/raw/ana_volume/` y `/Volumes/weather/raw/noaa_volume/`.
* Notebooks numerados por capa: `00_Landing/`, `01_DDL/`, `02_Bronze/`, `03_EDA/`, `04_Silver/`, `05_Gold/`, `06_Quality/`.
* Toda decisión técnica se registra en `decisions.md` antes o junto con el código que la implementa.
