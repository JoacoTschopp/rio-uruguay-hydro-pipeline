# Roadmap del dataset de tesis

Fecha de corte: **2026-08-21**
Rama de trabajo: `feature/ana-backfill-automation`
Entregable final del roadmap: `weather.gold.training_dataset_v0` cerrado, documentado y descargable en local.

Este documento reemplaza a los planes anteriores (`thesis_dataset_roadmap.md`,
`rating_curve_discharge_plan.md`, `silver_gold_jobs_plan.md`, `sg_rainfall_ingestion_plan.md`), que fueron
retirados del repositorio. Lo que esos planes tenían de conocimiento consolidado vive ahora en
`decisions.md` (por qué se hizo cada cosa) y en `current_pipeline_inventory.md` /
`silver_gold_implementation_status.md` (qué quedó desplegado).

---

## 1. Objetivo y alcance

Construir un dataset diario, reproducible y documentado para predecir el **caudal (m³/s) del Río Uruguay**
en la estación objetivo, con horizontes de 1 a 7 días y 14 días.

| Dimensión | Definición |
| --- | --- |
| Variable objetivo | Caudal en m³/s (el nivel se conserva como target secundario) |
| Punto de predicción | `ana_74100000` — Irai, frontera Brasil/Argentina |
| Horizontes | t+1, t+2, t+3, t+4, t+5, t+6, t+7, t+14 |
| Granularidad | Diaria. Grano lógico `fecha + punto_prediccion` |
| Alcance espacial en Gold | **Sólo la sub-cuenca `alta_frontera`** (Decisión 018) |
| Alcance espacial de la ingesta | Toda la cuenca, las tres sub-cuencas |
| Piso temporal del caudal | 2000-01-01 |

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
decisión es reversible sin volver a descargar nada: revertirla es levantar el filtro en el notebook de Gold y
sembrar `weather.silver.estacion_subcuenca` con las estaciones de las otras dos sub-cuencas.

---

## 2. Estado al 2026-08-21 — qué ya está terminado

| Bloque | Estado | Evidencia |
| --- | --- | --- |
| Landing + Bronze (ANA, METAR, Salto Grande, ECMWF) | Operativo | 5 jobs diarios en `databricks.yml` |
| Silver: niveles, temperatura, lluvia, ECMWF, caudal | Materializado | `silver_gold_implementation_status.md` |
| Gold `training_dataset_v0` | Materializado y validado | 31.094 filas, 0 duplicados, 0 mismatches de target |
| Conversión nivel → caudal por curva vigente | Implementada | Decisión 017 · 210.106 filas en `river_discharge_daily` |
| Backfill histórico ANA (nivel + lluvia) | **Completo** | 361 estaciones agotadas, 0 activas, 248 archivos sincronizados |
| Barrido de curvas de aforo, toda la cuenca | **Completo** | 392 estaciones, 0 errores, `pendientes = 0` |

### Resultado del barrido de curvas

| Veredicto | Estaciones | Efecto |
| --- | ---: | --- |
| `usable` (MAPE ≤ 20%) | 19 | Nivel + caudal |
| `usable_sin_validacion` | 35 | Fuera de la cuenca alta |
| `usable_con_huecos` | 5 | Fuera de la cuenca alta |
| `sospechosa` (MAPE > 20%) | 3 | Nivel sí, caudal fuera del agregado |
| `sin_curva` | 330 | Sólo nivel |
| **Total barrido** | **392** | 62 con curva · 1.235 segmentos · 2.270 aforos |

De las 62 estaciones con curva, **25 tienen la vigencia vencida**; 2 de ellas en la cuenca alta
(`70100000` y `72715000`, ambas vencidas el 2023-12-31).

---

## 3. Fases

Ordenadas por relación entregable/tiempo. Las estimaciones son en días de trabajo efectivo.

### Fase 1 — Exportador local del dataset Gold

**Estimación:** ≈ 0,5 día · **Depende de:** nada · **Estado:** `Pendiente`

Va primera por rápida y porque es el instrumento para auditar todo lo demás: sin poder abrir la tabla en
pandas, las reglas de la Fase 2 y la calidad de lluvia de la Fase 3 se deciden a ciegas.

**Diseño.** Un task final del job de Gold escribe un Parquet único en
`/Volumes/weather/raw/gold_export/`; el script local lo baja con `databricks fs cp`, el mismo camino de
autenticación que ya usa `notebooks_local/ana_historic_backfill/sync_to_databricks.py`. No requiere un SQL
warehouse encendido, en línea con el criterio de costo de la Decisión 016.

**Tareas**

- [ ] Task `Export_Gold_Snapshot` al final del job de Gold: escribe Parquet + `manifest.json`.
- [ ] `notebooks_local/gold_export/export_gold_dataset.py` con la interfaz:
  `--refresh`, `--desde`, `--solo-caudal`, `--confiable`, `--horizonte {1..7,14}`, `--formato parquet|csv`, `--resumen`.
- [ ] Manifiesto con versión Delta de origen, filas, rango de fechas, columnas, hash del archivo y fecha de exportación.
- [ ] Corte por versión Delta: si no cambió, no vuelve a bajar.
- [ ] Lock compartido (`lock.py`) con las tareas de ANA, para no solaparse.

**Criterio de cierre:** `python export_gold_dataset.py --resumen` imprime filas, rango de fechas, faltantes
por columna y cobertura por `caudal_metodo` sin abrir Databricks.

---

### Fase 2 — Contrato de consolidación y regeneración de Gold

**Estimación:** ≈ 2 días · **Depende de:** Fase 1 (para auditar el resultado) · **Estado:** `Pendiente`

Escribir como documento y como código las reglas que hoy están dispersas en los notebooks, aplicar las
decisiones nuevas (Decisión 019) y ampliar a 8 horizontes.

**El principio que ordena todas las reglas:** el nivel nunca se pierde; lo que se puede perder es el caudal
derivado de él.

| # | Regla | Criterio | Estado |
| --- | --- | --- | --- |
| R1 | Piso temporal | Sin caudal antes de 2000-01-01 | Implementada |
| R2 | Sub-cuenca | Sólo estaciones de `alta_frontera` | A formalizar |
| R3 | Estación sin curva | Sin caudal derivable, **el nivel se conserva** | Nueva |
| R4 | Vigencia vencida | Se extiende la última curva hasta hoy, marcada con `curva_vigencia_extendida` | Nueva |
| R5 | Cota fuera de rango | Se extrapola y se marca; el registro se conserva | Implementada |
| R6 | Estación íntegramente fuera de tabla | Si **toda** la serie cae fuera del rango calibrado, se descarta su caudal y queda sólo el nivel | Nueva |
| R7 | Curva no confiable | `is_usable = false` ⇒ el caudal sale del agregado; el nivel se conserva | Umbral abierto |
| R8 | Fuente con faltantes | `missing_pct > 0,90` ⇒ columna en `NULL` — **el criterio se rediseña en la Fase 3** | A rediseñar |
| R9 | Cola sin target | Cada horizonte pierde sus últimos *h* días | Sin implementar |

**Tareas**

- [ ] `docs/gold_consolidation_contract.md` con las nueve reglas, su implementación y el conteo de filas que explica cada una.
- [ ] Implementar R3, R4 y R6 en `ETL_Silver_River_Discharge_Daily.ipynb`; agregar la columna `curva_vigencia_extendida`.
- [ ] Ampliar a 8 horizontes en `ETL_Gold_Training_Dataset_v0.ipynb`: `caudal_t_mas_{1,2,3,4,5,6,7,14}d` y sus equivalentes de nivel (16 columnas de target).
- [ ] Cerrar la definición única de MAPE / `is_usable` (ver §5, punto abierto 1) y re-emitir el veredicto de las 22 estaciones de la cuenca alta.
- [ ] Subir los JSON del barrido cerrado al Volume y correr `Rating_Curve_Discharge_Initial_Load` → Silver → Gold en ese orden.
- [ ] Emitir el listado de fechas extrapoladas de la estación objetivo, como insumo para contrastar contra crónicas de crecidas al escribir la tesis.

**Criterio de cierre:** la cantidad de filas de `training_dataset_v0` se explica regla por regla, y el
veredicto de cada una de las 22 estaciones de la cuenca alta sale de una sola definición de MAPE.

---

### Fase 3 — Lluvia y temperatura

**Estimación:** ≈ 4-6 días · **Depende de:** Fase 1 · **Estado:** `Pendiente`

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

**Tareas — lluvia**

- [ ] Rediseñar el portón de calidad: medir `missing_pct` **por estación** sobre toda la serie, no un promedio global sobre 30 días. Publicar las estaciones que pasan y descartar sólo las que no.
- [ ] Sustituir el `DELETE` todo-o-nada por un filtro por estación.
- [ ] Re-materializar `weather.silver.rainfall_daily` en modo `full` y medir la cobertura real ahora que el backfill terminó.
- [ ] Conectar `weather.silver.sg_rainfall_daily` (Salto Grande) a Gold — está en Silver y nunca llegó al dataset.
- [ ] Agregar lluvia por sub-cuenca y publicar en Gold sólo `alta_frontera`, con features de acumulado y ventanas móviles.

**Tareas — temperatura**

- [ ] Documentar INMET en `data_sources.md` antes de escribir código (regla de §10 de ese documento): endpoint, autenticación, cobertura, frecuencia, tabla Bronze destino.
- [ ] Landing + Bronze de INMET para las estaciones de la cuenca.
- [ ] Unificar METAR + INMET en `weather.silver.temperature_daily` con prioridad de fuente y trazabilidad de origen por registro.
- [ ] Medir cobertura por año y aplicar el mismo criterio por estación que en lluvia.

**Criterio de cierre:** las columnas de lluvia y temperatura salen pobladas en Gold con cobertura medida y
documentada por año, o bien queda escrita la exclusión definitiva con la evidencia que la sostiene.

---

### Fase 4 — Pronóstico ECMWF: histórico e integración a Gold

**Estimación:** ≈ 3-5 días · **Depende de:** Fase 2 · **Estado:** `Pendiente`

Es la única familia de features con información del futuro: lo que separa un modelo autorregresivo de un
modelo de pronóstico. La Decisión 018 reduce el trabajo de tres sub-cuencas a una.

**Tareas**

- [ ] Completar el backfill de `cf`: falta 2006-10-01 → 2018-08-02 (cobertura actual 2018-08-03 → hoy).
- [ ] Arrancar el backfill de `pf`, encadenado detrás de `cf` (comparten cola y token de TIGGE/ECDS).
- [ ] Recortar los agregados por sub-cuenca a `alta_frontera` para lo que se publica en Gold.
- [ ] Features de precipitación pronosticada alineadas con los ocho horizontes del target.
- [ ] **Medir la latencia real de disponibilidad por producto** y registrar la edad del pronóstico usado en una columna `forecast_age_days` (ver §5, punto abierto 2).

**Criterio de cierre:** Gold publica features de precipitación pronosticada para `alta_frontera` con serie
histórica desde 2006-10, y cada fila declara la edad del pronóstico del que salieron.

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
| 03:45 | `ECMWF_Forecast_Daily_Incremental` | **Adelantado** desde las 05:00 |
| 04:00 | Conversión nivel → caudal | **Nuevo eslabón diario** |
| 04:30 | `Silver_Gold_Daily_Incremental` | — |
| 05:00 | Exportación del snapshot local | **Nuevo** (Fase 1) |
| 06:00 | Dataset listo con el día anterior cerrado | Meta |

**El conflicto que resuelve esta fase.** Hoy `ECMWF_Forecast_Daily_Incremental` corre a las 08:00 UTC, o sea
05:00 Montevideo: **después** de que Gold se materializa a las 04:30. Mientras el pronóstico no entra a Gold
eso no molesta, pero al integrarlo (Fase 4) Gold estaría consumiendo el pronóstico del día anterior, con un
desfase de 24 h que no queda registrado en ninguna columna — el tipo de error que después aparece como una
señal rara en el modelo y cuesta semanas rastrear.

**Decisión adoptada:** si el ciclo está disponible en ECMWF antes de la hora de descarga actual, se adelanta
la descarga y el pronóstico entra a Gold **antes del volcado**. Si la medición de latencia muestra que no
está disponible tan temprano, la alternativa es correr Gold detrás del pronóstico (Gold puede moverse a las
05:15 y seguir cumpliendo la meta de las 06:00), nunca dejar el pronóstico fuera de la corrida del día.

**Tareas**

- [ ] Medir a qué hora está realmente disponible cada producto y adelantar `ECMWF_Forecast_Daily_Incremental` todo lo que la fuente permita.
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
- [ ] Diccionario de todas las columnas con unidad, origen, regla de cálculo y rango observado.
- [ ] Cobertura por `caudal_metodo` y por veredicto de curva.
- [ ] Exportar al repo `notebooks/06_Quality/Validate_Training_Dataset_v0.ipynb` y `Check_Bronze_Freshness.ipynb`, que hoy sólo existen en el Workspace de Databricks (pendiente registrado en la Decisión 017).

**Criterio de cierre:** el capítulo de datos de la tesis se puede escribir desde este reporte sin volver a
consultar Databricks.

---

### Fase 7 — Ampliación del agregado de la cuenca alta

**Estimación:** ≈ 1 día · **Depende de:** Fase 2 · **Estado:** `Pendiente`

Va última porque su ganancia es acotada: la mayoría de las estaciones del grupo B no tiene nivel antes de
~2014, así que engrosan la cola reciente de la serie, no los 26 años.

**Tareas**

- [ ] Traer las coordenadas de las 40 estaciones con curva del grupo B desde el inventario de ANA.
- [ ] Unión espacial contra `SIG/subcuenca_1_frontera.gpkg`.
- [ ] Sembrar en `weather.silver.estacion_subcuenca` sólo las que caigan dentro de `alta_frontera`.
- [ ] Recalcular el agregado y medir la mejora de cobertura por año.

**Criterio de cierre:** se sabe cuántas de las 40 estaciones caen en la cuenca alta y desde qué año densifican
el agregado.

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

## 5. Puntos abiertos

1. **Definición única de MAPE / `is_usable`.** El reporte local calcula `70100000` = 86% y `70300000` = 111%;
   la validación en Silver registró 123% y 138% para las mismas estaciones. La diferencia está en qué aforos
   entran en la comparación (todos vs. sólo los que caen dentro del rango calibrado). Hay que elegir una sola
   definición: es la que decide qué estación entra al agregado de la cuenca alta. **Se resuelve en la Fase 2.**
2. **Latencia real del pronóstico.** TIGGE (`cf`/`pf`, vía `cdsapi`) documenta un embargo para acceso público
   que puede llegar a ~48 h. Si se confirma, el pronóstico que entra a Gold no es el del día sino el del ciclo
   disponible más reciente, y eso cambia el significado operativo del modelo. Se mide en la Fase 4 y se
   registra en `forecast_age_days`; no se asume ni a favor ni en contra hasta medirlo.
3. **`Daily_ECMWF_FC` sigue roto** por la colisión `cfgrib`/`eckit` con Spark Connect en serverless
   (Decisión 013, causa raíz identificada, sin fix disponible en este workspace). No bloquea el roadmap porque
   `cf`/`pf` usan netCDF y no pasan por `cfgrib`.
4. **El barrido local de curvas está por delante de Databricks:** 510 segmentos y 2.270 aforos en local contra
   509 y 1.737 en la última carga registrada. Se reconcilia en la Fase 2.

---

## 6. Fuera de alcance

| Tema | Motivo |
| --- | --- |
| Segundo punto de predicción aguas abajo (CARU / Salto Grande) | Decisión 018 |
| Agregados de caudal de `intermedia_paso_libres` y `baja_salto_grande` | Decisión 018 — columnas reservadas en `NULL` |
| Baseline y pipeline de entrenamiento | Fase posterior del proyecto, no del dataset |
| Histórico de `fc` (HRES determinístico) | Sin archivo público; requiere Service Agreement / MARS (Decisión 012) |
| Pronóstico anterior a 2006-10 | Límite real de la fuente TIGGE (Decisión 012) |
| Granularidad horaria | Evaluable recién si el dataset diario demuestra viabilidad (Decisión 003) |
| Migración a PostgreSQL o Spark local | Decisiones 007 y 008 |
