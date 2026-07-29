# Plan de jobs Silver/Gold

## Objetivo

Este documento define la implementacion de la capa Silver y la primera tabla Gold entrenable a partir de las tablas Bronze existentes.

No se modifican notebooks actuales de `00_Landing`, `01_DDL`, `02_Bronze` ni `03_EDA`. Los jobs Bronze que funcionan hoy siguen siendo la fuente de verdad para alimentar Bronze.

La ejecucion real en Databricks fue realizada el 2026-05-09 usando el MCP local de Databricks. El estado desplegado se documenta en `docs/silver_gold_implementation_status.md`.

## Decisiones confirmadas

| Decision | Valor |
| --- | --- |
| Catalogo Unity | `weather` |
| Schemas | `silver`, `gold` |
| Target v0 | `codigoestacao = '74100000'` |
| Punto de prediccion Gold | `ana_74100000` |
| Regla de faltantes | Global por fuente/atributo |
| Umbral de descarte | `missing_pct > 0.90` |
| Ejecucion Databricks | Ejecutado con MCP local el 2026-05-09 |

## Inventario Bronze usado

| Fuente | Tabla Bronze | Uso |
| --- | --- | --- |
| ANA niveles | `weather.bronze.nivel_ana` | Target y features hidrologicas |
| METAR aeropuertos | `weather.bronze.metar` | Temperatura diaria |
| ANA lluvia | `weather.bronze.ana_rio_uruguai` | Lluvia diaria solo si pasa calidad |

La EDA existente indica que lluvia tiene aproximadamente `99.78%` de dias faltantes a nivel global. Por eso la tabla Silver puede quedar sin carga publicada y Gold debe dejar la feature de lluvia en `NULL` mientras `attribute_quality.is_usable = false`.

## Notebooks nuevos

| Notebook | Funcion |
| --- | --- |
| `notebooks/04_Silver/DDL_Silver_Gold.ipynb` | Crea schemas y tablas Delta Silver/Gold |
| `notebooks/04_Silver/ETL_Silver_Level_Daily.ipynb` | Agrega nivel ANA diario para `74100000` |
| `notebooks/04_Silver/ETL_Silver_Temperature_Daily.ipynb` | Agrega temperatura diaria por aeropuerto |
| `notebooks/04_Silver/ETL_Silver_Rainfall_Daily.ipynb` | Evalua calidad y publica lluvia diaria solo si pasa umbral |
| `notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb` | Construye `training_dataset_v0` |
| `notebooks/06_Quality/Check_Bronze_Freshness.ipynb` | Falla temprano si Bronze no esta fresco |
| `notebooks/06_Quality/Validate_Training_Dataset_v0.ipynb` | Valida unicidad, calidad y targets |

## DDL

```sql
CREATE CATALOG IF NOT EXISTS weather;
CREATE SCHEMA IF NOT EXISTS weather.silver;
CREATE SCHEMA IF NOT EXISTS weather.gold;

CREATE TABLE IF NOT EXISTS weather.silver.attribute_quality (
  source_layer STRING,
  source_table STRING,
  source_name STRING,
  attribute_name STRING,
  grain STRING,
  evaluation_start_date DATE,
  evaluation_end_date DATE,
  expected_days BIGINT,
  observed_days BIGINT,
  missing_days BIGINT,
  missing_pct DOUBLE,
  threshold_pct DOUBLE,
  is_usable BOOLEAN,
  evaluated_at TIMESTAMP,
  notes STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
USING DELTA;

CREATE TABLE IF NOT EXISTS weather.silver.river_levels_daily (
  fecha DATE,
  codigoestacao STRING,
  nivel_media_cm DOUBLE,
  nivel_media_m DOUBLE,
  registros_total BIGINT,
  registros_validos BIGINT,
  first_medicao_ts TIMESTAMP,
  last_medicao_ts TIMESTAMP,
  source_table STRING,
  processed_at TIMESTAMP,
  updated_at TIMESTAMP
)
USING DELTA;

CREATE TABLE IF NOT EXISTS weather.silver.temperature_daily (
  fecha DATE,
  icao_id STRING,
  temp_media_c DOUBLE,
  temp_min_c DOUBLE,
  temp_max_c DOUBLE,
  registros_total BIGINT,
  registros_validos BIGINT,
  first_obs_ts TIMESTAMP,
  last_obs_ts TIMESTAMP,
  source_table STRING,
  processed_at TIMESTAMP,
  updated_at TIMESTAMP
)
USING DELTA;

CREATE TABLE IF NOT EXISTS weather.silver.rainfall_daily (
  fecha DATE,
  codigoestacao STRING,
  lluvia_acumulada_mm DOUBLE,
  registros_total BIGINT,
  registros_validos BIGINT,
  first_medicao_ts TIMESTAMP,
  last_medicao_ts TIMESTAMP,
  source_table STRING,
  processed_at TIMESTAMP,
  updated_at TIMESTAMP
)
USING DELTA;

CREATE TABLE IF NOT EXISTS weather.gold.training_dataset_v0 (
  fecha DATE,
  punto_prediccion STRING,
  codigoestacao STRING,
  nivel_rio_actual_cm DOUBLE,
  nivel_rio_actual_m DOUBLE,
  nivel_registros_validos BIGINT,
  temp_media_c DOUBLE,
  temp_min_c DOUBLE,
  temp_max_c DOUBLE,
  temp_station_count BIGINT,
  lluvia_acumulada_mm DOUBLE,
  lluvia_is_usable BOOLEAN,
  nivel_rio_lag_1d DOUBLE,
  nivel_rio_lag_3d DOUBLE,
  nivel_rio_lag_7d DOUBLE,
  nivel_rio_media_3d DOUBLE,
  nivel_rio_media_7d DOUBLE,
  nivel_rio_delta_1d DOUBLE,
  nivel_rio_t_mas_1d DOUBLE,
  nivel_rio_t_mas_3d DOUBLE,
  nivel_rio_t_mas_7d DOUBLE,
  nivel_rio_t_mas_14d DOUBLE,
  feature_generated_at TIMESTAMP,
  updated_at TIMESTAMP
)
USING DELTA;
```

## Regla global de faltantes

Para cada atributo publicable:

```text
expected_days = datediff(max(fecha), min(fecha)) + 1
observed_days = count(distinct fecha con valor valido)
missing_days = expected_days - observed_days
missing_pct = missing_days / expected_days
is_usable = missing_pct <= 0.90
```

Los resultados se guardan en `weather.silver.attribute_quality` por `source_table + attribute_name + grain`.

## Jobs Databricks

### `Silver_Gold_Initial_Load_v0`

1. `DDL_Silver_Gold`
2. `ETL_Silver_Level_Daily` con `load_mode = full`
3. `ETL_Silver_Temperature_Daily` con `load_mode = full`
4. `ETL_Silver_Rainfall_Daily` con `load_mode = full`
5. `ETL_Gold_Training_Dataset_v0` con `load_mode = full`
6. `Validate_Training_Dataset_v0`

### `Silver_Gold_Daily_Incremental`

1. `Check_Bronze_Freshness`
2. `ETL_Silver_Level_Daily` con `load_mode = incremental`
3. `ETL_Silver_Temperature_Daily` con `load_mode = incremental`
4. `ETL_Silver_Rainfall_Daily` con `load_mode = incremental`
5. `ETL_Gold_Training_Dataset_v0` con `load_mode = incremental`
6. `Validate_Training_Dataset_v0`

El job incremental debe agendarse despues de:

- `All_Estacoes_ANA_Daily`
- `Nivel_ANA_Target`
- `Temperature_Airport_Brasil`

## Idempotencia

- DDL usa `CREATE IF NOT EXISTS`.
- Silver usa `MERGE` por clave logica:
  - nivel: `fecha + codigoestacao`;
  - temperatura: `fecha + icao_id`;
  - lluvia: `fecha + codigoestacao`.
- Gold full reemplaza controladamente el punto `ana_74100000`.
- Gold incremental borra y reconstruye solo la ventana afectada:
  - `window_start = changed_min - 14 dias`;
  - `window_end = changed_max + 7 dias`.
- La lluvia no se publica cuando `missing_pct > 0.90`.

## Validaciones minimas

- `DESCRIBE` de todas las tablas Silver/Gold.
- Unicidad de claves logicas.
- `weather.silver.attribute_quality` contiene evaluaciones para nivel, temperatura y lluvia.
- Gold contiene una fila por `fecha + punto_prediccion`.
- `punto_prediccion = 'ana_74100000'`.
- Targets `t+1`, `t+3`, `t+7`, `t+14` coinciden con el nivel futuro correspondiente.
- Si lluvia no es usable, `lluvia_acumulada_mm` debe quedar `NULL` en Gold.

## Orden de ejecucion recomendado

1. Confirmar MCP Databricks disponible.
2. Ejecutar `DDL_Silver_Gold`.
3. Ejecutar `Silver_Gold_Initial_Load_v0`.
4. Revisar salida de `Validate_Training_Dataset_v0`.
5. Crear `Silver_Gold_Daily_Incremental` con schedule posterior a Bronze.
6. Activar alertas del job incremental ante fallas de freshness o validacion.
