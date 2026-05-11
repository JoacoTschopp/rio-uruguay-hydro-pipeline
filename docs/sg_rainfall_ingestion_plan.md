# Plan de ingesta Salto Grande - Precipitacion

## Objetivo

Incorporar precipitacion diaria de estaciones Salto Grande como fuente independiente, con trazabilidad por archivo Raw, tabla Bronze propia y tabla Silver propia.

## Decisiones

| Decision | Valor |
| --- | --- |
| Fuente | Salto Grande SOAP API |
| Operacion | `HidroSerieHistorica` |
| Variable | `P` precipitacion |
| Ventana recuperable | Ultimos 30 dias disponibles |
| Limite diario | Hasta ayer, no incluye el dia en curso |
| Raw | Un archivo JSON por dia |
| Separacion de fuentes | Tablas SG separadas de ANA |

## Rutas y tablas

| Capa | Recurso |
| --- | --- |
| Inventario estaciones | `/Volumes/weather/raw/sg_volume/sg_estaciones_activas/estaciones_activas.csv` |
| Raw daily | `/Volumes/weather/raw/sg_volume/json/daily/SG_P_YYYY_MM_DD.json` |
| Bronze | `weather.bronze.sg_rainfall` |
| Silver | `weather.silver.sg_rainfall_daily` |
| Calidad | `weather.silver.attribute_quality` |

## Notebooks

| Notebook | Funcion |
| --- | --- |
| `notebooks/01_DDL/DDL_SG_Rainfall.ipynb` | Crea directorio Raw y tablas Delta SG |
| `notebooks/00_Landing/Salto_Grande/Daily_SG_Rainfall.ipynb` | Descarga dias faltantes de la ventana de 30 dias |
| `notebooks/02_Bronze/ETL_Bronze_SG_Rainfall.ipynb` | Carga Raw JSON a Bronze con `MERGE` idempotente |
| `notebooks/04_Silver/ETL_Silver_SG_Rainfall_Daily.ipynb` | Publica precipitacion diaria acumulada por estacion |

## Job

`SG_Rainfall_Daily_Incremental`

1. `DDL_SG_Rainfall`
2. `Daily_SG_Rainfall`
3. `ETL_Bronze_SG_Rainfall`
4. `ETL_Silver_SG_Rainfall_Daily`

Schedule versionado: `03:30` America/Montevideo.

## Idempotencia y recuperacion

La landing calcula las fechas esperadas desde `hoy - 30 dias` hasta `ayer` y solo descarga los archivos faltantes, salvo que `force_reload=true`.

Bronze hace `MERGE` por `fecha + id_estacion`.

Silver hace `MERGE` por `fecha + id_estacion` y publica `lluvia_acumulada_mm` como acumulado diario de `P`.

## Validaciones iniciales realizadas

* MCP Databricks confirmo que existe `/Volumes/weather/raw/sg_volume/sg_estaciones_activas/estaciones_activas.csv`.
* El inventario contiene columnas `Id`, `Nombre`, `Latitud`, `Longitud`, `Fecha`, `Variables`.
* Se crearon en Databricks:
  * `/Volumes/weather/raw/sg_volume/json/daily/`
  * `weather.bronze.sg_rainfall`
  * `weather.silver.sg_rainfall_daily`
* `databricks bundle validate --profile DEFAULT` finalizo correctamente.
* `databricks bundle deploy --profile DEFAULT` finalizo correctamente y creo/actualizo el job.
* Primera corrida manual de `SG_Rainfall_Daily_Incremental` finalizo correctamente.
* Resultado de la primera corrida:
  * Raw: 30 archivos `SG_P_YYYY_MM_DD.json`.
  * Rango cargado: `2026-04-11` a `2026-05-10`.
  * Bronze: 2.190 filas, 73 estaciones.
  * Silver: 2.190 filas, 73 estaciones.
  * Calidad Silver: `expected_days = 30`, `observed_days = 30`, `missing_pct = 0.0`, `is_usable = true`.
