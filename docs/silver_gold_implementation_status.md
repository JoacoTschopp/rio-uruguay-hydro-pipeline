# Estado de implementación Silver/Gold

Fecha de actualización: 2026-05-09

## Resumen

La capa Silver/Gold definida en `docs/silver_gold_jobs_plan.md` quedó desplegada y ejecutada en Databricks.

## Jobs Databricks

| Job | Estado | Schedule | Job ID |
| --- | --- | --- | --- |
| `Silver_Gold_Initial_Load_v0` | Creado y ejecutado manualmente con éxito | Sin schedule | `101402765418521` |
| `Silver_Gold_Daily_Incremental` | Creado, activo y probado manualmente con éxito | `04:30` America/Montevideo | `20817204203342` |

El job incremental corre después de los jobs Bronze diarios existentes:

| Job Bronze | Schedule observado |
| --- | --- |
| `Nivel_ANA_Target` | `02:00:42` America/Montevideo |
| `All_Estacoes_ANA_Daily` | `03:00:13` America/Montevideo |
| `Temperature_Airport_Brasil` | `02:00:43` UTC |

## Runs validados

| Run | Resultado |
| --- | --- |
| `Silver_Gold_Initial_Load_v0` run `933795064550723` | `SUCCESS` |
| `Silver_Gold_Daily_Incremental` run `729377179997482` | `SUCCESS` |

## Tablas materializadas

| Tabla | Filas |
| --- | ---: |
| `weather.silver.attribute_quality` | 5 |
| `weather.silver.river_levels_daily` | 30.582 |
| `weather.silver.temperature_daily` | 46.787 |
| `weather.silver.rainfall_daily` | 0 |
| `weather.gold.training_dataset_v0` | 30.992 |

## Cobertura Gold

| Métrica | Valor |
| --- | --- |
| Fecha mínima | `1941-07-02` |
| Fecha máxima | `2026-05-08` |
| Punto de predicción | `ana_74100000` |
| Duplicados por `fecha + punto_prediccion` | 0 |
| Mismatches target `t+1`, `t+3`, `t+7`, `t+14` | 0 |

## Calidad de atributos

| Fuente | Atributo | Missing pct | Usable |
| --- | --- | ---: | --- |
| `weather.silver.river_levels_daily` | `nivel_media_cm` | 0,013229 | true |
| `weather.silver.temperature_daily` | `temp_media_c` | 0,996686 | false |
| `weather.silver.temperature_daily` | `temp_min_c` | 0,996686 | false |
| `weather.silver.temperature_daily` | `temp_max_c` | 0,996686 | false |
| `weather.silver.rainfall_daily` | `lluvia_acumulada_mm` | 0,997916 | false |

Según la regla documentada (`missing_pct > 0.90`), lluvia y temperatura quedan excluidas de Gold v0 y se publican como `NULL`.

## Observación sobre METAR

`weather.bronze.metar` tiene registros entre `1990-01-01` y `2026-05-08`, pero las columnas de temperatura (`temp`/`tmpf`) solo están pobladas para una porción reciente. Los campos crudos históricos (`rawOb`/`metar`) aparecen nulos en las muestras de 1990, por lo que no hay señal suficiente para imputar o reconstruir temperatura histórica desde Bronze actual.

## Configuración versionada

La definición de los jobs quedó versionada en `databricks.yml` mediante Databricks Asset Bundles.
