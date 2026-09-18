# Reporte de calidad de `weather.gold.training_dataset_v0`

Fecha de medición: **2026-08-26**, contra Databricks real (warehouse serverless `Serverless Starter
Warehouse`, `d8aaafcf1fdb6645`, vía `POST /api/2.0/sql/statements`). Entregable de la **Fase 6** de
`docs/roadmap.md`. Cubre el ~80% de la fase que corresponde a lo ya cerrado (Fases 1, 2, 3, 7 y 9);
la sección final marca explícitamente lo que falta cuando cierre la Fase 4 (pronóstico).

Estado de la tabla al momento de la medición: **9.732 filas**, **2000-01-01 → 2026-08-23**, un solo
`punto_prediccion` (`ana_74100000`), **83 columnas**, sin huecos de calendario (ver §3).

---

## 1. Método

Todas las cifras de este documento salen de consultas SQL reales contra
`weather.gold.training_dataset_v0` (y, para contexto de origen, contra
`weather.silver.river_discharge_daily` / `estacion_subcuenca`), no de inspección de código ni de
estimaciones. Mismo mecanismo que ya usaron las Decisiones 023-028 y 033: `databricks api post
/api/2.0/sql/statements` contra el warehouse serverless, con `MSYS_NO_PATHCONV=1` en Git Bash. Las
reglas de cálculo de cada columna se verificaron contra el código real de
`notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb` (no se documentó nada por referencia).

Los dos notebooks de calidad que pide la Fase 6 (`Validate_Training_Dataset_v0.ipynb`,
`Check_Bronze_Freshness.ipynb`) **ya estaban versionados en el repo** al empezar esta sesión
(`notebooks/06_Quality/`, commit `864cb85` y anteriores) — se verificó comparando su contenido
contra el Workspace real (`databricks workspace export --format SOURCE`) y son idénticos línea por
línea. La Decisión 017 los daba como pendientes de traer al repo; ya no lo están. No hizo falta
ningún `workspace import` en esta sesión.

---

## 2. Resumen general

| Métrica | Valor |
| --- | --- |
| Filas | 9.732 |
| Rango de fechas | 2000-01-01 → 2026-08-23 |
| Días de calendario esperados en el rango | 9.732 (`DATEDIFF(max,min)+1`) |
| Filas ≠ días de calendario | **0** — sin huecos de grano diario |
| `punto_prediccion` distintos | 1 (`ana_74100000`) |
| Columnas | 83 |
| `caudal_metodo` distintos en Gold | 2: `interpolado` (9.696), `NULL` (36) |

---

## 3. Discontinuidades temporales

**Grano de calendario: sin huecos.** `DATEDIFF(MAX(fecha), MIN(fecha)) + 1 = 9.732 = COUNT(*) =
COUNT(DISTINCT fecha)`. Cada día entre 2000-01-01 y 2026-08-23 tiene exactamente una fila. Esto
confirma que `build_calendar()` en `ETL_Gold_Training_Dataset_v0.ipynb` (secuencia diaria explícita,
no un `JOIN` que pueda perder días) cumple lo que promete.

**Huecos de valor (la fila existe, el dato no) para la estación objetivo:**

| Caso | Filas | Rango |
| --- | ---: | --- |
| `nivel_rio_actual_cm` y `caudal_actual_m3s` ambos `NULL` | 27 | `2014-12-31` (1 día suelto) + `2026-04-07` a `2026-05-04` (26 días, con una recuperación de 2 días el 04-08/04-09 en medio del corte) |
| `nivel_rio_actual_cm` `NULL`, `caudal_actual_m3s` con dato | **93** | `2025-11-01` → `2026-03-27` |
| `nivel_rio_actual_cm` con dato, `caudal_actual_m3s` `NULL` | 9 | `2026-05-26` a `2026-08-23` (días sueltos, cola reciente) |
| Ambos con dato | 9.603 | resto |

**Hallazgo no documentado antes de este reporte:** las 93 filas de la segunda fila de la tabla son
un caso real, no un artefacto de la consulta. `nivel_rio_actual_cm`/`_m` sale de
`weather.silver.river_levels_daily` y `caudal_actual_m3s` sale de
`weather.silver.river_discharge_daily` — dos tablas Silver independientes que ambas dependen en
última instancia del mismo Bronze (`weather.bronze.ana_rio_uruguai`), pero con pipelines de
agregación distintos. Entre 2025-11-01 y 2026-03-27 la primera no tiene fila para `74100000`
mientras la segunda sí (`caudal_metodo='interpolado'`, `caudal_registros_validos=1`, un solo
registro válido ese día). No se investigó la causa raíz en esta sesión (está fuera del alcance de
"medir calidad", no de "corregir pipeline"); queda como hallazgo para una sesión futura que toque
`ETL_Silver_River_Levels_Daily` o el Bronze de nivel.

Los 9 días de cola reciente (`nivel` con dato, `caudal` sin) son esperables: es el desfase normal
entre la llegada del nivel diario y la conversión nivel→caudal, que hoy no está encadenada como task
diario (pendiente de la Fase 5, todavía `Pendiente` en el roadmap).

---

## 4. Verificación de fuga de target (data leakage)

Se verificó, **para las 9.732 filas de la tabla completa** (no sólo un spot-check), que
`caudal_t_mas_{1,7,14}d` de la fecha `f` coincide exactamente (`ABS(diff) ≤ 0.0001`) con
`caudal_actual_m3s` de la fecha `f + N` días, vía un `LEFT JOIN` de la tabla contra sí misma
desplazada por fecha:

| Horizonte | Filas con mismatch (valor no nulo que no matchea `f+N`) |
| --- | ---: |
| t+1 | 0 |
| t+7 | 0 |
| t+14 | 0 |

Spot-check adicional con fechas conocidas (`2010-06-01`, `2015-01-15`, `2020-01-15`, `2023-03-10`):
los tres horizontes coinciden dígito a dígito contra el valor real de `f+N`. Ejemplo:
`2010-06-01.caudal_t_mas_14d = 1722.9471494399995`, que es exactamente
`caudal_actual_m3s` de `2010-06-15`. Se confirmó también que **no** es una copia del mismo día:
`caudal_actual_m3s` de `2010-06-01` es `2407.15…`, distinto del `t_mas_1d` de esa misma fila
(`2360.23…`, que es el valor real de `2010-06-02`). **Sin fuga de target detectada.**

Nota metodológica: se encontraron pares de días con `caudal_t_mas_Nd` idéntico bit a bit al valor
observado (p. ej. `2010-06-02` y `2010-06-08` ambos con `nivel=299 cm` → mismo `caudal_m3s`,
`2360.227010760419`). No es un bug: la conversión nivel→caudal es una función determinística de la
curva de aforo, así que dos días con el mismo nivel exacto dan el mismo caudal exacto. Se investigó
antes de descartarlo como coincidencia.

---

## 5. Cobertura por `caudal_metodo` y por veredicto de curva

La tabla Gold tiene un solo `punto_prediccion` (la estación objetivo, `74100000`), que es una de las
20/22 estaciones `is_usable=true` de la cuenca alta (R7, MAPE 30%) y **no** es una de las 2 con
`curva_vigencia_extendida` (`70100000`, `72715000` — Decisión 019/enmienda, R4). Por eso la
distribución en Gold es simple:

| `caudal_metodo` | `curva_vigencia_extendida` | Filas | % | Rango de fechas |
| --- | --- | ---: | ---: | --- |
| `interpolado` | `false` | 9.696 | 99,63% | 2000-01-01 → 2026-08-20 |
| `NULL` (sin conversión ese día) | `NULL` | 36 | 0,37% | 2014-12-31 → 2026-08-23 (ver §3) |

Ninguna fila de la estación objetivo tiene `caudal_metodo` = `extrapolado_superior`,
`extrapolado_inferior`, `sin_curva` ni `descartado_r6` — consistente con el contrato (R5: 0
extrapolaciones en el target; R6: sólo activó para `66400390`, fuera de la cuenca alta; R7: el
target está entre las 20 usables). `caudal_extrapolado = true` en **0** filas;
`supera_aforo_maximo = true` en **16** filas (el nivel superó el aforo máximo medido pero se
mantuvo dentro del rango calibrado de la curva — no es lo mismo que extrapolar); `caudal_confiable =
true` en las 9.696 filas con dato, `false` en 0.

**Cobertura de los agregados por sub-cuenca** (veredicto de curva a nivel de estación, aplicado a
las estaciones que contribuyen al agregado, no al target individual):

| Columna | No nulas | % | Estaciones que aportan (Decisión 028) |
| --- | ---: | ---: | --- |
| `caudal_agregado_alta_frontera_m3s` | 9.697 | 99,64% | 36 (22 grupo A + 14 grupo B) |
| `caudal_agregado_intermedia_paso_libres_m3s` | 7.684 | 78,96% | 23 (fuera de alcance de tesis, Decisión 018) |
| `caudal_agregado_baja_salto_grande_m3s` | 6.843 | 70,33% | 2 (fuera de alcance de tesis, Decisión 018) |

**Hallazgo de calidad no documentado antes de este reporte:** el agregado `SUM(caudal_m3s)` por
sub-cuenca (`ETL_Gold_Training_Dataset_v0.ipynb`, celda `subcuenca_daily`) **no filtra por
`caudal_confiable`** (documentado ya en la Decisión 028 como criterio deliberado, "mismo criterio
que ya regía antes"). El efecto real medido: **9.653 de 9.732 filas (99,2%)** de
`caudal_agregado_alta_frontera_m3s` incluyen al menos una estación con `caudal_confiable=false` ese
día (`AVG(confiable_pct) = 0,90`), y **218 filas** (2,2%) superan 50.000 m³/s — fisicamente
implausible para esta cuenca (el máximo real del target en 26 años es 32.624 m³/s). El pico medido,
**823.897,75 m³/s el 2023-05-06**, se explica por una sola estación: `73340000` (una de las 14
"grupo B" de `alta_frontera`, Decisión 028), con `caudal_m3s = 817.914,79`, `caudal_metodo =
'extrapolado_superior'`, `caudal_confiable = false` ese día — y no es un evento aislado: los 15
valores más altos del agregado (790.000-824.000 m³/s) se concentran todos entre abril y julio de
2023, la misma estación dominando el agregado durante meses. **Recomendación para quien use esta
columna en modelado:** filtrar o investigar `73340000` antes de usar `caudal_agregado_alta_frontera_m3s`
como feature cruda; el nombre de la columna no deja ver que puede estar dominada por una curva no
confiable.

---

## 6. Faltantes por columna y por año

Tabla completa de nulos por columna (9.732 filas totales), agrupada por bloque temático. `n` =
filas `NULL`; `%` = filas no nulas.

### 6.1. Identificadores y calendario

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| `fecha` | 0 | 100% |
| `punto_prediccion` | 0 | 100% |
| `codigoestacao` | 0 | 100% |
| `feature_generated_at` / `updated_at` | 0 | 100% |

### 6.2. Nivel del río (target secundario, estación objetivo)

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| `nivel_rio_actual_cm` / `_m` | 120 | 98,8% |
| `nivel_registros_validos` | 120 | 98,8% |
| `nivel_rio_lag_1d` | 121 | 98,8% |
| `nivel_rio_lag_3d` | 123 | 98,7% |
| `nivel_rio_lag_7d` | 127 | 98,7% |
| `nivel_rio_media_3d` | 112 | 98,8% |
| `nivel_rio_media_7d` | 104 | 98,9% |
| `nivel_rio_delta_1d` | 127 | 98,7% |
| `nivel_rio_t_mas_1d` … `t_mas_14d` | 121 → 134 (crece con el horizonte) | 98,6-98,8% |

### 6.3. Caudal (target principal, estación objetivo)

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| `caudal_actual_m3s` | 36 | 99,6% |
| `caudal_metodo`, `caudal_extrapolado`, `distancia_fuera_rango_cm`, `supera_aforo_maximo`, `caudal_confiable`, `curva_vigencia_extendida` | 36 cada una | 99,6% |
| `caudal_registros_validos` | 0 (siempre 0 o 1, nunca `NULL`) | 100% |
| `caudal_lag_1d` / `_3d` | 36 / 36 | 99,6% |
| `caudal_lag_7d` | 40 | 99,6% |
| `caudal_media_3d` / `_7d` | 27 / 19 | 99,7-99,8% |
| `caudal_delta_1d` | 42 | 99,6% |
| `caudal_t_mas_1d` … `t_mas_14d` | 37 → 50 (crece con el horizonte) | 99,5-99,6% |

### 6.4. Temperatura por estación (METAR + INMET, agregado `alta_frontera`)

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| `temp_media_c` / `temp_min_c` / `temp_max_c` | 2.548 | 73,8% |
| `temp_agregado_alta_frontera_station_count` / `_cobertura_pct` | 2.548 | 73,8% |
| `temp_station_count` (deprecada, Decisión 025) | 9.732 | 0% — siempre `NULL`, a propósito |

Cobertura anual (ya medida en la Decisión 025, reconfirmada): 0% en 2000-2005, 9,6% en 2006, 99,2%
en 2007, **100% cada año 2008-2025**, 90,2% en 2026 (parcial).

### 6.5. Lluvia por estación (ANA, agregado `alta_frontera`)

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| `lluvia_acumulada_mm` | 34 | 99,65% |
| `lluvia_agregado_alta_frontera_acum_3d_mm` / `_7d_mm` | 26 / 19 | 99,7-99,8% |
| `lluvia_agregado_alta_frontera_station_count` / `_cobertura_pct` | 32 | 99,67% |
| `lluvia_is_usable` (deprecada, Decisión 023) | 9.732 | 0% — siempre `NULL`, a propósito |

Cobertura anual (Decisión 024): 100% todos los años 2000-2025, 85,4% en 2026 (parcial).

### 6.6. Observación en grilla CPTEC (MERGE lluvia, SAMeT temperatura)

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| Las 7 columnas `lluvia_merge_alta_frontera_*` | 0 | **100%** |
| Las 5 columnas `temp_samet_alta_frontera_*` | 0 | **100%** |

Sin excepción en las 9.732 filas — confirma lo cerrado en la Decisión 033. `lluvia_merge_alta_frontera_es_preliminar
= true` en 46 filas (cola reciente, archivo todavía no regenerado); `temp_samet_alta_frontera_es_preliminar
= true` en 15 filas.

### 6.7. Agregados de caudal por sub-cuenca

| Columna | Nulos | Cobertura |
| --- | ---: | ---: |
| `caudal_agregado_alta_frontera_m3s` (+ lags, + `confiable_pct`) | 35 | 99,64% |
| `caudal_agregado_intermedia_paso_libres_m3s` (+ lags, + `confiable_pct`) | 2.048 | 78,96% |
| `caudal_agregado_baja_salto_grande_m3s` (+ lags, + `confiable_pct`) | 2.889 | 70,33% |

Las dos últimas están fuera del alcance de la tesis (Decisión 018) pero tienen datos reales (no son
un placeholder en `NULL`), documentado en la Decisión 028.

### 6.8. Faltantes por año — columnas clave (2000-2026)

| Año | Días | `nivel` nulo | `caudal` nulo | `temp` (estación) nulo | `lluvia` (estación) nulo | `merge` nulo | `samet` nulo | `agregado_intermedia` nulo | `agregado_baja` nulo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2000 | 366 | 0 | 0 | 366 | 0 | 0 | 0 | 366 | 366 |
| 2001 | 365 | 0 | 0 | 365 | 0 | 0 | 0 | 365 | 365 |
| 2002 | 365 | 0 | 0 | 365 | 0 | 0 | 0 | 365 | 365 |
| 2003 | 365 | 0 | 0 | 365 | 0 | 0 | 0 | 365 | 365 |
| 2004 | 366 | 0 | 0 | 366 | 0 | 0 | 0 | 366 | 366 |
| 2005 | 365 | 0 | 0 | 365 | 0 | 0 | 0 | 179 | 365 |
| 2006 | 365 | 0 | 0 | 330 | 0 | 0 | 0 | 0 | 365 |
| 2007 | 365 | 0 | 0 | 3 | 0 | 0 | 0 | 1 | 232 |
| 2008 | 366 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 24 |
| 2009 | 365 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 35 |
| 2010-2013 | ~1.461 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2014 | 365 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 3 |
| 2015-2022 | ~2.922 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2023 | 365 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 2024 | 366 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2025 | 365 | 61 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026 (parcial, a 08-23) | 235 | 58 | 35 | 23 | 34 | 0 | 0 | 37 | 37 |

`merge` y `samet` en 0 nulos todos los años, sin excepción — la fila más limpia de toda la tabla.
`nivel`/`caudal` prácticamente sin huecos hasta 2024; el hueco de 2025 (61 días) y 2026 (58/35 días)
corresponde a lo detallado en §3.

---

## 7. Diccionario de columnas

`weather.gold.training_dataset_v0` tiene 83 columnas. Se agrupan por bloque; unidad, origen y regla
de cálculo verificados contra `docs/gold_consolidation_contract.md`, `docs/data_sources.md` y el
código real de `ETL_Gold_Training_Dataset_v0.ipynb`. Rango observado = `MIN`/`MAX` real medido en
esta sesión (§1).

### 7.1. Identificadores

| Columna | Tipo | Origen / regla |
| --- | --- | --- |
| `fecha` | `date` | Clave de grano (junto a `punto_prediccion`). Secuencia diaria explícita, `build_calendar()`. |
| `punto_prediccion` | `string` | Constante `'ana_74100000'` (Decisión 018). |
| `codigoestacao` | `string` | Constante `'74100000'`, código ANA de la estación objetivo (Irai, frontera Brasil/Argentina). |
| `feature_generated_at`, `updated_at` | `timestamp` | `current_timestamp()` en el momento de la corrida del job de Gold. |

### 7.2. Nivel del río (target secundario)

| Columna | Unidad | Origen | Regla | Rango observado |
| --- | --- | --- | --- | --- |
| `nivel_rio_actual_cm` | cm | `weather.silver.river_levels_daily.nivel_media_cm` (ANA `Cota_Adotada`, telemetría horaria/subhoraria promediada por día) | Media diaria de lecturas válidas | 90,0 – 1.485,0 |
| `nivel_rio_actual_m` | m | ídem, en metros | `nivel_media_m` | 0,9 – 14,85 |
| `nivel_registros_validos` | conteo | ídem | Nº de lecturas intradía válidas usadas en la media | 1 – 98 |
| `nivel_rio_lag_1d`/`_3d`/`_7d` | m | derivada | `LAG(nivel_rio_actual_m, N)` sobre la ventana ordenada por `fecha` | mismo rango que `nivel_rio_actual_m` |
| `nivel_rio_media_3d`/`_7d` | m | derivada | Media móvil de `nivel_rio_actual_m` sobre 3/7 días (`rowsBetween`) | subconjunto del rango de `nivel_rio_actual_m` |
| `nivel_rio_delta_1d` | m | derivada | `nivel_rio_actual_m − nivel_rio_lag_1d` | −5,39 – 8,57 |
| `nivel_rio_t_mas_{1,2,3,4,5,6,7,14}d` | m | derivada (target secundario) | `LEAD(nivel_rio_actual_m, N)` — verificado sin fuga (§4) | mismo rango que `nivel_rio_actual_m` |

### 7.3. Caudal (target principal)

| Columna | Unidad | Origen | Regla | Rango observado |
| --- | --- | --- | --- | --- |
| `caudal_actual_m3s` | m³/s | `weather.silver.river_discharge_daily.caudal_m3s` (nivel → caudal vía curva de aforo vigente, Decisión 017) | Ley de potencia `Q = A·(H−H0)^N` por segmento de curva vigente en la fecha | 145,47 – 32.624,42 |
| `caudal_registros_validos` | 0/1 | derivada | `1` si `caudal_actual_m3s` no nulo, `0` si no (no es un conteo de lecturas, pese al nombre — es un flag) | 0 – 1 |
| `caudal_metodo` | string | `river_discharge_daily.caudal_metodo` | `interpolado` / `extrapolado_superior` / `extrapolado_inferior` / `sin_curva` / `descartado_r6` (universo completo; en la estación objetivo sólo aparece `interpolado` o `NULL`, ver §5) | — |
| `caudal_extrapolado` | boolean | ídem | `true` si `caudal_metodo` empieza con `extrapolado_` | siempre `false` en el target (0 filas) |
| `distancia_fuera_rango_cm` | cm | ídem | Distancia del nivel al límite calibrado de la curva cuando extrapola | 0,0 – 0,0 en el target (nunca extrapola) |
| `supera_aforo_maximo` | boolean | ídem | `true` si el nivel supera el aforo máximo medido pero sigue dentro del rango calibrado | `true` en 16 filas del target |
| `caudal_confiable` | boolean | ídem | `is_usable` de la curva de la estación (R7, MAPE ≤ 30% en rango) propagado a cada fila | `true` en las 9.696 filas con dato (target siempre usable) |
| `curva_vigencia_extendida` | boolean | ídem (R4, Decisión 019 enm.) | `true` si la última curva vigente se extendió más allá de su `valid_to` nominal | siempre `false` en el target |
| `caudal_lag_1d`/`_3d`/`_7d` | m³/s | derivada | `LAG(caudal_actual_m3s, N)` | mismo rango que `caudal_actual_m3s` |
| `caudal_media_3d`/`_7d` | m³/s | derivada | Media móvil 3/7 días | subconjunto del rango de `caudal_actual_m3s` |
| `caudal_delta_1d` | m³/s | derivada | `caudal_actual_m3s − caudal_lag_1d` | −16.068,78 – 19.138,26 |
| `caudal_t_mas_{1,2,3,4,5,6,7,14}d` | m³/s | derivada (target principal) | `LEAD(caudal_actual_m3s, N)` — verificado sin fuga (§4) | mismo rango que `caudal_actual_m3s` |

### 7.4. Temperatura por estación (agregado `alta_frontera`)

| Columna | Unidad | Origen | Regla | Rango observado |
| --- | --- | --- | --- | --- |
| `temp_media_c` | °C | `weather.silver.temperature_daily` (METAR + INMET, unificadas por `estacion_id`/`fuente`, Decisión 025), filtrado a estaciones de `estacion_subcuenca = alta_frontera` (en la práctica sólo INMET: los 4 aeropuertos METAR caen fuera de las 3 sub-cuencas) | `AVG(temp_media_c)` de las estaciones que reportan ese día | 1,04 – 27,09 |
| `temp_min_c` | °C | ídem | `MIN(temp_min_c)` entre estaciones | mínimo real: −6,0 |
| `temp_max_c` | °C | ídem | `MAX(temp_max_c)` entre estaciones | máximo real: 36,7 |
| `temp_agregado_alta_frontera_station_count` | conteo | derivada | `COUNT(DISTINCT estacion_id)` con `temp_media_c` no nulo | 2 – 12 (universo de 15 mapeadas) |
| `temp_agregado_alta_frontera_cobertura_pct` | fracción [0,1] | derivada | `station_count / 15` | 0 – 0,8 (verificado en `[0,1]` por `Validate_Training_Dataset_v0`) |
| `temp_station_count` | bigint | **deprecada** (Decisión 025) | Reemplazada por `temp_agregado_alta_frontera_*`; siempre `NULL` a propósito | — |

### 7.5. Lluvia por estación (agregado `alta_frontera`)

| Columna | Unidad | Origen | Regla | Rango observado |
| --- | --- | --- | --- | --- |
| `lluvia_acumulada_mm` | mm (**suma**, no promedio) | `weather.silver.rainfall_daily.lluvia_acumulada_mm` (ANA `Chuva_Adotada`), filtrado a `alta_frontera` | `SUM(lluvia_acumulada_mm)` de **todas** las estaciones que reportan ese día (hasta 782 mapeadas) | 0,0 – 12.241,28 — ver nota abajo |
| `lluvia_agregado_alta_frontera_acum_3d_mm`/`_7d_mm` | mm | derivada | Suma móvil 3/7 días de `lluvia_acumulada_mm` | acumulados del rango de arriba |
| `lluvia_agregado_alta_frontera_station_count` | conteo | derivada | `COUNT(DISTINCT codigoestacao)` con dato ese día | 0 – 177 (universo de 782 mapeadas, cobertura real baja por día) |
| `lluvia_agregado_alta_frontera_cobertura_pct` | fracción [0,1] | derivada | `station_count / 782` | 0 – 0,226 |
| `lluvia_is_usable` | boolean | **deprecada** (Decisión 023) | Reemplazada por `_cobertura_pct`; siempre `NULL` a propósito | — |

**Nota sobre el rango de `lluvia_acumulada_mm`:** el máximo real (12.241,28 mm, 2024-12-07) no es un
error de unidades ni un outlier de estación — es la **suma** de 152 estaciones reportando ese día
(≈80,5 mm/estación en promedio, un día de lluvia fuerte real). El nombre de la columna no dice que es
una suma sobre el agregado, no una lectura puntual; documentado acá para que no se lea como un error
al inspeccionar el rango.

### 7.6. Observación en grilla CPTEC (Decisión 033)

| Columna | Unidad | Origen | Regla | Rango observado |
| --- | --- | --- | --- | --- |
| `lluvia_merge_alta_frontera_mm` | mm | `weather.silver.precip_grid_daily` (MERGE, CPTEC/INPE, satélite GPM-IMERG V07B + pluviómetros, grilla 0,1°) | Media areal de los puntos de grilla dentro de `alta_frontera` (ventana 12Z(D-1)→12Z(D)) | 0,0 – 85,28 |
| `lluvia_merge_alta_frontera_max_mm` | mm | ídem | Máximo de los puntos de grilla ese día | — |
| `lluvia_merge_alta_frontera_acum_3d_mm`/`_7d_mm` | mm | derivada | Suma móvil 3/7 días | — |
| `lluvia_merge_alta_frontera_pluviometros` | conteo | ídem | Densidad de pluviómetros usados en el NEST de esa celda/día | 5 – 223 |
| `lluvia_merge_alta_frontera_cobertura_pct` | fracción [0,1] | derivada | Puntos de grilla con dato / puntos totales de `alta_frontera` (566 puntos) | 1,0 (siempre completa) |
| `lluvia_merge_alta_frontera_es_preliminar` | boolean | ídem | `true` si el archivo de origen no fue regenerado todavía (MERGE se reescribe al mes siguiente) | `true` en 46 filas |
| `temp_samet_alta_frontera_media_c` | °C | `weather.silver.temp_grid_daily` (SAMeT, CPTEC/INPE, observaciones + ERA5 corregido, grilla 0,05°) | Media areal de `alta_frontera`, día calendario UTC | −0,33 – 26,15 |
| `temp_samet_alta_frontera_max_c`/`_min_c` | °C | ídem | Media areal de TMAX/TMIN | — |
| `temp_samet_alta_frontera_cobertura_pct` | fracción [0,1] | derivada | Puntos con dato / puntos totales (2.269 puntos) | 1,0 (siempre completa) |
| `temp_samet_alta_frontera_es_preliminar` | boolean | ídem | `true` si no pasaron los 7 días de regeneración de SAMeT | `true` en 15 filas |

### 7.7. Agregados de caudal por sub-cuenca (Decisiones 018, 028)

| Columna | Unidad | Origen | Regla | Rango observado |
| --- | --- | --- | --- | --- |
| `caudal_agregado_alta_frontera_m3s` | m³/s | `river_discharge_daily` × `estacion_subcuenca` | `SUM(caudal_m3s)` de todas las estaciones de `alta_frontera` (36: 22 grupo A + 14 grupo B), **sin filtrar `caudal_confiable`** | 272,49 – 823.897,75 — ver hallazgo de §5 |
| `caudal_agregado_alta_frontera_lag_1d`/`_2d`/`_3d` | m³/s | derivada | `LAG` sobre el agregado | — |
| `caudal_agregado_alta_frontera_confiable_pct` | fracción [0,1] | derivada | `AVG(caudal_confiable::double)` entre las estaciones que aportan ese día | promedio real: 0,90 |
| `caudal_agregado_intermedia_paso_libres_*` | m³/s | ídem, sub-cuenca `intermedia_paso_libres` | ídem (23 estaciones) — **fuera del alcance de la tesis**, Decisión 018 | 0,0 – 973.005,93 |
| `caudal_agregado_baja_salto_grande_*` | m³/s | ídem, sub-cuenca `baja_salto_grande` | ídem (2 estaciones) — **fuera del alcance de la tesis**, Decisión 018 | 0,54 – 38.895,24 |

---

## 8. Hallazgos de calidad encontrados en esta sesión (no documentados antes)

Ninguno bloquea el cierre de la Fase 6 (son limitaciones de la fuente/diseño, no bugs del pipeline
de Gold), pero se registran porque no estaban en ninguna decisión previa:

1. **Divergencia `nivel_rio_actual_cm` vs. `caudal_actual_m3s` en 93 días** (`2025-11-01` →
   `2026-03-27`): el nivel de la estación objetivo sale `NULL` de `river_levels_daily` mientras el
   caudal (que también depende del nivel, pero vía `river_discharge_daily`) sí tiene dato. Dos
   pipelines Silver independientes leyendo la misma fuente Bronze pueden divergir. Ver §3.
2. **`caudal_agregado_alta_frontera_m3s` puede estar dominado por una curva no confiable**: 99,2% de
   las filas incluyen al menos una estación con `caudal_confiable=false`; el pico de 823.897 m³/s
   (25× el máximo real del target) lo explica la estación `73340000` sola, con
   `caudal_metodo='extrapolado_superior'`, sostenido durante meses de 2023. Ver §5.
3. **`lluvia_acumulada_mm` es una suma sobre estaciones, no una lectura puntual** — el máximo
   observado (12.241 mm) es correcto pero puede leerse como un error de unidades si no se documenta
   la regla de agregación. Ver §7.5.

---

## 9. Pendiente al cierre de la Fase 4

Este reporte cubre lo ya cerrado (Fases 1, 2, 3, 7, 9). La Fase 4 (pronóstico TIGGE + GEFS con
empalme calibrado) sigue `En curso` en paralelo — no se tocó nada de esa fase en esta sesión. Lo que
falta actualizar en este mismo documento cuando cierre:

* **Columna `forecast_source`** (todavía no existe en el esquema de Gold — no aparece en las 83
  columnas de §7): declarar su origen (`tigge_cf`, `tigge_pf`, `gefs_reforecast`, empalme calibrado)
  por fila, y sumarla a §7 con su regla de cálculo real.
* **Features de pronóstico calibrado**: hoy no hay ninguna columna de precipitación/temperatura
  pronosticada en Gold. Cuando entren, sumar a §6 (faltantes por año — van a tener huecos reales en
  2000-2006 y en el tramo de empalme 2006-2019 hasta que se complete el backfill de GEFS) y a §7
  (unidad, horizonte, `forecast_age_days` mencionado en la Decisión/investigación A).
* **Cobertura por horizonte de pronóstico**: una vez existan las features, medir cobertura por
  horizonte (t+1 a t+14) igual que se mide para los targets en §6.3 — el pronóstico probablemente
  tenga peor cobertura en los horizontes largos.
* Nada de lo medido en este reporte para nivel/caudal/temperatura/lluvia/MERGE/SAMeT necesita
  recalcularse por el cierre de la Fase 4: son columnas independientes, la Fase 4 sólo agrega
  columnas nuevas.
