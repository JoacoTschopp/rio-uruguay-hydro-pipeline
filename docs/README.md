# Índice de documentación

Documentación del proyecto **Río Uruguay – Hydro Pipeline** (tesis de Maestría en Ciencia de Datos).

## Orden de lectura recomendado

1. `dataset_definition.md` — qué dataset queremos construir, target, granularidad, features candidatas.
2. `data_sources.md` — catálogo de fuentes ingestadas y candidatas: APIs, rutas, tablas Bronze, frecuencias, estado.
3. `current_pipeline_inventory.md` — qué hay hoy en Databricks: notebooks, jobs, capas, brechas.
4. `thesis_dataset_roadmap.md` — fases para llegar a `gold.training_dataset_v0` y baseline.
5. `decisions.md` — log de decisiones técnicas y metodológicas (ADR-style).

## Mapa rápido

| Documento                       | Pregunta que responde                                  |
| ------------------------------- | ------------------------------------------------------ |
| `dataset_definition.md`         | ¿Qué quiero predecir y con qué grano?                 |
| `data_sources.md`               | ¿De dónde vienen los datos y qué tablas existen?      |
| `current_pipeline_inventory.md` | ¿Qué procesos corren hoy y qué falta?                 |
| `thesis_dataset_roadmap.md`     | ¿Qué hago próximo y en qué orden?                     |
| `decisions.md`                  | ¿Por qué se eligió cada enfoque?                       |

## Estado actual del pipeline

* **Landing + Bronze**: operativo para 3 fuentes (ANA estaciones, ANA niveles, METAR aeropuertos).
* **EDA Bronze**: realizado (cobertura, faltantes, duplicados, outliers, frecuencia real).
* **Silver**: no implementado.
* **Gold**: no implementado.
* **Jobs Databricks**: 3 jobs serverless diarios.

## Próximo entregable

`gold.training_dataset_v0` — primera versión entrenable. Ver fases en `thesis_dataset_roadmap.md`.

## Convenciones

* Catálogo Unity: `weather`.
* Schemas: `raw`, `bronze`, `silver`, `gold`.
* Volumes: `/Volumes/weather/raw/ana_volume/` y `/Volumes/weather/raw/noaa_volume/`.
* Notebooks numerados por capa: `00_Landing/`, `01_DDL/`, `02_Bronze/`, `03_EDA/`, `04_Silver/` (futuro), `05_Gold/` (futuro).
