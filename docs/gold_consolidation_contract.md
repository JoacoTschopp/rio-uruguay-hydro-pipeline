# Contrato de consolidación de `weather.gold.training_dataset_v0`

Fecha de cierre de R1-R7 y R9: **2026-08-21** (Fase 2 de `docs/roadmap.md`). R8 se cerró para
lluvia el mismo día en la Fase 3 (Decisión 023); temperatura queda pendiente. Este documento fija
en código y en texto las nueve reglas (`R1`–`R9`) de la Decisión 019 y su enmienda. Los números de
esta página son los reales, medidos contra el Gold regenerado el 2026-08-21 (versión Delta 244 de
`weather.gold.training_dataset_v0`, tras la Fase 3).

**El principio que ordena las nueve reglas:** el nivel nunca se pierde; lo que se puede
perder es el caudal derivado de él.

---

## R1 — Piso temporal: Gold arranca en 2000-01-01

**Dónde:** `notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb`, `DATASET_FLOOR` (cell-1) y
`build_calendar()` (cell-2), que recorta `calendar_start = max(min_fecha, DATASET_FLOOR)`.

**Efecto medido:** `training_dataset_v0` pasó de 31.096 filas (1941–2026) a **9.729 filas**
(2000-01-01 a 2026-08-20). Las ~21.400 filas de 1941–1999 salieron de Gold. La serie larga
de nivel **no se perdió**: sigue completa desde 1941 en `weather.silver.river_levels_daily`
(no tocada por este cambio, que solo afecta a Gold).

## R2 — Sub-cuenca: solo `alta_frontera` entra a Gold

**Dónde:** `weather.silver.estacion_subcuenca` (Decisión 018), consumida en
`ETL_Gold_Training_Dataset_v0.ipynb` para los agregados `caudal_agregado_<subcuenca>_*`.
Ya estaba implementada antes de esta fase; sin cambios.

## R3 — Estación sin curva de aforo: el nivel se conserva

**Dónde:** `notebooks/04_Silver/ETL_Silver_River_Discharge_Daily.ipynb`, cell-9:
`caudal_metodo = 'sin_curva'` cuando no hay vigencia activa para esa fecha, `caudal_m3s`
queda en `NULL` pero `nivel_media_cm`/`nivel_media_m` se escriben igual.

**Efecto medido:** 792 filas / 5 estaciones con `caudal_metodo = 'sin_curva'` en
`weather.silver.river_discharge_daily` (universo completo de 392 estaciones con curva en
algún momento; las estaciones que nunca tuvieron curva ni siquiera entran a esta tabla,
pero su nivel sigue en `weather.bronze.ana_rio_uruguai`).

## R4 — Vigencia vencida: se extiende hasta hoy

**Dónde:** `ETL_Silver_River_Discharge_Daily.ipynb`, cell-4: por estación, si la curva de
`valid_from` más reciente tiene `valid_to < current_date()`, se extiende `valid_to` hasta
hoy y se marca `curva_vigencia_extendida = true`. Columna nueva en
`weather.silver.rating_curve_segments`, `weather.silver.river_discharge_daily` y
`weather.gold.training_dataset_v0` (DDL: `notebooks/04_Silver/DDL_Silver_Gold.ipynb`).

**Efecto medido:** 2 de las 22 estaciones de la cuenca alta quedaron con vigencia
extendida — `70100000` y `72715000`, ambas con vigencia nominal vencida el 2023-12-31, tal
como anticipaba la Decisión 019. La estación objetivo (`74100000`) no está entre ellas, así
que `curva_vigencia_extendida` sale en `false` en las 9.729 filas de Gold hoy; la columna
queda lista para cuando la curva del target venza.

## R5 — Cota fuera del rango calibrado: se extrapola y se marca

**Dónde:** ya implementada antes de esta fase (Decisión 017 · D3), sin cambios:
`caudal_extrapolado`, `distancia_fuera_rango_cm` en `river_discharge_daily`.

**Efecto medido:** 2.619 filas `extrapolado_superior` + 1.306 `extrapolado_inferior` en el
universo completo (392 estaciones). En la estación objetivo, **0 filas extrapoladas** —
confirmado con `notebooks_local/gold_export/fechas_extrapoladas.py`, que hoy escribe un CSV
vacío. El listado queda listo para cuando aparezca la primera extrapolación real.

## R6 — Estación íntegramente fuera de tabla: se descarta el caudal

**Dónde:** `ETL_Silver_River_Discharge_Daily.ipynb`, cell-9, después de calcular
`caudal_metodo`: si una estación con curva disponible nunca tiene una fila `interpolado`,
se fuerza `caudal_m3s = NULL`, `caudal_confiable = false`,
`caudal_metodo = 'descartado_r6'`.

**Efecto medido:** **1 estación** activó la regla — `66400390`, con una única lectura de
nivel de 20.079,7 cm (~200 m), a 19.379,7 cm fuera del rango calibrado de su curva: un
outlier de datos, no una crecida real. Ninguna de las 22 estaciones de la cuenca alta
activó R6 (0%), como anticipaba la Decisión 019.

## R7 — Umbral de `is_usable`: MAPE ≤ 30% en rango

**Dónde:** `ETL_Silver_River_Discharge_Daily.ipynb`, `MAPE_USABLE_THRESHOLD = 0.30` (cell-1);
mismo umbral alineado en `notebooks_local/ana_rating_curve/download_rating_curves_batch.py`
(`MAPE_SOSPECHOSA_THRESHOLD`), para que el reporte local y la validación en Silver no den
veredictos distintos para la misma estación.

**Efecto medido:** **20 de 22 estaciones usables** en la cuenca alta. Quedan fuera
`70100000` (MAPE 114,7%) y `70300000` (MAPE 138,2%); conservan su nivel y solo pierden el
caudal, según la regla general.

## R8 — Sin umbral de exclusión para lluvia (temperatura queda pendiente)

**Dónde:** `ETL_Silver_Rainfall_Daily.ipynb` ya no mide un `missing_pct` global para decidir si
publica o borra; publica toda estación con dato real y la medición de calidad queda como
informativa en `weather.silver.attribute_quality` (Decisión 023). `ETL_Gold_Training_Dataset_v0.ipynb`
corrige además el alcance de `lluvia_acumulada_mm`: antes sumaba toda la cuenca (violaba R2),
ahora sólo `alta_frontera`, vía el mismo join contra `weather.silver.estacion_subcuenca` que usa
el agregado de caudal. Se agregan `lluvia_agregado_alta_frontera_station_count`,
`_cobertura_pct`, `_acum_3d_mm` y `_acum_7d_mm`. `lluvia_is_usable` queda deprecada (siempre
`NULL`): la cobertura real reemplaza al portón binario.

**Efecto medido** (2026-08-21, versión Delta post-regeneración): de las 22 estaciones de
`alta_frontera`, **sólo 9 reportan lluvia, y sólo desde 2026-03-03** — 0 días de lluvia antes de
esa fecha en 26 años de historia. De las 9.729 filas de Gold, sólo **137 (1,4%)** tienen
`lluvia_acumulada_mm` no nulo; `lluvia_agregado_alta_frontera_cobertura_pct` promedia 0,006 sobre
la serie completa y hasta 9/22 (41%) en los días recientes con dato. Esto no es un defecto de la
regla: es la cobertura real de la fuente, expuesta en vez de ocultada por un portón que antes daba
una falsa sensación de cobertura casi completa al sumar lluvia de estaciones fuera de la cuenca
del punto de predicción. Detalle completo en la Decisión 023.

**Salto Grande fuera del agregado.** `weather.silver.sg_rainfall_daily` no se conecta a Gold:
ninguna de sus 69 estaciones activas cae en `alta_frontera` (59 en `baja_salto_grande`, las 10
restantes en `intermedia_paso_libres`, según la columna `subcuenca_nombre` del inventario del proveedor).
Conectarla violaría el mismo R2 que esta regla corrige para ANA.

**Temperatura fuera de alcance de esta pasada.** El mismo criterio (sin umbral, cobertura como
columna) queda pendiente para `weather.silver.temperature_daily` — tarea de la Fase 3 aún
abierta, junto con la ingesta de INMET.

## R9 — Cola sin target: se recorta en el exportador

**Dónde:** ya implementada en la Fase 1 (`notebooks_local/gold_export/export_gold_dataset.py`,
`trim_horizon_tail()`), sin cambios en esta fase. Gold conserva las filas con target en
`NULL`; el exportador las recorta por horizonte con `--horizonte`.

## Ampliación a 8 horizontes

**Dónde:** `ETL_Gold_Training_Dataset_v0.ipynb`, `HORIZONS = [1, 2, 3, 4, 5, 6, 7, 14]`,
aplicado en paralelo a `nivel_rio_t_mas_{h}d` y `caudal_t_mas_{h}d` (16 columnas de target).
DDL correspondiente en `DDL_Silver_Gold.ipynb`.

**Efecto medido:** las 16 columnas de horizonte están pobladas en Gold. De las 9.696 filas
`interpolado` de la estación objetivo, el conteo de targets no nulos decrece con el
horizonte como es esperable (más días sin observación futura hacia el final de la serie):
`caudal_t_mas_1d` 9.690, `caudal_t_mas_2d` 9.687, `caudal_t_mas_6d` 9.677,
`caudal_t_mas_14d` 9.661.

---

## Reconciliación del barrido de curvas

El barrido cerrado (392 estaciones, 62 con curva) se subió completo al Volume
(`notebooks_local/ana_rating_curve/sync_to_databricks.py`: 407 JSON de curvas + 77 de
aforos) y se reprocesó con `Rating_Curve_Discharge_Initial_Load` (`ETL_Bronze_Rating_Curve`
→ `ETL_Silver_River_Discharge_Daily` en `load_mode=full` → `Validate_River_Discharge`,
las tres tareas en verde) antes de regenerar Gold.

## Verificación de cierre

- `Rating_Curve_Discharge_Initial_Load` (job de Databricks): 3/3 tareas en verde.
- `Silver_Gold_Initial_Load_v0` (job de Databricks): 7/7 tareas en verde, incluyendo
  `Validate_Training_Dataset_v0` y `Export_Gold_Snapshot`.
- `python export_gold_dataset.py --refresh --resumen`: reproduce localmente 9.729 filas,
  rango 2000-01-01 a 2026-08-20, 99,7% `interpolado` para la estación objetivo — sin abrir
  Databricks, mismo criterio de cierre que la Fase 1.
- `python fechas_extrapoladas.py`: 0 fechas extrapoladas para la estación objetivo hoy
  (esperado, ver R5).
