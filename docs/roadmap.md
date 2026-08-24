# Roadmap del dataset de tesis

Fecha de corte: **2026-08-24**
Rama de trabajo: `feature/ana-backfill-automation`
Entregable final del roadmap: `weather.gold.training_dataset_v0` cerrado, documentado y descargable en local.

Este documento reemplaza a los planes anteriores (`thesis_dataset_roadmap.md`,
`rating_curve_discharge_plan.md`, `silver_gold_jobs_plan.md`, `sg_rainfall_ingestion_plan.md`), que fueron
retirados del repositorio. Lo que esos planes tenían de conocimiento consolidado vive ahora en
`decisions.md` (por qué se hizo cada cosa) y en `current_pipeline_inventory.md` /
`silver_gold_implementation_status.md` (qué quedó desplegado).

**No quedan decisiones abiertas.** Los criterios que estaban sin fijar se cerraron el 2026-08-21 en la
enmienda a la Decisión 019 y en las Decisiones 021 y 022. Lo que queda son tareas de investigación acotadas
dentro de fases concretas, cada una con su criterio de salida definido de antemano (§5).

---

## 1. Objetivo y alcance

Construir un dataset diario, reproducible y documentado para predecir el **caudal (m³/s) del Río Uruguay**
en la estación objetivo, con horizontes de 1 a 7 días y 14 días.

| Dimensión | Definición | Decisión |
| --- | --- | --- |
| Variable objetivo | Caudal en m³/s (el nivel se conserva como target secundario) | 017 · D2 |
| Punto de predicción | `ana_74100000` — Irai, frontera Brasil/Argentina | 018 |
| Horizontes | t+1, t+2, t+3, t+4, t+5, t+6, t+7, t+14 | 019 |
| Granularidad | Diaria. Grano lógico `fecha + punto_prediccion` | 003 |
| Alcance espacial en Gold | **Sólo la sub-cuenca `alta_frontera`** | 018 |
| Alcance espacial de la ingesta | Toda la cuenca, las tres sub-cuencas | 018 |
| Piso temporal de Gold | **2000-01-01**, para caudal, features y pronóstico | 019 enm. · 021 |

**El modelado no forma parte de este roadmap.** El baseline y el pipeline de entrenamiento son una fase
posterior del proyecto. Este roadmap termina cuando el dataset está serio: fuentes consolidadas, reglas de
inclusión escritas, calidad medida y snapshot reproducible.

### Alcance de la tesis (Decisión 018)

| Sub-cuenca | Ingesta | Gold | Tesis |
| --- | --- | --- | --- |
| `alta_frontera` — aporte hasta la frontera Brasil/Argentina | Sí | Sí | Sí |
| `intermedia_paso_libres` — frontera a Paso de los Libres | Sí | No | No |
| `baja_salto_grande` — Paso de los Libres a Salto Grande | Sí | No | No |

El segundo punto de predicción aguas abajo (CARU / Salto Grande) queda cancelado como objetivo. Las columnas
de agregado de las sub-cuencas de aguas abajo permanecen reservadas en el esquema de Gold, en `NULL`. La
decisión es reversible sin volver a descargar nada.

---

## 2. Estado al 2026-08-21 — qué ya está terminado

| Bloque | Estado | Evidencia |
| --- | --- | --- |
| Landing + Bronze (ANA, METAR, Salto Grande, ECMWF `cf`/`pf`) | Operativo | 5 jobs diarios en `databricks.yml` |
| Silver: niveles, temperatura, lluvia, ECMWF, caudal | Materializado | `silver_gold_implementation_status.md` |
| Gold `training_dataset_v0` | Materializado y validado | 0 duplicados, 0 mismatches de target |
| Conversión nivel → caudal por curva vigente | Implementada | Decisión 017 · 210.106 filas en `river_discharge_daily` |
| Backfill histórico ANA (nivel + lluvia) | **Completo** | 361 estaciones agotadas, 0 activas, 248 archivos sincronizados |
| Barrido de curvas de aforo, toda la cuenca | **Completo** | 392 estaciones, 0 errores, `pendientes = 0` |

### Resultado del barrido de curvas

| Veredicto | Estaciones | Efecto |
| --- | ---: | --- |
| Con curva usable (MAPE ≤ 30% en rango) | 20 de 22 en la cuenca alta | Nivel + caudal |
| Con curva no confiable | 2 (`70100000`, `70300000`) | Sólo nivel |
| Con curva, fuera de la cuenca alta | 40 | Fuera de Gold |
| `sin_curva` | 330 | Sólo nivel |
| **Total barrido** | **392** | 62 con curva · 1.235 segmentos · 2.270 aforos |

De las 62 estaciones con curva, **25 tienen la vigencia vencida**; 2 de ellas en la cuenca alta
(`70100000` y `72715000`, ambas vencidas el 2023-12-31), que se resuelven por extensión de curva (R4).

---

## 3. Fases

Ordenadas por relación entregable/tiempo. Las estimaciones son en días de trabajo efectivo.

### Fase 1 — Exportador local del dataset Gold

**Estimación:** ≈ 0,5 día · **Depende de:** nada · **Estado:** `Cerrada (2026-08-21)`

Va primera por rápida y porque es el instrumento para auditar todo lo demás: sin poder abrir la tabla en
pandas, las reglas de la Fase 2 y la cobertura de lluvia de la Fase 3 se deciden a ciegas.

**Diseño.** Un task final del job de Gold escribe un Parquet único en
`/Volumes/weather/raw/gold_export_volume/`; el script local lo baja con `databricks fs cp`, el mismo camino de
autenticación que ya usa `notebooks_local/ana_historic_backfill/sync_to_databricks.py`. No requiere un SQL
warehouse encendido, en línea con el criterio de costo de la Decisión 016.

**Tareas**

- [x] Task `Export_Gold_Snapshot` al final del job de Gold: escribe Parquet + `manifest.json`
  (`notebooks/05_Gold/Export_Gold_Snapshot.ipynb`, encadenado tras `Validate_Training_Dataset_v0`
  en `silver_gold_initial_load_v0` y `silver_gold_daily_incremental` en `databricks.yml`).
- [x] `notebooks_local/gold_export/export_gold_dataset.py` con la interfaz:
  `--refresh`, `--desde`, `--confiable`, `--horizonte {1..7,14}`, `--formato parquet|csv`, `--resumen`.
- [x] **`--horizonte` implementa la regla R9**: recorta la cola de días sin target observable para ese horizonte (Decisión 019, enmienda). Gold no borra esas filas. Nota: hoy Gold solo publica `caudal_t_mas_{1,3,7,14}d`; pedir `--horizonte 2/4/5/6` falla con un error explícito hasta que la Fase 2 agregue los 8 horizontes.
- [x] Manifiesto con versión Delta de origen, filas, rango de fechas, columnas, hash del archivo y fecha de exportación.
- [x] Corte por versión Delta: si no cambió, no vuelve a bajar (`needs_download`, cacheado en `notebooks_local/gold_export/cache/`).
- [x] Lock compartido (`lock.py`) con las tareas de ANA, para no solaparse (importa directamente `notebooks_local/ana_historic_backfill/lock.py`, mismo archivo de lock).

**Criterio de cierre:** `python export_gold_dataset.py --resumen` imprime filas, rango de fechas, faltantes
por columna y cobertura por `caudal_metodo` sin abrir Databricks. **Cumplido y verificado contra el Volume
real** (2026-08-21): `Export_Gold_Snapshot` corrió dentro de `Silver_Gold_Daily_Incremental`
(versión Delta 236, 31.096 filas, 1941-07-02 a 2026-08-20) y `export_gold_dataset.py --resumen` bajó y
resumió ese snapshot sin abrir Databricks; una segunda corrida sin `--refresh` confirmó el corte por versión
Delta (`Version Delta sin cambios (236); usando cache local`), y `--desde/--confiable/--horizonte` filtraron
correctamente sobre el dataset real. Ver seguimiento en §7 de este documento.

---

### Fase 2 — Contrato de consolidación y regeneración de Gold

**Estimación:** ≈ 2 días · **Depende de:** Fase 1 (para auditar el resultado) · **Estado:** `Cerrada (2026-08-21)`

Escribir como documento y como código las reglas que hoy están dispersas en los notebooks, y aplicar las
Decisiones 019 y su enmienda.

**El principio que ordena todas las reglas:** el nivel nunca se pierde; lo que se puede perder es el caudal
derivado de él.

| # | Regla | Criterio | Estado |
| --- | --- | --- | --- |
| R1 | Piso temporal | Gold arranca en **2000-01-01**; las 21.400 filas de 1941–1999 salen (la serie larga de nivel queda en Silver) | Implementada (31.096 → 9.729 filas) |
| R2 | Sub-cuenca | Sólo estaciones de `alta_frontera` | Implementada |
| R3 | Estación sin curva | Sin caudal derivable, **el nivel se conserva** | Implementada |
| R4 | Vigencia vencida | Se extiende la última curva hasta hoy, marcada con `curva_vigencia_extendida` | Implementada (2/22 en la cuenca alta: `70100000`, `72715000`) |
| R5 | Cota fuera de rango | Se extrapola y se marca; el registro se conserva como probable crecida real | Implementada |
| R6 | Estación íntegramente fuera de tabla | Si **toda** la serie cae fuera del rango calibrado, se descarta su caudal y queda sólo el nivel | Implementada (1 estación en todo el universo: `66400390`, outlier de datos) |
| R7 | Curva no confiable | **MAPE ≤ 30% contra aforos dentro del rango calibrado**. Resultado: 20/22 usables | Implementada (`70100000` 114,7%, `70300000` 138,2%) |
| R8 | Cobertura de fuentes | **Sin umbral de exclusión**: se publica toda estación con dato y la cobertura viaja como columna | Implementada (Fase 3: lluvia 2026-08-22, temperatura 2026-08-24) |
| R9 | Cola sin target | Se recorta **en el exportador**, por horizonte. Gold conserva las filas con target en `NULL` | Implementada (Fase 1) |

**Tareas**

- [x] `docs/gold_consolidation_contract.md` con las nueve reglas, su implementación y el conteo de filas que explica cada una.
- [x] Implementar R3, R4 y R6 en `ETL_Silver_River_Discharge_Daily.ipynb`; agregar la columna `curva_vigencia_extendida`.
- [x] Fijar el cálculo de `is_usable` en R7 (MAPE en rango, umbral 30%) y re-emitir el veredicto de las 22 estaciones de la cuenca alta.
- [x] Aplicar R1: Gold arranca en 2000-01-01. Verificar que `weather.silver.river_levels_daily` conserva la serie desde 1941.
- [x] Ampliar a 8 horizontes en `ETL_Gold_Training_Dataset_v0.ipynb`: `caudal_t_mas_{1,2,3,4,5,6,7,14}d` y sus equivalentes de nivel (16 columnas de target).
- [x] Subir los JSON del barrido cerrado al Volume y correr `Rating_Curve_Discharge_Initial_Load` → Silver → Gold en ese orden (484 archivos subidos: 407 curvas + 77 aforos; las tres tareas del job en verde).
- [x] Emitir el listado de fechas extrapoladas de la estación objetivo, como insumo para contrastar contra crónicas de crecidas al escribir la tesis (`notebooks_local/gold_export/fechas_extrapoladas.py`; hoy 0 filas).

**Criterio de cierre:** la cantidad de filas de `training_dataset_v0` se explica regla por regla, y el
veredicto de cada una de las 22 estaciones de la cuenca alta sale de una sola definición de MAPE.
**Cumplido y verificado contra Databricks real** (2026-08-21): Gold pasó de 31.096 a 9.729 filas
(2000-01-01 a 2026-08-20); `rating_curve_segments` da 20/22 estaciones `is_usable` en la cuenca
alta con un único umbral de MAPE (30%, mismo en Silver y en el reporte local); 2 estaciones con
`curva_vigencia_extendida`; 1 estación (`66400390`, fuera de la cuenca alta) descartada por R6. Ver
seguimiento en §7.

---

### Fase 3 — Lluvia y temperatura

**Estimación:** ≈ 4-6 días · **Depende de:** Fase 1 · **Estado:** `Cerrada (2026-08-24)` — lluvia cerrada 2026-08-22 (corregida en dos pasadas), temperatura cerrada 2026-08-24 (Decisión 025)

**Es el trabajo más importante del roadmap en contenido.** Sin forzante meteorológico el modelo sólo ve el
propio río. Descarga e histórico se resuelven para **toda la cuenca**; a Gold entra sólo el agregado de
`alta_frontera`, igual que el caudal.

**Dos hallazgos que condicionan el diseño**

1. **La lluvia probablemente ya está en Bronze y el portón de calidad la está borrando.**
   `ETL_Silver_Rainfall_Daily.ipynb` ya lee *todas* las estaciones de `weather.bronze.ana_rio_uruguai` — no
   está limitado al target. Su tabla quedó en 0 filas porque mide `missing_pct` sobre una ventana de 30 días
   **promediando todas las estaciones juntas**, y si supera 0,90 ejecuta un `DELETE` de todas las filas de la
   fuente. Con ~330 estaciones que reportan nivel y nunca lluvia, ese promedio global está condenado a fallar
   aunque existan estaciones con serie de lluvia excelente. Además se midió en mayo de 2026, antes de que el
   backfill histórico trajera `Chuva_Adotada` junto con `Cota_Adotada` para 361 estaciones.
2. **ANA no sirve temperatura.** El endpoint telemétrico que usa el pipeline
   (`HidroinfoanaSerieTelemetricaAdotada/v2`) devuelve `Cota_Adotada`, `Chuva_Adotada` y `Vazao_Adotada`;
   no hay campo de temperatura, porque ANA es la agencia de aguas y no la meteorológica. Las fuentes reales
   de temperatura son **METAR** de aeropuertos (ya ingestada, poblada sólo en el tramo reciente) e **INMET**,
   el instituto meteorológico brasileño, identificado en `data_sources.md` §9.3 y nunca ingestado.

**Tareas — lluvia** (cerradas 2026-08-22, Decisiones 023 y 024 — ver seguimiento en §7)

- [x] Reemplazar el portón todo-o-nada por la regla R8: publicar toda estación con dato real y exponer la cobertura como columna (`lluvia_agregado_alta_frontera_station_count`, `_cobertura_pct` en el agregado por sub-cuenca).
- [x] Eliminar el `DELETE` global de la fuente.
- [x] Re-materializar `weather.silver.rainfall_daily` en modo `full` y medir la cobertura real por estación y por año, ahora que el backfill terminó. **Hallazgo inicial (Decisión 023, 2026-08-21):** de las 22 estaciones *con curva* de `alta_frontera`, sólo 9 reportan lluvia, y sólo desde 2026-03-03. **Hallazgo corregido (Decisión 024, 2026-08-22):** ese "0 días" era un artefacto de que `weather.silver.estacion_subcuenca` sólo tenía esas 22 filas — nunca se sembró con el resto del inventario. Resembrada con las 1.387 estaciones del inventario completo (782 en `alta_frontera`), aparecen **332 estaciones con lluvia real y con historia desde 1923**. Tras re-materializar Gold: `lluvia_acumulada_mm` pasa de 1,42% a **99,65%** de filas no nulas, 100% de cobertura anual 2000-2025. La lluvia deja de ser una limitación y pasa a ser la feature externa con mejor cobertura del dataset.
- [x] Conectar `weather.silver.sg_rainfall_daily` (Salto Grande) a Gold — **resuelto por la negativa**: el inventario de estaciones SG ya trae `subcuenca_nombre` resuelto por el proveedor y ninguna cae en `alta_frontera` (59 de 69 en `baja_salto_grande`, las 10 restantes en `intermedia_paso_libres`). Conectarla violaría el alcance espacial de la Decisión 018, igual que el bug que esta fase corrigió para ANA.
- [x] Agregar lluvia por sub-cuenca y publicar en Gold sólo `alta_frontera`, con acumulados y ventanas móviles (`lluvia_agregado_alta_frontera_acum_3d_mm`, `_acum_7d_mm`).
- [x] Backfill dirigido de `Chuva_Adotada` propia para las 22 estaciones del grupo A
  (`notebooks_local/ana_historic_backfill/run_backfill_alta_frontera.py`), iniciado para investigar
  el hallazgo de la Decisión 023 — sigue corriendo (retomando ~2022, 8/22 estaciones todavía activas
  al 2026-08-22) como mejora complementaria, ya no bloqueante tras la Decisión 024.

**Tareas — temperatura** (cerradas 2026-08-24, Decisión 025 — ver seguimiento en §7)

- [x] Documentar INMET en `data_sources.md` antes de escribir código (regla de §10 de ese documento): endpoint, autenticación, cobertura, frecuencia, tabla Bronze destino. **Hecho 2026-08-22** (`data_sources.md` §9.3), contra la fuente real, no por referencia:
  catálogo de estaciones (`apitempo.inmet.gov.br/estacoes/T`) y descarga histórica masiva
  (`portal.inmet.gov.br/uploads/dadoshistoricos/{AAAA}.zip`, 2000-2026 confirmados, formato CSV
  verificado) **funcionan y fueron probados**; los endpoints incrementales documentados por
  librerías comunitarias (`inmetpy` y similares) **no funcionan hoy** (204/404 en vivo,
  2026-08-22) — API cambiada o dada de baja por INMET desde que esas integraciones se escribieron.
  La estimación inicial de "42 estaciones en la cuenca" era sólo un filtro de bounding box; el
  join espacial exacto contra los polígonos de sub-cuenca (hecho al implementar, 2026-08-24) dio
  el número real: **27 estaciones — 15 en `alta_frontera`, 12 en `intermedia_paso_libres`**.
- [x] Landing + Bronze de INMET para las estaciones de la cuenca. `notebooks_local/inmet_backfill/` (mismo patrón que `notebooks_local/ana_historic_backfill/`): backfill histórico completo 2000-2026 corrido 2026-08-24, **2.593.410 registros horarios**, 0 años fallidos. `weather.bronze.inmet` (MERGE append-only, `notebooks/02_Bronze/ETL_Bronze_INMET.ipynb`). No se implementó re-descarga periódica del ZIP como mecanismo incremental (decisión explícita, ver Decisión 025) — sin job Databricks de INMET en `databricks.yml`, sólo el backfill local.
- [x] Unificar METAR + INMET en `weather.silver.temperature_daily` con trazabilidad de origen por registro. **No hizo falta regla de prioridad**: los 4 aeropuertos METAR están geográficamente fuera de las tres sub-cuencas (confirmado con el mismo join espacial), así que METAR e INMET nunca compiten por el mismo territorio dentro de `alta_frontera`.
- [x] Medir cobertura por año, con el mismo criterio R8 que en lluvia. **Hallazgo (Decisión 025, 2026-08-24):** de las 9.732 filas de Gold, `temp_media_c` no nulo en **73,8%** (7.184 filas). Cobertura 0% en 2000-2005 (ninguna estación de `alta_frontera` operaba todavía), 9,6% en 2006, 99,2% en 2007, **100% todos los años desde 2008 hasta 2025**. Se corrigió además un bug de alcance espacial en Gold: `temp_global` promediaba los 4 aeropuertos METAR sin ningún `JOIN` a sub-cuenca (violaba R2 igual que el bug de lluvia de la Decisión 023/024, sin datos faltantes de por medio) — reemplazado por `temp_alta_frontera`, escopeado igual que lluvia y caudal.

**Criterio de cierre:** las columnas de lluvia y temperatura salen pobladas en Gold, con la cobertura de cada
una medida y documentada por año.

---

### Fase 4 — Pronóstico desde 2000: TIGGE + GEFS con empalme calibrado

**Estimación:** ≈ 6-9 días · **Depende de:** Fase 2 · **Estado:** `Pendiente`

Es la única familia de features con información del futuro: lo que separa un modelo autorregresivo de un
modelo de pronóstico. Por la Decisión 021 el pronóstico ahora cubre **desde 2000**, alineado con el piso del
dataset, en vez de arrancar en 2006-10.

**Cobertura por fuente**

| Tramo | Fuente | Nota |
| --- | --- | --- |
| 2000-01 → 2006-09 | GEFS Reforecast v12 (NOAA) | Único que cubre el hueco con pronósticos reales |
| 2006-10 → 2019 | Solapamiento GEFS + TIGGE | 13 años, se usan para calibrar el empalme |
| 2020 → hoy | TIGGE (`cf`/`pf`, ECMWF) | Backfill ya cubierto desde 2018-08 |

**Tareas**

- [ ] Documentar GEFS Reforecast v12 en `data_sources.md` antes de escribir código.
- [ ] Verificar horizonte y resolución reales de GEFS v12 contra el requisito de cubrir hasta t+14 a escala de sub-cuenca.
- [ ] Landing + Bronze de GEFS v12 **en local** (I/O contra API externa, precedente de las Decisiones 015/016), con estado resumible y lock compartido. Dimensionar el volumen: se necesita sólo precipitación sobre el bounding box de la cuenca, pero los archivos de origen son globales.
- [ ] Completar el backfill de `cf`: falta 2006-10-01 → 2018-08-02.
- [ ] Arrancar el backfill de `pf`, encadenado detrás de `cf` (comparten cola y token de TIGGE/ECDS).
- [ ] **Calibrar GEFS contra TIGGE** sobre los 13 años de solapamiento: corrección de sesgo por sub-cuenca y por horizonte, aplicada **en Silver** (regla de negocio, Decisión 011).
- [ ] Publicar **una sola serie homogénea** de pronóstico con la columna `forecast_source` declarando el origen de cada fila.
- [ ] Recortar los agregados a `alta_frontera` para lo que se publica en Gold, con features alineadas a los ocho horizontes del target.
- [ ] **Investigación acotada:** relevar qué productos de ensemble y qué parámetros de precipitación expone hoy ECMWF Open Data, que es gratuito y sin embargo (ver §5, tarea A).

**Criterio de cierre:** Gold publica features de precipitación pronosticada para `alta_frontera` de forma
continua desde 2000-01-01, con `forecast_source` y sin escalón detectable en el empalme.

---

### Fase 5 — Cadena diaria cerrada a las 06:00

**Estimación:** ≈ 1-2 días · **Depende de:** Fases 2 y 4 · **Estado:** `Pendiente`

Requisito operativo: **todos los días a las 06:00 el dataset debe tener el día anterior cerrado**, tanto para
predecir como para reentrenar y testear.

**Cadencias (Decisión 020)**

| Proceso | Cadencia | Dónde corre |
| --- | --- | --- |
| Conversión nivel → caudal de las estaciones con curva | **Diaria**, antes de Gold | Databricks |
| Descarga de curvas de aforo nuevas | **Trimestral** | Local (`download_rating_curves_batch.py`) |
| Carga a Bronze de las curvas nuevas + reproceso del caudal histórico | Trimestral, tras la descarga | Databricks |

**Orden objetivo de la cadena** (America/Montevideo)

| Hora | Proceso | Cambio |
| --- | --- | --- |
| ~23:00 (D-1) | `Temperature_Airport_Brasil` | — |
| 02:00 | `Nivel_ANA_Target` | — |
| 03:00 | `All_Estacoes_ANA_Daily` | — |
| 03:30 | `SG_Rainfall_Daily_Incremental` | — |
| 03:45 | Descarga local de `fc` (Fase 8) | **Nuevo** |
| 03:45 | `ECMWF_Forecast_Daily_Incremental` | **Adelantado** desde las 05:00 |
| 04:00 | Conversión nivel → caudal | **Nuevo eslabón diario** |
| 04:30 | `Silver_Gold_Daily_Incremental` | — |
| 05:00 | Exportación del snapshot local | **Nuevo** (Fase 1) |
| 06:00 | Dataset listo con el día anterior cerrado | Meta |

**El conflicto que resuelve esta fase.** Hoy `ECMWF_Forecast_Daily_Incremental` corre a las 08:00 UTC, o sea
05:00 Montevideo: **después** de que Gold se materializa a las 04:30. Mientras el pronóstico no entra a Gold
eso no molesta, pero al integrarlo (Fase 4) Gold estaría consumiendo el pronóstico del día anterior, con un
desfase de 24 h que no queda registrado en ninguna columna. Si la fuente no permite adelantar la descarga, la
alternativa es correr Gold detrás del pronóstico (puede moverse a las 05:15 y seguir cumpliendo la meta),
nunca dejar el pronóstico fuera de la corrida del día.

**Tareas**

- [ ] Medir a qué hora está realmente disponible cada producto y adelantar la descarga todo lo que la fuente permita.
- [ ] Encadenar la conversión nivel → caudal como task diario previo a Gold dentro de `Silver_Gold_Daily_Incremental`.
- [ ] Separar el refresco trimestral de curvas en un job propio, sin schedule diario.
- [ ] Agregar la exportación del snapshot local al final de la cadena.
- [ ] Dejar el orden completo escrito en `current_pipeline_inventory.md`, con la regla de que ningún eslabón que alimente a Gold puede correr después de Gold.

**Criterio de cierre:** tres días consecutivos en que a las 06:00 el snapshot local tiene la fila de ayer
completa, con caudal y pronóstico del ciclo correcto.

---

### Fase 6 — Reporte de calidad y diccionario de columnas

**Estimación:** ≈ 1 día · **Depende de:** Fases 2, 3 y 4 · **Estado:** `Pendiente`

Va después de las fuentes nuevas para no tener que rehacerlo.

**Tareas**

- [ ] Faltantes por columna y por año; discontinuidades temporales; verificación de fuga de target.
- [ ] Diccionario de todas las columnas con unidad, origen, regla de cálculo y rango observado. Incluye las columnas nuevas: `curva_vigencia_extendida`, `forecast_source`, `_cobertura_pct`.
- [ ] Cobertura por `caudal_metodo` y por veredicto de curva.
- [ ] Exportar al repo `notebooks/06_Quality/Validate_Training_Dataset_v0.ipynb` y `Check_Bronze_Freshness.ipynb`, que hoy sólo existen en el Workspace de Databricks (pendiente registrado en la Decisión 017).

**Criterio de cierre:** el capítulo de datos de la tesis se puede escribir desde este reporte sin volver a
consultar Databricks.

---

### Fase 7 — Ampliación del agregado de la cuenca alta

**Estimación:** ≈ 1 día · **Depende de:** Fase 2 · **Estado:** `Pendiente`

Ganancia acotada: la mayoría de las estaciones del grupo B no tiene nivel antes de ~2014, así que engrosan la
cola reciente de la serie, no los 26 años.

**Tareas**

- [ ] Traer las coordenadas de las 40 estaciones con curva del grupo B desde el inventario de ANA.
- [ ] Unión espacial contra `SIG/subcuenca_1_frontera.gpkg`.
- [ ] Sembrar en `weather.silver.estacion_subcuenca` sólo las que caigan dentro de `alta_frontera`.
- [ ] Recalcular el agregado y medir la mejora de cobertura por año.

**Criterio de cierre:** se sabe cuántas de las 40 estaciones caen en la cuenca alta y desde qué año densifican
el agregado.

---

### Fase 8 — `fc` determinístico por vía local

**Estimación:** ≈ 1-2 días + investigación · **Depende de:** Fase 4 · **Estado:** `Pendiente`

Última fase por decisión explícita. Resuelve la Decisión 013, que estaba pendiente desde el crash de
`Daily_ECMWF_FC`, moviendo el proceso a local: la causa raíz es la colisión de `cfgrib`/`eckit` con el Spark
Connect del compute serverless, que en una máquina local no existe.

**Tareas**

- [ ] **Arrancar la descarga diaria local cuanto antes**, incluso antes de completar el resto de la fase: ECMWF Open Data retiene sólo ~12 corridas (2-3 días), así que cada día sin descargar es archivo perdido de forma irrecuperable.
- [ ] Reinstalar `notebooks_local/ecmwf/landing_fc_opendata.py` (borrado en el commit `ac6deab`) y sumar su carga al script de descarga y sincronización que ya usan las demás fuentes locales.
- [ ] Encadenarlo en la cadena diaria de la Fase 5 y verificar que `cfgrib` funciona en local sin el crash.
- [ ] **Investigación acotada:** relevar si existe alguna ruta de archivo histórico de `fc` (ver §5, tarea B).
- [ ] Actualizar `data_sources.md` §7.1: `fc` deja de estar «descartado» y pasa a estar ingestado por vía local.

**Criterio de cierre:** `fc` se descarga a diario sin fallar y su archivo local crece; la ruta de historia
quedó relevada y documentada, con o sin resultado positivo.

---

## 4. Criterio de avance

Una fase se considera cerrada si produce un entregable versionado en el repositorio o una tabla trazable en
Databricks, **y** cumple su criterio de cierre. No cuenta como avance:

* probar notebooks sin salida documentada;
* agregar fuentes sin integrarlas a Gold;
* modificar código sin registrar la decisión en `decisions.md`;
* generar tablas sin validar su granularidad;
* automatizar jobs antes de cerrar el contrato de consolidación.

---

## 5. Tareas de investigación con criterio de salida definido

No son decisiones abiertas: la decisión ya está tomada y lo que falta es un dato del mundo. Cada una tiene
definido de antemano qué se hace si la investigación no encuentra lo que busca, para que ninguna fase quede
bloqueada esperando a un tercero.

**A · Acceso al pronóstico en tiempo real** (Fase 4)
Relevar qué productos de ensemble y qué parámetros de precipitación expone hoy ECMWF Open Data, que es
gratuito y sin embargo — es de donde ya sale `fc`. La nota de `data_sources.md` §7 dice que `tp` para
`cf`/`pf` no estaba disponible ahí, pero el catálogo cambió varias veces desde entonces.
*Criterio de salida:* se usa Open Data. **No se contrata ninguna vía paga.** Si Open Data no alcanza, se
convive con la latencia de TIGGE y cada fila declara `forecast_age_days`, de modo que el modelo entrene con
la misma latencia que tendrá en operación y la métrica reportada sea honesta.

**B · Historia de `fc`** (Fase 8)
Relevar si existe alguna ruta de archivo histórico de `fc` (Service Agreement / MARS con acuerdo académico
institucional, u otro endpoint de ECMWF).
*Criterio de salida:* si no hay ruta viable, el lugar del pronóstico determinístico lo ocupa el **GEFS
operativo de NOAA**, cuyo reforecast 2000–2019 ya estará ingestado por la Fase 4 — con lo cual entrenamiento
y operación quedan sobre el mismo modelo. **El reemplazo aplica únicamente a `fc`**: el ensemble sigue siendo
de ECMWF (`cf`/`pf`), no se migra a NOAA.

**C · Horizonte y resolución de GEFS v12** (Fase 4)
Verificar contra la fuente que la cobertura ~2000–2019 llega hasta t+14 con resolución útil a escala de
sub-cuenca, y dimensionar el volumen de descarga.
*Criterio de salida:* si no llega a t+14, los horizontes largos quedan sin feature de pronóstico en el tramo
2000–2006 y se documenta como limitación de cobertura por horizonte, sin mover el piso del dataset.

---

## 6. Fuera de alcance

| Tema | Motivo |
| --- | --- |
| Segundo punto de predicción aguas abajo (CARU / Salto Grande) | Decisión 018 |
| Agregados de caudal de `intermedia_paso_libres` y `baja_salto_grande` | Decisión 018 — columnas reservadas en `NULL` |
| Baseline y pipeline de entrenamiento | Fase posterior del proyecto, no del dataset |
| ERA5 como fuente de pronóstico | Es reanálisis, no pronóstico: sobrestimaría la habilidad del modelo (Decisión 021) |
| Investigar los coeficientes de `70100000` y `70300000` | Conservan su nivel; sólo pierden el caudal (Decisión 019, enmienda) |
| Serie de nivel 1941–1999 dentro de Gold | Gold arranca en 2000; la serie queda completa en `weather.silver.river_levels_daily` |
| Granularidad horaria | Evaluable recién si el dataset diario demuestra viabilidad (Decisión 003) |
| Migración a PostgreSQL o Spark local | Decisiones 007 y 008 |
| `cfgrib` dentro de Databricks serverless | Sin solución conocida en este workspace; el pipeline dejó de necesitarlo (Decisión 022) |

---

## 7. Seguimiento de fases cerradas

Cada fase se cierra con su propio test (unitario si el código corre local, notebook de
`06_Quality` si corre en Databricks) antes de abrir la PR de esa fase. Esta tabla registra
dónde vive ese test y qué quedó pendiente de verificar contra el entorno real.

| Fase | Test | Estado | Pendiente |
| --- | --- | --- | --- |
| Fase 1 — Exportador local de Gold | `notebooks_local/gold_export/test_export_gold_dataset.py` (20 casos: filtros, regla R9, resumen, corte por versión Delta, lock compartido) — corre offline con `python -m pytest`; verificado además contra el Volume real (`Export_Gold_Snapshot` corrido en Databricks + `export_gold_dataset.py --resumen`/`--desde`/`--confiable`/`--horizonte` corridos contra el snapshot descargado) | Verde, local y contra Databricks real | Ninguno. Se creó el Volume `weather.raw.gold_export_volume` (no existía) y se corrigió el nombre en el código para seguir la convención `<fuente>_volume` del resto de `weather.raw`. |
| Fase 2 — Contrato de consolidación y regeneración de Gold | `notebooks/06_Quality/Validate_River_Discharge.ipynb` y `Validate_Training_Dataset_v0.ipynb`, ambos como task final de sus jobs (`Rating_Curve_Discharge_Initial_Load` y `Silver_Gold_Initial_Load_v0`) — corridos en Databricks real, 3/3 y 7/7 tareas en verde respectivamente; verificado además con consultas SQL ad hoc contra `weather.silver.rating_curve_segments`/`river_discharge_daily` (warehouse serverless `Serverless Starter Warehouse`) y con `export_gold_dataset.py --refresh --resumen` / `fechas_extrapoladas.py --offline` contra el snapshot local | Verde, local y contra Databricks real | Ninguno. `docs/gold_consolidation_contract.md` documenta las nueve reglas con los conteos reales. |
| Fase 3 (lluvia) — R8 sin umbral, agregado por sub-cuenca | `Validate_Training_Dataset_v0.ipynb` extendido con dos asserts nuevos (cobertura en `[0,1]`, `lluvia_is_usable` deprecada en `NULL`) — corrido en Databricks real dentro de `Silver_Gold_Initial_Load_v0` dos veces: 2026-08-21 (7/7 tareas en verde, versión Delta 244, con `estacion_subcuenca` todavía en 22 filas) y 2026-08-22 tras la Decisión 024 (7/7 en verde, `estacion_subcuenca` resembrada a 1.387 filas antes de correr el job); verificado además con consultas SQL ad hoc contra `weather.silver.rainfall_daily`/`estacion_subcuenca` y `weather.gold.training_dataset_v0` (warehouse serverless, vía `databricks api post /api/2.0/sql/statements`) | Verde, local (sintaxis) y contra Databricks real | Ninguno en el código. **Cerrado 2026-08-22:** el hallazgo "sólo 9/22 estaciones con lluvia desde 2026-03-03" (Decisión 023) era un artefacto de que `estacion_subcuenca` sólo tenía 22 filas; resembrada con el inventario completo (1.387 estaciones), la cobertura real de `alta_frontera` es 332 estaciones con lluvia desde 1923, y `lluvia_acumulada_mm` en Gold pasa a 99,65% no nulo (Decisión 024). El backfill dirigido a las 22 estaciones del grupo A (`run_backfill_alta_frontera.py`) sigue corriendo en background como mejora complementaria, no bloqueante. Nota operativa: los notebooks de este repo se sincronizan al Databricks Repo (`/Workspace/Users/joaquintschopp@gmail.com/rio-uruguay-hydro-pipeline`, git-linked a `main`) con `databricks workspace import --format JUPYTER --overwrite`, no con `databricks bundle deploy` (ese comando sólo sube a `.bundle/.../files`, un path que ningún job lee) — repetir este paso en cualquier sesión futura que edite notebooks antes de correr jobs. |
| Fase 3 (temperatura) — INMET + R8 sin umbral, escopeo a `alta_frontera` | `Validate_Training_Dataset_v0.ipynb` extendido con el assert de cobertura en `[0,1]` para `temp_agregado_alta_frontera_cobertura_pct` — corrido en Databricks real dentro de `Silver_Gold_Initial_Load_v0` (2026-08-24, `load_mode=full`, 8/8 tareas en verde tras reparar dos fallos encontrados en el camino, ver Decisión 025); verificado además con consultas SQL ad hoc contra `weather.bronze.inmet`/`weather.silver.temperature_daily`/`estacion_subcuenca`/`weather.gold.training_dataset_v0` (warehouse serverless, vía `databricks api post /api/2.0/sql/statements`) y con `export_gold_dataset.py --refresh --resumen` contra el snapshot local | Verde, local y contra Databricks real | Ninguno en el código. **Cerrado 2026-08-24:** backfill INMET completo (27 estaciones de la cuenca, 2.593.410 registros horarios, 2000-2026); `temp_media_c` en Gold pasa de temperatura nacional (bug de alcance, nunca escopeada a sub-cuenca) a 73,8% no nulo real de `alta_frontera`, 100% de cobertura diaria 2008-2025. Dos bugs de ejecución encontrados y corregidos: (1) INMET cambia el separador de fecha de `-` a `/` a partir de 2019, rompía `to_timestamp`; (2) la migración de esquema de `temperature_daily` (agregar `estacion_id`/`fuente` a una tabla ya poblada) dejó ~47.000 filas METAR huérfanas con `estacion_id = NULL` que no matcheaban el nuevo `MERGE` — se limpiaron con un `DELETE` antes de reintentar. Detalle completo en la Decisión 025. |
