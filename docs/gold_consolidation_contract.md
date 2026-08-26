# Contrato de consolidación de `weather.gold.training_dataset_v0`

Fecha de cierre de R1-R7 y R9: **2026-08-21** (Fase 2 de `docs/roadmap.md`). R8 se cerró para
lluvia el 2026-08-21 (Decisión 023) y para temperatura el 2026-08-24 (Decisión 025), cerrando la
Fase 3 completa. Este documento fija en código y en texto las nueve reglas (`R1`–`R9`) de la
Decisión 019 y su enmienda. Los números de R1-R7 y R9 son los medidos el 2026-08-21; los de R8
(lluvia y temperatura) están actualizados al 2026-08-24 (versión Delta 257 de
`weather.gold.training_dataset_v0`).

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
Ya estaba implementada antes de esta fase; sin cambios de código.

**Efecto medido (2026-08-24, Fase 7 del roadmap, Decisión 028):** el `JOIN` de
`caudal_agregado_alta_frontera_m3s` contra `estacion_subcuenca` siempre fue dinámico, nunca
hardcodeado a las 22 estaciones del grupo A. La resiembra completa de `estacion_subcuenca` en la
Decisión 024 (782 estaciones en `alta_frontera`, no solo 22) amplió sin código nuevo el universo
del agregado de caudal: de las 40 estaciones "grupo B" con curva del barrido de la Fase 2
(clasificadas entonces como "fuera de la cuenca alta"), **14 caen realmente en `alta_frontera`**
con la unión espacial real (validada al 99,9% con `geopandas`, Decisión 024). Hoy 36 estaciones
distintas (22 grupo A + 14 grupo B) contribuyen a `caudal_agregado_alta_frontera_m3s`, verificado
contra Databricks real: el valor de esa columna en `weather.gold.training_dataset_v0` coincide
exactamente con un recálculo fresco del `JOIN` completo para fechas de muestra en 2010, 2020 y
2025. Las estaciones nuevas empiezan a densificar el agregado en **2015** (1-3 activas por día ese
año) y llegan a 10-14 activas por día en 2024-2026. Detalle completo en la Decisión 028.

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

## R8 — Sin umbral de exclusión para lluvia y temperatura

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

**Temperatura (cerrado 2026-08-24, Decisión 025).** Mismo criterio que lluvia: sin umbral de
exclusión, cobertura real como columna. Se sumó INMET (27 estaciones automáticas de la cuenca,
15 en `alta_frontera`) a `weather.silver.temperature_daily`, unificado con METAR vía `estacion_id`
y `fuente`. Se corrigió además un bug de alcance espacial en `ETL_Gold_Training_Dataset_v0.ipynb`:
el bloque `temp_global` promediaba los 4 aeropuertos METAR sin ningún `JOIN` contra
`estacion_subcuenca` — violaba R2 igual que el bug de lluvia de las Decisiones 023/024, sólo que
sin datos faltantes de por medio (el número resultante era temperatura nacional brasileña, no de
la cuenca). Los 4 aeropuertos METAR están geográficamente fuera de las tres sub-cuencas, así que
el reemplazo (`temp_alta_frontera`, mismo patrón de `JOIN` que lluvia) usa exclusivamente
estaciones INMET — no hizo falta ninguna regla de prioridad entre fuentes. Se agregan
`temp_agregado_alta_frontera_station_count` y `_cobertura_pct`; `temp_station_count` (la columna
vieja, sin escopear) queda deprecada.

**Efecto medido** (2026-08-24, `Silver_Gold_Initial_Load_v0` en `load_mode=full`,
`weather.gold.training_dataset_v0`): de las 9.732 filas totales, **7.184 (73,8%) tienen
`temp_media_c` no nulo**. La cobertura por año es 0% en 2000-2005 (ninguna estación de
`alta_frontera` operaba todavía — la primera, `A828` Erechim, arranca en 2006-11), 9,6% en 2006
(arranca a mitad de año), 99,2% en 2007 y **100% todos los años desde 2008 hasta 2025** (90,2% en
2026, año en curso, parcial); el promedio de estaciones que aportan al agregado diario crece de
2,0 (2006) a 8-12 sobre un universo de 15 mapeadas en `alta_frontera`. Detalle completo, incluyendo
dos bugs de ejecución encontrados y corregidos (formato de fecha de INMET cambia en 2019; migración
de esquema con `MERGE` dejando filas huérfanas), en la Decisión 025.

**Salto Grande y METAR fuera del agregado**, mismo motivo que lluvia: ninguna estación (SG o METAR)
cae en `alta_frontera`.

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
- **Temperatura (2026-08-24, Decisión 025):** `Silver_Gold_Initial_Load_v0` en `load_mode=full`:
  8/8 tareas en verde (job creció de 7 a 8 tareas con `ETL_Bronze_INMET`), incluyendo
  `Validate_Training_Dataset_v0` y `Export_Gold_Snapshot`. `python export_gold_dataset.py
  --refresh --resumen` reproduce localmente 9.732 filas, rango 2000-01-01 a 2026-08-23,
  `temp_media_c` no nulo en 73,8% de las filas — sin abrir Databricks.
