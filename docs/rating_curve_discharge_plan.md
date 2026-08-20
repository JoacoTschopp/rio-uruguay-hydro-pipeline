# Plan: curvas de aforo multi-estación y conversión nivel → caudal

## 0. Objetivo

Hoy el pipeline solo tiene la curva de descarga de **una** estación (`74100000`, Irai), descargada a mano
con `notebooks_local/ana_rating_curve/download_rating_curve.py`. El dataset de tesis usa niveles de
múltiples estaciones ANA como predictores (y como target), y el nivel (cota, cm) **no es comparable
entre estaciones**: depende del cero de escala local y de la geometría de la sección. El caudal
(m³/s) sí es una magnitud física comparable, es la variable que tiene sentido hidrológico para
propagación aguas abajo, y es la que usan los sistemas operativos para toma de decisión.

Este plan cubre dos fases:

* **Fase 1** — descargar y consolidar las curvas de aforo (curva-chave) de **todas** las estaciones ANA
  con medición de nivel, no solo el target.
* **Fase 2** — aplicar la conversión nivel → caudal dentro del pipeline Medallion en Databricks,
  eligiendo por cada registro la curva vigente en esa fecha, y exponer el caudal como variable y como
  target del dataset de entrenamiento.

Ambas fases son independientes en ejecución: la Fase 2 puede empezar en cuanto la Fase 1 tenga
descargadas las curvas del grupo A (ver §2.2).

---

## 1. Decisiones tomadas (2026-08-14)

Estas cuatro decisiones están cerradas y el resto del documento ya las refleja. Se formalizan como
Decisión 017 en `decisions.md` al implementar.

| # | Decisión | Detalle |
| --- | --- | --- |
| D1 | **La conversión nivel → caudal ocurre en Silver** | Tabla nueva `weather.silver.river_discharge_daily`, grano `fecha + codigoestacao`. Gold consume el caudal ya calculado. §3.1 |
| D2 | **El target es caudal, sin perder el nivel** | Gold publica targets de caudal (`caudal_t_mas_1d/3d/7d/14d`) **y** mantiene los de nivel (`nivel_rio_t_mas_*`). Ambos conjuntos de features también. §3.5 |
| D3 | **Cota fuera del rango calibrado se extrapola, no se anula** | Nunca `NULL` por estar fuera de rango. Se extrapola con el segmento extremo y se marca con flags (`caudal_extrapolado`, `caudal_metodo`, `distancia_fuera_rango_cm`) para que el tratamiento como outlier sea una decisión de modelado, no una pérdida de información. §3.4 |
| D4 | **Todas las estaciones con nivel, piso temporal 2000-01-01** | Se implementa para el universo completo (~385 estaciones con `Cota_Adotada` en Bronze), sin filtrar por profundidad histórica. Nada anterior a 2000-01-01 entra al dataset. Una limpieza posterior por representatividad se hará con el sistema ya funcionando. §2.2 |

Sobre D3, un matiz que conviene tener presente: extrapolar una ley de potencia por encima de su rango
calibrado es donde más se equivoca, y justamente en crecidas. Con las flags, un caudal sobredimensionado
queda identificable y filtrable aguas abajo — que es exactamente lo pedido: sobredimensionar antes que
perder el dato. La magnitud real del error de extrapolación se mide en §3.6 y se documenta.

---

## 2. Hallazgos de la investigación previa (ya validados contra datos reales)

Estos tres hallazgos condicionan el diseño de todo el plan y ya están confirmados, no son supuestos.

### 2.1. La API filtra por fecha de modificación del registro, no por vigencia — calibrado y corregido (2026-08-14)

Hallazgo inicial (antes de calibrar): `download_rating_curve.py` parte el rango `1950-01-01 → hoy` en
77 ventanas de 365 días. Para 74100000, 75 de 77 ventanas devolvían `[]` y solo 2 (`2024-02-26..2025-02-25`
y `2025-02-26..2026-02-26`) traían las 8 vigencias completas desde 1948. La hipótesis original fue
"el endpoint no filtra por vigencia, trae toda la historia en cualquier ventana que pegue".

**Esa hipótesis se probó y es incorrecta.** Ejecutado el Paso 0 de calibración (§3.3) contra 8
estaciones con curva real, cada item devuelto trae un campo `Data_Ultima_Alteracao` (fecha en que ANA
tocó ese registro en su sistema, no la vigencia de la curva), y **el endpoint filtra por ese campo
cayendo dentro de la ventana consultada** — se confirmó comparando `Data_Ultima_Alteracao` de cada
segmento contra la ventana que lo devolvió. Por eso las 2 ventanas "mágicas" para 74100000
funcionaban: sus 25 segmentos históricos comparten `Data_Ultima_Alteracao = 2024-10-25` (una migración
masiva de datos históricos hecha por ANA) y los 3 segmentos de la curva vigente tienen
`Data_Ultima_Alteracao = 2025-12-09` (última recalibración). Esas dos fechas caen, por coincidencia, en
esas dos ventanas puntuales — pero **la fecha de migración no es la misma para todas las estaciones**:

| Estación | Ventanas con datos (de 77, rango 1950-2026) |
| --- | --- |
| 74100000 | `2024-02-26..2025-02-25`, `2025-02-26..2026-02-26` |
| 72680000 | `2024-02-26..2025-02-25`, `2025-02-26..2026-02-26` |
| 71350001 | `2024-02-26..2025-02-25`, `2025-02-26..2026-02-26` |
| 73350000 | `2023-02-25..2024-02-25`, `2024-02-26..2025-02-25` |
| 72849000 | `2023-02-25..2024-02-25`, `2024-02-26..2025-02-25` |
| 70110000, 72100980, 73100000 | ninguna (`[]` en las 77 ventanas) — estas 3 **no tienen curva real** |

Usar solo las 2 ventanas de 74100000 como constante fija habría producido falsos negativos
(`sin_curva`) para 73350000 y 72849000, dos estaciones del grupo A que sí tienen curva.

**Conclusión calibrada:** en las 8 estaciones con curva probadas, todos los `Data_Ultima_Alteracao`
caen dentro de una banda de ~3 años (`2023-02-25` a `2026-02-26`, es decir "los últimos ~3.5 años desde
hoy"), consistente con que ANA migró/cargó el histórico completo de curvas a este webservice en algún
momento de ese período. Las 3 estaciones sin datos en esa banda tampoco tuvieron datos en ninguna de
las 77 ventanas 1950-2026 — `[]` es una señal confiable de "sin curva publicada", no de "ventana
equivocada".

**Ventana fija adoptada para el barrido masivo:** 5 ventanas de 365 días cubriendo
`(hoy.año − 4)-01-01 → hoy` (con margen de 1 año extra sobre el piso observado de 2023-02-25, dado que
solo se probaron 8 de ~385 estaciones). Esto son **5 requests por estación** en vez de 77 — sigue
siendo un cambio de orden de magnitud (≈1.925 requests para 385 estaciones en vez de ≈30.000), aunque
mayor que la estimación inicial de "2-3 requests". Si el reporte de cobertura (paso 6) muestra
estaciones con curva conocida por otra vía (ej. `Vazao_Adotada` con muchos registros en Bronze) pero
`sin_curva` en este barrido, es la señal de que el margen de 1 año no alcanzó para esa estación y hay
que ampliarlo puntualmente.

Nota importante para D4: aunque el dataset arranca en 2000, **las curvas hay que traerlas completas**.
Una vigencia que empezó en 1992 puede seguir vigente en 2003, así que el rango de descarga de curvas no
se recorta por el piso de 2000 — el recorte temporal se aplica a los datos de nivel, no a los
metadatos de curva. Esto ya no depende de la ventana de consulta (que es sobre `Data_Ultima_Alteracao`,
no sobre vigencia): la vigencia de cada segmento devuelto sigue siendo la real, sin importar cuándo fue
tocado el registro por última vez.

### 2.2. La convención de unidades de la fórmula está mal resuelta en el script actual

La curva-chave segmentada es `Q = A · (H − H0)^N`. El script actual compara dos convenciones
candidatas y elige la de menor error contra los aforos reales. **Las dos candidatas son incorrectas**:

| Convención | Fórmula implementada | MAPE vs 292 aforos reales | Mediana |
| --- | --- | ---: | ---: |
| `h0_in_meters=False` (H0 en cm) | `H_cm − H0` | 25.538 (absurdo) | 11.995 |
| `h0_in_meters=True` (actual "ganadora") | `H_cm/100 − H0/100` | **0,44** | 0,25 |
| **Correcta** | `H_cm/100 − H0` | **0,051** | **0,031** |

La API entrega `Coef_h0` **ya en metros** (valores como `0.67`, `0.87`, `0.19`), mientras que la cota
viene en cm. La conversión correcta es pasar la cota a metros y restar H0 tal cual. La rama
`h0_in_meters=True` del script divide H0 por 100 **de más**, y el selector por MAPE la elige porque es
"la menos mala de dos opciones malas": queda con **44% de error medio** en vez de **5,1%**.

Consecuencia: la columna `coefficient_h0_cm` del CSV `segmentos_curva_74100000.csv` está mal
nombrada (es en metros) y `curva_aforo_74100000.csv` está **numéricamente mal**. Hay que regenerarlo.

### 2.3. La tabla generada hoy solo sirve para el presente, no para el histórico

`build_stage_discharge_table()` usa únicamente `choose_active_curve()` — la curva **vigente hoy**. Para
convertir 25 años de niveles históricos hace falta la curva **vigente en cada fecha**. Para 74100000
hay 8 vigencias distintas entre 1948 y 2026, con coeficientes muy diferentes (A de 290,7 a 672,9).
Usar la curva vigente para todo el histórico introduciría un sesgo sistemático creciente hacia atrás
en el tiempo — exactamente el tipo de error silencioso que arruina un dataset de entrenamiento.

También hay **huecos de vigencia**: para 74100000 no existe curva entre `1953-09-19` y `1971-07-05`.
Ese hueco cae antes del piso de 2000, pero otras estaciones pueden tener huecos dentro del rango útil.
Un hueco de vigencia **sí** produce `NULL` — es ausencia real de la curva, distinto del caso de cota
fuera de rango (D3), donde sí hay curva y se extrapola.

---

## 3. Fase 1 — Descarga de curvas de aforo de todas las estaciones con nivel

### 3.1. Dónde corre

**Local**, siguiendo la Decisión 016: es I/O secuencial contra una API externa, sin nada que ganar de
Spark. Se reutiliza la infraestructura ya construida para el backfill de ANA (`lock.py`, logging a
archivo, `sync_to_databricks.py`). Directorio: `notebooks_local/ana_rating_curve/`.

### 3.2. Universo de estaciones

Por D4, el alcance es **el universo completo** de estaciones con medición de nivel. No se filtra por
profundidad histórica: el backfill (Decisión 016) está corriendo y le va a dar profundidad a las
estaciones que hoy solo tienen desde 2026-03-03, así que descartarlas ahora obligaría a rehacer el
trabajo. El universo **no se hardcodea**: se calcula y se persiste como `estaciones_nivel.json`, mismo
criterio que el backfill histórico (Decisión 015).

```sql
-- se corre una vez en Databricks (es barata) y se vuelca a estaciones_nivel.json
SELECT DISTINCT codigoestacao
FROM weather.bronze.ana_rio_uruguai
WHERE Cota_Adotada IS NOT NULL AND trim(Cota_Adotada) <> ''
```

Los **grupos** que siguen son solo **orden de ejecución**, no recorte de alcance — las dos se
descargan completas:

* **Grupo A — 22 estaciones con historia profunda** (`SIG/estaciones_ana_nivel_historico.geojson`):
  las únicas con historia real anterior a 2026-03-03. Se hacen primero porque desbloquean la Fase 2 con
  datos suficientes para validar de punta a punta.
* **Grupo B — el resto** (~360 estaciones): mismo tratamiento, en tandas resumibles a continuación.

Muchas estaciones del grupo B son pluviométricas que reportan algún `Cota_Adotada` espurio y no tienen
curva. La API devuelve `[]` — ese es el criterio de descarte, registrado como `sin_curva` en el reporte.
No hay que pre-filtrar por tipo de estación.

### 3.3. Pasos

**Paso 0 — Calibración del rango (bloqueante, ~15 min). ✅ Ejecutado 2026-08-14.**
Se probaron 8 estaciones (5 del grupo A + 3 del grupo B) con barridos completos de 77 ventanas
(1950-2026) más pruebas puntuales de ventana ancha. Resultado, ver detalle en §2.1:

* el endpoint **no** acepta ventanas > 366 días (confirmado: 800 días → `406 Client Error`), el
  `MAX_WINDOW_DAYS = 365` heredado es correcto también para este endpoint;
* el filtro de fecha del endpoint es sobre `Data_Ultima_Alteracao` (modificación del registro), no
  sobre vigencia de la curva — una sola ventana reciente **no** basta, y el número de ventanas
  necesarias varía por estación (observado: 2, en fechas distintas según estación);
* estaciones sin curva publicada devuelven `[]` en las 77 ventanas de forma consistente — no es un
  problema de rango, es ausencia real de datos.

**Constante fijada:** 5 ventanas de 365 días cubriendo `(año_actual − 4)-01-01 → hoy`. Documentado en
§2.1 con el margen de seguridad adoptado y la señal para detectarlo si no alcanza.

**Paso 1 — Script de barrido multi-estación.**
Nuevo `notebooks_local/ana_rating_curve/download_rating_curves_batch.py`, que reutiliza las funciones
de request/normalización del script actual y agrega lo que hoy no tiene:

* estado resumible (`rating_curve_state.json`: pendientes / hechas / sin-curva / con-error), mismo
  patrón que `historic_backfill_state.json`;
* **re-autenticación ante 401** — el script actual no la tiene y un barrido largo va a cruzar el
  vencimiento del token (`run_backfill_local.py` ya resuelve esto, se copia el patrón);
* lock de un solo proceso (`lock.py`) y logging a `logs/rating_curve.log`;
* flags `--group {A,B}`, `--stations`, `--max-stations N`, `--only-missing`, `--skip-aforos`;
* salida por estación en `output/raw_json/` + consolidados `segmentos_curva_ALL.csv` y
  `aforos_ALL.csv`.

**Paso 2 — Corregir la convención de unidades.**
En el módulo de normalización: renombrar `coefficient_h0_cm` → `coefficient_h0_m`, implementar la
conversión correcta (`H_cm/100 − H0_m`) y **mantener la validación contra aforos**, pero como control
de calidad por estación (reporta MAPE) en lugar de como selector entre convenciones. Si una estación
da MAPE alto (> ~15-20%), se marca como sospechosa en el reporte en vez de elegir en silencio una
fórmula alternativa.

**Paso 3 — Curvas del grupo A** (22 estaciones) + aforos del grupo A desde 2000-01-01.
**Paso 4 — Curvas del grupo B** (~360 estaciones), tandas resumibles.
**Paso 5 — Aforos del grupo B** (segunda pasada, no bloqueante, ver §3.5).

Los pasos 3-5 deben coordinarse con el backfill histórico que ya corre cada 4 h: **nunca en paralelo**,
comparten cuenta y token de la API de ANA (mismo criterio que Decisión 015). La forma más simple es
reutilizar el mismo `lock.py` con un nombre de lock compartido, o correrlo en la ventana entre tandas.

**Paso 6 — Reporte de cobertura.**
`output/reporte_cobertura_curvas.csv`, una fila por estación: n° de vigencias, rango temporal cubierto,
**huecos de vigencia dentro de 2000-hoy**, rango de cota cubierto, n° de aforos, MAPE de validación, y
un veredicto `usable / usable_con_huecos / sin_curva / sospechosa`. Es el insumo del gate de calidad
de la Fase 2.

**Paso 7 — Subida a Databricks.**
Los consolidados se suben al Volume (`databricks fs cp`, mismo patrón que `sync_to_databricks.py`) en
una carpeta nueva `/Volumes/weather/raw/ana_volume/rating_curves/`. El volumen de datos es chico
(~10-15k filas de segmentos en total), así que no hace falta chunking ni cuidados de tamaño.

### 3.4. Costo estimado

| Concepto | Requests | Tiempo estimado |
| --- | ---: | ---: |
| Calibración (paso 0) | ~450 (8 estaciones × 77 ventanas) | ✅ hecho |
| Curvas grupo A (22 est. × 5 ventanas) | ~110 | 5 min |
| Aforos grupo A (22 est. × 27 ventanas desde 2000) | ~600 | 30-60 min |
| Curvas grupo B (~360 est. × 5 ventanas) | ~1.800 | 60-90 min |
| Aforos grupo B (~360 est. × 27 ventanas, no bloqueante) | ~9.700 | 5-8 h en tandas |

Las estimaciones de tiempo asumen la latencia variable ya observada en el backfill (Decisión 016,
consecuencia abierta: 6-21 min por ventana de 351 estaciones). Podría ser peor; el estado resumible
y el corte por `--max-stations` cubren ese riesgo. Los primeros cuatro renglones (≈2 h) son los que
bloquean la Fase 2; el quinto corre después, en segundo plano.

### 3.5. Alcance de los aforos (medições reais)

Los aforos **no** se usan para calcular caudal — se usan para **validar** que la curva reproduce
mediciones reales, y (nuevo con D3) para **acotar hasta dónde la extrapolación es defendible**: el
aforo de mayor cota registrado en una estación marca el límite empírico real de la curva.

* **Rango: desde 2000-01-01**, coherente con D4 (27 ventanas por estación en vez de 77).
* **Grupo A: obligatorio y bloqueante** — son las estaciones con historia profunda, donde la validación
  importa más.
* **Grupo B: segunda pasada, no bloqueante.** La Fase 2 no espera por estos aforos, porque existe un
  control cruzado independiente y gratuito: `Vazao_Adotada` ya viene en Bronze para muchas estaciones
  (§3.6 de Fase 2). Cuando los aforos del grupo B lleguen, se recalcula el MAPE por estación y se
  actualiza `is_usable` en Silver sin tocar el resto del pipeline.
* Si una estación no tiene aforos desde 2000, se acepta la curva sin validación pero se marca
  `sin_validacion` en el reporte y en Silver.

---

## 4. Fase 2 — Transformación nivel → caudal en el pipeline

### 4.1. La conversión va en Silver (D1)

La conversión cota → caudal es una **normalización física por estación**, no un feature: aplica al
grano `fecha + codigoestacao`, que es el grano de Silver. Gold trabaja a grano
`fecha + punto_prediccion` y su trabajo es lags, ventanas móviles y targets. Es coherente con la
Decisión 011 (el recorte geográfico se hace en Silver porque es regla de negocio) y con la Decisión 006.
Además deja el caudal disponible para EDA, para el segundo punto de predicción y para cualquier Gold
futuro, sin duplicar la lógica de vigencia de curvas en cada notebook.

### 4.2. Tablas nuevas

`notebooks/01_DDL/DDL_Rating_Curve.ipynb` (o extender `DDL_Silver_Gold.ipynb`):

```
weather.bronze.ana_rating_curve_segments   -- espejo crudo del JSON de la API
weather.bronze.ana_discharge_measurements  -- aforos crudos

weather.silver.rating_curve_segments
  codigoestacao STRING, rating_curve_id STRING, segment_number INT,
  valid_from DATE, valid_to DATE,
  stage_min_cm DOUBLE, stage_max_cm DOUBLE,
  coefficient_a DOUBLE, coefficient_h0_m DOUBLE, coefficient_n DOUBLE,
  consistency_level INT,
  is_lowest_segment BOOLEAN, is_highest_segment BOOLEAN,   -- segmentos extremos de la vigencia (para extrapolar, D3)
  aforo_stage_max_cm DOUBLE,                               -- cota máxima con aforo real: límite empírico
  is_usable BOOLEAN, validation_mape DOUBLE,
  source_table STRING, processed_at TIMESTAMP, updated_at TIMESTAMP

weather.silver.river_discharge_daily
  fecha DATE, codigoestacao STRING,
  nivel_media_cm DOUBLE, nivel_media_m DOUBLE,             -- el nivel NUNCA se pierde (D2)
  caudal_m3s DOUBLE,
  rating_curve_id STRING, segment_number INT,              -- trazabilidad de qué curva se usó
  caudal_metodo STRING,                                    -- 'interpolado' | 'extrapolado_superior' | 'extrapolado_inferior' | 'bajo_cero_curva' | 'sin_curva'
  caudal_extrapolado BOOLEAN,
  distancia_fuera_rango_cm DOUBLE,                         -- cuánto excede el rango calibrado (0 si dentro)
  supera_aforo_maximo BOOLEAN,                             -- cota por encima del aforo real más alto de la estación
  curva_disponible BOOLEAN,                                -- false solo si no hay vigencia para esa fecha
  caudal_confiable BOOLEAN,                                -- dentro de rango calibrado + curva is_usable
  source_table STRING, processed_at TIMESTAMP, updated_at TIMESTAMP
```

Tabla separada en vez de columnas nuevas en `river_levels_daily`: el ciclo de vida es distinto (el
caudal se recalcula entero cuando ANA publica una recalibración de curva, el nivel no) y evita tocar
el esquema de una tabla que ya alimenta Gold.

### 4.3. ETL Bronze (`notebooks/02_Bronze/ETL_Bronze_Rating_Curve.ipynb`)

Lee `/Volumes/weather/raw/ana_volume/rating_curves/`, MERGE idempotente por
`(codigoestacao, rating_curve_id, segment_number)`. Sin tipado (coherente con el resto de Bronze del
proyecto: el tipado se resuelve en Silver).

### 4.4. ETL Silver (`notebooks/04_Silver/ETL_Silver_River_Discharge_Daily.ipynb`)

Corazón de la Fase 2. Lógica:

1. **Cargar segmentos** desde Bronze, tipar, aplicar reglas de selección:
   * ante vigencias solapadas, preferir mayor `consistency_level` (2 = consistido > 1 = bruto);
   * descartar segmentos con `coefficient_a`, `coefficient_n` o `coefficient_h0_m` nulos;
   * marcar `is_lowest_segment` / `is_highest_segment` por `rating_curve_id`.
2. **Join temporal con `river_levels_daily`**: por `codigoestacao` y
   `valid_from <= fecha <= valid_to`, filtrando `fecha >= 2000-01-01` (D4). Es un range join; con
   ~10-15k segmentos totales conviene `broadcast()` la tabla de segmentos — no hay riesgo de OOM
   (contraste con Decisión 014).
3. **Selección de segmento por cota**, con extrapolación (D3):

   | Caso | Segmento usado | `caudal_metodo` | `caudal_m3s` |
   | --- | --- | --- | --- |
   | Cota dentro de `[stage_min, stage_max]` de algún segmento | ese segmento | `interpolado` | calculado |
   | Cota > `stage_max` del segmento más alto | el más alto | `extrapolado_superior` | **calculado igual** |
   | Cota < `stage_min` del segmento más bajo, pero > H0 | el más bajo | `extrapolado_inferior` | **calculado igual** |
   | Cota ≤ H0 (por debajo del cero de la curva) | — | `bajo_cero_curva` | `0.0` |
   | No hay vigencia de curva para esa fecha | — | `sin_curva` | `NULL` |

   Solo el último caso produce `NULL`, y es ausencia real de curva, no un problema de rango.
   El caso `bajo_cero_curva` se resuelve con `0.0` en vez de `NULL` por el mismo criterio de D3 (no
   perder el dato): físicamente la cota está por debajo del nivel de referencia de la curva y el caudal
   es despreciable. Queda flageado; si el EDA muestra que es frecuente en alguna estación, es señal de
   cero de escala desplazado y se revisa esa curva.
4. **Cálculo**: `caudal_m3s = A · (nivel_media_cm/100 − H0_m)^N`, con la convención validada en §2.2.
5. **Flags de contexto de la extrapolación** — el punto clave de D3: el dato se entrega, pero
   perfectamente identificable para tratarlo como outlier aguas abajo.
   * `distancia_fuera_rango_cm`: cuántos cm por encima (o debajo) del rango calibrado cayó la cota;
     `0` si está dentro. Permite un umbral graduado en vez de un booleano (ej. "aceptar hasta 50 cm de
     extrapolación").
   * `supera_aforo_maximo`: la cota supera el aforo real más alto medido en esa estación. Es el
     indicador más honesto de "acá la curva ya no tiene respaldo empírico".
   * `caudal_confiable = interpolado AND curva is_usable`. **No es un filtro aplicado**, es una columna:
     el dataset sale completo y el modelado decide.
6. **Registrar calidad** en `weather.silver.attribute_quality` (mismo patrón `build_quality` /
   `merge_quality` que ya usan los ETL Silver existentes), con `attribute_name = 'caudal_m3s'` y grano
   por estación, para que Gold pueda usar el gate `quality_is_usable()` que ya tiene implementado.
   Agregar además una métrica de % de días extrapolados por estación/año.
7. **Modos** `full` / `incremental` con `incremental_lookback_days`, idénticos a los demás ETL Silver.
   Un `full` extra hace falta cada vez que se refresquen las curvas (§4.7).

### 4.5. ETL Gold (`notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb`)

Por D2, Gold pasa a tener **doble juego de targets y features**: caudal como variable principal de
decisión, nivel conservado íntegro.

Cambios sobre el notebook actual:

* leer también `weather.silver.river_discharge_daily`;
* **targets nuevos (principales)**: `caudal_t_mas_1d`, `caudal_t_mas_3d`, `caudal_t_mas_7d`,
  `caudal_t_mas_14d`;
* **targets existentes conservados**: `nivel_rio_t_mas_1d/3d/7d/14d` sin cambios. Permite entrenar en
  cualquiera de los dos espacios y comparar; y como la conversión es determinística y biyectiva dentro
  del rango de la curva, se puede predecir caudal y traducir a nivel (o al revés) después;
* **features de caudal**: `caudal_actual_m3s`, `caudal_lag_1d/3d/7d`, `caudal_media_3d/7d`,
  `caudal_delta_1d`, más las columnas de contexto que se propagan desde Silver
  (`caudal_extrapolado`, `distancia_fuera_rango_cm`, `supera_aforo_maximo`, `caudal_confiable`);
* **features de nivel existentes**: se mantienen todas;
* **features de caudal aguas arriba** — acá está el valor real de tener curvas de todas las estaciones.
  Con caudal comparable entre estaciones se pueden construir agregados por sub-cuenca
  (`SIG/subcuencas_modelo.geojson` ya define las 3):
  `caudal_agregado_subcuenca_X_m3s`, `caudal_agregado_lag_1d/2d/3d`, y un
  `caudal_agregado_confiable_pct` (qué proporción del agregado viene de caudales no extrapolados).
  Esto es físicamente sensato — los caudales se suman, los niveles no — y es probablemente la ganancia
  predictiva más grande de todo este trabajo. Requiere el grupo B completo (§3.2).

`DDL_Silver_Gold.ipynb` debe extenderse con todas estas columnas antes de correr el ETL.

### 4.6. Validación (`notebooks/06_Quality/Validate_River_Discharge.ipynb`)

* comparar `caudal_m3s` calculado contra `Vazao_Adotada` de Bronze donde exista (la API ya trae caudal
  adoptado para algunas estaciones — **es un control cruzado independiente y gratuito**, no hay que
  descargarlo). Es el sustituto de los aforos mientras el grupo B esté pendiente;
* comparar contra los aforos (mismo cálculo de MAPE que §3.3 paso 2, pero ahora en Spark sobre toda la
  serie), **separando aforos dentro de rango vs. por encima del rango calibrado** — esto último mide
  directamente cuánto se equivoca la extrapolación de D3 y es el número que hay que documentar;
* % de días por estación/año según `caudal_metodo`: cuánto del dataset es interpolado vs. extrapolado.
  Si una estación resulta ser mayoritariamente extrapolada, es candidata a exclusión en la limpieza
  posterior que mencionaste;
* distribución de `distancia_fuera_rango_cm` para calibrar un umbral razonable de "outlier";
* monotonicidad de la curva (Q creciente con la cota) y continuidad entre segmentos consecutivos —
  detecta errores de transcripción de coeficientes de la API;
* saltos abruptos en los bordes de vigencia (mismo día, curvas distintas → salto de caudal): si es
  grande, indica cambio de cero de escala y hay que documentarlo.

### 4.7. Actualización de curvas en el tiempo

Las curvas cambian raramente (para 74100000: 8 vigencias en 78 años). No hace falta job diario.
Propuesta: re-correr la Fase 1 (paso 4, sin `--only-missing`) **trimestralmente** o cuando la
validación cruzada contra `Vazao_Adotada` empiece a degradarse. Si aparece una vigencia nueva o cambia
una existente, `ETL_Silver_River_Discharge_Daily` debe correrse en modo `full` para esa estación —
recalcular todo el histórico, no solo lo reciente.

### 4.8. Fuera de alcance

* **Salto Grande / punto de predicción aguas abajo**: los datos del segundo punto crítico no vienen de
  ANA (son CARU / Salto Grande, ver `docs/sg_rainfall_ingestion_plan.md`). Esta conversión aplica solo
  a estaciones ANA. La conversión nivel → caudal del punto aguas abajo es un problema aparte.
* **Estaciones sin curva publicada**: quedan con nivel solamente (`caudal_metodo = 'sin_curva'`). No se
  estima una curva propia por regresión a partir de aforos — es un trabajo de hidrometría en sí mismo
  y no está justificado para v0.
* **Curvas de estaciones con influencia de represa**: Irai (74100000) está bajo influencia directa de
  la UHE Foz do Chapecó (ya advertido en el docstring del script actual). La curva sigue siendo válida
  como relación cota-caudal de la sección, pero el régimen no es natural. Se documenta, no se corrige.
* **Limpieza por representatividad de estaciones**: explícitamente diferida. Primero el sistema completo
  para todas las estaciones, después la selección con las métricas de §4.6 en la mano.

---

## 5. Orden de ejecución

| # | Paso | Fase | Bloquea a |
| --- | --- | --- | --- |
| 1 | Calibración de ventanas (§3.3 paso 0) | 1 | todo |
| 2 | Corregir convención H0 + renombrar columna (§3.3 paso 2) | 1 | 4, 5, 9 |
| 3 | Script de barrido multi-estación (§3.3 paso 1) | 1 | 4, 5 |
| 4 | Curvas + aforos grupo A (22 est.) | 1 | 8 |
| 5 | Curvas grupo B (~360 est.) | 1 | 11 |
| 6 | Reporte de cobertura | 1 | 9 |
| 7 | Subida al Volume | 1 | 8 |
| 8 | DDL + ETL Bronze de curvas | 2 | 9 |
| 9 | ETL Silver `river_discharge_daily` (incluye extrapolación D3) | 2 | 10, 11 |
| 10 | Notebook de validación (incluye error de extrapolación) | 2 | 11 |
| 11 | Gold: targets de caudal + features + agregados por sub-cuenca | 2 | — |
| 12 | Aforos grupo B (segunda pasada) → refresco de `is_usable` | 1 | — |
| 13 | Documentar Decisión 017 en `decisions.md` + `data_sources.md` | 2 | — |

Con el paso 7 completo (~2 h de descarga tras la calibración) ya se puede arrancar toda la Fase 2. El
paso 5 corre en paralelo a los pasos 8-10 y solo bloquea los agregados por sub-cuenca del paso 11. El
paso 12 corre en segundo plano y no bloquea nada: mejora la confianza de las curvas del grupo B una vez
que el resto ya funciona.
