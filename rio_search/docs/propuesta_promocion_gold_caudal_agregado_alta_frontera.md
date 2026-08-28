# Propuesta de promoción a Gold: `caudal_agregado_alta_frontera_m3s`

Fase 9 (Extensibilidad probada y promoción a Gold), `docs/rio_search_plan.md` §3.6, §5, §2.1.

**Estado: propuesta documentada, NO aplicada.** Este documento no modifica ningún notebook de
Databricks (sólo se leyó `notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb` para citarlo con
precisión) ni ejecuta nada contra `weather.gold.training_dataset_v0`. Los pasos de la sección
"Cómo aplicarla" quedan para que el usuario los ejecute cuando decida.

## 1. Qué columna y por qué

`weather.gold.training_dataset_v0.caudal_agregado_alta_frontera_m3s` (feature, no target) es la
suma diaria de `caudal_m3s` de todas las estaciones ANA que `weather.silver.estacion_subcuenca`
ubica en la subcuenca `alta_frontera` (notebook citado abajo, bloque `subcuenca_daily`). El plan
(§2.1) ya señalaba un outlier de 823.897 m³/s en 2023 y proponía dos caminos distintos para dos
capas distintas: en la app, un transform experimental `clip`/`winsor`; en Gold, "candidata a
promoción... filtrando por `caudal_confiable`". Este documento verifica ambos con datos reales y
recomienda **sólo el primero** para promoción inmediata, dejando el segundo documentado como
alternativa de mayor alcance para una Decisión futura separada (§4 abajo).

## 2. Evidencia real (Rio_Search + Databricks, no hipotética)

### 2.1. El snapshot descargado por Rio_Search confirma el outlier y su magnitud

Sobre `rio_search/backend/data/gold_snapshot/training_dataset_v0.parquet` (delta_version 268, el
mismo que usan las corridas reales de `bilstm_baseline_v1.yaml`/`ridge_baseline_v1.yaml`, Fase 9),
con Polars:

| Estadístico | Valor |
| --- | --- |
| Filas no nulas | 9.697 / 9.732 |
| Máximo | 823.897,75 m³/s (2023-05-06) |
| p99 / p999 (serie completa, contaminada) | 789.249 / 793.763 m³/s |
| Filas > 50.000 m³/s | **218** (no 1 solo día) |
| Máximo excluyendo filas > 50.000 | **48.617,30 m³/s** |
| p999 excluyendo filas > 50.000 | 39.802,79 m³/s |

Es decir: la serie "limpia" (sin las 218 filas contaminadas) nunca supera **48.617 m³/s** en todo
el histórico (2000-2026). Un `clip`/`winsor` con techo **50.000 m³/s** no recorta ningún valor
legítimo observado — queda justo por encima del máximo histórico limpio — y sólo afecta las 218
filas contaminadas. Este es el mismo valor (`max: 50000`) que ya usa el transform experimental
`clip` en `configs/experiments/bilstm_baseline_v1.yaml` (Fase 3) y
`configs/experiments/ridge_baseline_v1.yaml` (Fase 9): no fue un número arbitrario, este análisis
lo confirma post-hoc con el dataset real.

### 2.2. Las 218 filas contaminadas no son un evento aislado: son 4 episodios de curva no confiable

Las 218 filas > 50.000 m³/s se agrupan en 4 ventanas, no una:

| Ventana | Días | Máximo |
| --- | --- | --- |
| 2023-01-17 → 2023-08-01 | 197 | 823.897,75 m³/s |
| 2024-01-15 → 2024-01-31 | 8 | 347.896,02 m³/s |
| 2025-02-28 → 2025-03-01 | 2 | 199.242,82 m³/s |
| 2025-07-15 → 2025-07-23 | 9 | 149.351,89 m³/s |

Consulta SQL real (Statement API, read-only, vía `DatabricksStatementExecutor` — el mismo cliente
que usa `GoldSnapshotSync`, sin tocar ningún notebook) contra
`weather.silver.river_discharge_daily` + `weather.silver.estacion_subcuenca`:

```sql
SELECT d.codigoestacao, count(*) as n, min(d.fecha) as min_fecha, max(d.fecha) as max_fecha,
       sum(case when d.caudal_confiable then 1 else 0 end) as n_confiable_true,
       max(d.caudal_m3s) as max_caudal
FROM weather.silver.river_discharge_daily d
JOIN weather.silver.estacion_subcuenca sc ON d.codigoestacao = sc.codigoestacao
WHERE sc.subcuenca = 'alta_frontera' AND d.caudal_m3s > 50000
GROUP BY d.codigoestacao ORDER BY n DESC
```

Resultado real:

| `codigoestacao` | filas > 50.000 | rango de fechas | `n_confiable_true` |
| --- | --- | --- | --- |
| `73340000` | 197 | 2023-01-17 → 2023-08-01 | **0** |
| `71890500` | 8 | 2024-01-15 → 2024-01-31 | **0** |
| `73204000` | 9 | 2025-07-15 → 2025-07-23 | **0** |
| `73330250` | 2 | 2025-02-28 → 2025-03-01 | **0** |

**Las 218 filas contaminadas tienen `caudal_confiable = false` en el 100 % de los casos, sin
excepción, en 4 estaciones distintas.** Para la estación dominante (`73340000`, el episodio de
2023), `caudal_metodo = 'extrapolado_superior'` en todas las filas del episodio: la lectura está
extrapolada por encima del rango calibrado de la curva de aforo (exactamente lo que el plan §2.1
llamaba "curva no confiable"). El resto de las estaciones de la subcuenca ese mismo día están en
el rango normal (decenas a pocos cientos de m³/s); el `Sum` sin filtrar suma una lectura de una
sola estación, con curva fuera de rango, que es ~100-1000x el resto.

### 2.3. `caudal_confiable` ya viaja al agregado, pero como metadato, no como filtro

El bloque real del notebook (`notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb`, celda de
código índice 3 — la 4ª celda del notebook —, líneas 129-137 de su `source`):

```python
subcuenca_daily = (
    spark.table(DISCHARGE_TABLE).alias('d')
    .join(spark.table(SUBCUENCA_TABLE).alias('sc'), 'codigoestacao', 'inner')
    .groupBy('fecha', 'subcuenca')
    .agg(
        F.sum('caudal_m3s').alias('caudal_agregado_m3s'),
        F.avg(F.col('caudal_confiable').cast('double')).alias('confiable_pct'),
    )
)
```

Ya calcula `confiable_pct` (fracción de estaciones contribuyentes marcadas confiables ese día) pero
**no lo usa para excluir nada de la suma** — `F.sum('caudal_m3s')` sigue sumando también las
lecturas con `caudal_confiable = false`. `caudal_agregado_alta_frontera_confiable_pct` en Gold ya
avisa (0,80-0,87 en los días contaminados, vs. valores más altos en días limpios) pero nada aguas
abajo lo lee como filtro — ni la propia Gold, ni (hasta ahora) la app.

### 2.4. Verificación cuantitativa del efecto de filtrar por `caudal_confiable`

Consulta real (mismo cliente, read-only) comparando la suma actual contra una suma que excluye
`caudal_confiable = false`:

| Fecha | Suma actual (Gold hoy) | Suma si se excluye `caudal_confiable=false` |
| --- | --- | --- |
| 2023-01-19 (contaminado) | 792.308,87 m³/s | **1.966,88 m³/s** |
| 2023-05-06 (máximo histórico) | 823.897,75 m³/s | **4.329,34 m³/s** |
| 2023-08-02 (día "limpio" adyacente) | 3.038,10 m³/s | 1.638,99 m³/s |
| 2022-12-01 (día "limpio", sin episodio) | 2.674,21 m³/s | 1.856,01 m³/s |

Los dos primeros confirman que filtrar por `caudal_confiable` resuelve el outlier extremo
(vuelve a un rango fisicamente plausible, consistente con estaciones vecinas). Los dos últimos
muestran algo que el plan no anticipaba: **incluso en días sin ningún episodio extremo, la suma
actual ya incluye lecturas de estaciones no confiables** (`caudal_agregado_alta_frontera_confiable_pct`
ronda 0,83-0,86 casi todo el histórico, no sólo en los 4 episodios) — filtrar por `caudal_confiable`
cambiaría el valor de la columna en una fracción sustancial de los ~9.700 días, no sólo en los 218
contaminados. Es la corrección más correcta hidrológicamente, pero de **alcance mucho mayor** que
"sacar 4 episodios": redefine la semántica de la columna para todo el histórico.

## 3. Recomendación para esta promoción: `clip`/`winsor`, no el filtro por `caudal_confiable`

Por lo de arriba, y siguiendo el criterio "más simple y seguro" pedido para esta fase:

* **Se recomienda promover el `clip`/`winsor`** (acotar `caudal_agregado_alta_frontera_m3s` a un
  techo, no excluir lecturas de la suma): es un cambio de **alcance acotado** (sólo toca las 218
  filas ya identificadas como contaminadas, el 97,8% de la serie no cambia de valor) y **reversible**
  (una sola expresión `.withColumn`, fácil de auditar en el diff del notebook).
* **No se recomienda promover el filtro por `caudal_confiable`** en esta pasada: es la corrección
  más correcta a largo plazo (§2.4), pero cambia el valor de la columna en una fracción grande del
  histórico completo (no sólo los 218 días contaminados) — un cambio de esa escala en una columna
  ya usada por baselines registrados (BiLSTM v9-12 en `weather.ml.rio_search_bilstm`, campeón
  provisorio, Decisión 046) merece su propia Decisión y su propia re-evaluación de esos runs, no
  agruparse con esta promoción. Queda documentado como alternativa futura, no descartado (§4).

### 3.1. Cambio exacto en PySpark propuesto (celda 4, después del bloque `subcuenca_wide`)

El notebook arma `subcuenca_wide` uniendo `caudal_agregado_{subcuenca}_m3s` para las 3 subcuencas
(líneas ~139-148 de la celda). La promoción agrega un `.withColumn` que acota **sólo** la columna
de `alta_frontera` (las otras dos subcuencas, `intermedia_paso_libres`/`baja_salto_grande`, están
fuera de alcance de la tesis por Decisión 018 — este documento no analizó si tienen el mismo
problema):

```python
# Antes (linea ~148, cierre del loop de subcuenca_wide):
    subcuenca_wide = subcuenca_wide.join(one, 'fecha', 'left')

# Despues (agregar inmediatamente despues del loop, antes de "base = ("):
MAX_CAUDAL_AGREGADO_ALTA_FRONTERA_M3S = 50000  # Decision <NNN> (docs/decisions.md):
    # p999 de la serie sin contaminar = 39.802,79 m3/s, maximo sin contaminar = 48.617,30 m3/s
    # (verificado sobre el snapshot real de Rio_Search, delta_version 268) -- ningun valor
    # legitimo observado en 2000-2026 supera este techo; las 218 filas que si lo superan tienen
    # caudal_confiable=false en el 100% de los casos en weather.silver.river_discharge_daily
    # (4 estaciones, 4 episodios de curva fuera de rango, el mayor: 73340000, 2023-01-17 a
    # 2023-08-01, caudal_metodo='extrapolado_superior').
subcuenca_wide = subcuenca_wide.withColumn(
    'caudal_agregado_alta_frontera_m3s',
    F.least(F.col('caudal_agregado_alta_frontera_m3s'), F.lit(MAX_CAUDAL_AGREGADO_ALTA_FRONTERA_M3S)),
)
```

`F.least(col, lit(techo))` dejar pasar todo valor `<= 50000` intacto y acota (nunca eleva) los
valores por encima — un clip clásico de un solo lado (la columna es un caudal, no tiene valores
negativos que también acotar). Los `lag_1d/lag_2d/lag_3d` de `caudal_agregado_alta_frontera_*` se
calculan **después** de este bloque (líneas ~205-210 de la celda, `F.lag(col_m3s, N).over(w)`), así
que automáticamente heredan el valor ya acotado sin tocar ese bloque aparte.

### 3.2. Consecuencia sobre el histórico y necesidad de regeneración

Este cambio altera el valor de `caudal_agregado_alta_frontera_m3s` (y sus 3 columnas de lag) para
las 218 filas ya identificadas — **requiere una corrida `full`** del notebook (widget `load_mode`,
no `incremental`: el modo incremental no reprocesa fechas ya materializadas) para que el histórico
completo de Gold refleje el cambio, igual que la regeneración de MERGE/SAMeT documentada
previamente (ver `notebooks_local/ecmwf`/Fase 9 CPTEC en el historial del proyecto).

## 4. Alternativa de mayor alcance, documentada para una Decisión futura (no esta)

Filtrar la suma por `caudal_confiable` (§2.3-2.4) es la corrección hidrológicamente más correcta:

```python
# En el bloque subcuenca_daily (celda 4, lineas 129-137), cambiar la linea del F.sum:
F.sum(F.when(F.col('caudal_confiable'), F.col('caudal_m3s'))).alias('caudal_agregado_m3s'),
# (F.when sin otherwise -> NULL en filas no confiables; F.sum ignora NULL, exclusion limpia)
```

Pero como muestra §2.4, cambia el valor de la columna en una fracción sustancial de **todo** el
histórico (no sólo los 218 días contaminados), porque `caudal_confiable=false` aparece de forma
dispersa y frecuente en estaciones que hoy contribuyen normalmente a la suma (con valores no
extremos). Aplicar esto de entrada tendría un radio de impacto mucho mayor sobre baselines ya
registrados en MLflow (BiLSTM v9-12, campeón provisorio pendiente de revisión, Decisión 046) que
el `clip` propuesto arriba. Se dejar documentado para que el usuario, si lo decide, lo evalúe como
una Decisión separada — idealmente re-corriendo el baseline BiLSTM sobre el dataset regenerado
para cuantificar el impacto en las métricas antes de reemplazar al campeón provisorio.

## 5. Pasos para que el usuario aplique la promoción (§3.1) cuando decida

1. Revisar y confirmar (o ajustar) el techo `MAX_CAUDAL_AGREGADO_ALTA_FRONTERA_M3S = 50000` de
   arriba contra este documento.
2. Editar `notebooks/05_Gold/ETL_Gold_Training_Dataset_v0.ipynb` (celda de código índice 3, después
   del loop de `subcuenca_wide`, antes de `base = (`) agregando el `.withColumn` de §3.1.
3. Registrar la Decisión correspondiente en `docs/decisions.md` (puede reusar el número reservado
   por la Decisión 051 de este documento, o abrir una nueva si el usuario ajusta el techo).
4. Correr el notebook en Databricks con `load_mode=full` (no `incremental`) para regenerar todo el
   histórico de `weather.gold.training_dataset_v0`.
5. Correr `06_Quality`/`gold_quality_report.md` (si aplica en este repo) para confirmar que el
   nuevo máximo de la columna es `<= 50000` y que el resto del reporte no cambia de forma
   inesperada.
6. En Rio_Search: `rio-search datasets refresh --force` para bajar el nuevo snapshot (nueva
   `delta_version`), y **quitar** el transform experimental `clip` de
   `configs/experiments/bilstm_baseline_v1.yaml`/`ridge_baseline_v1.yaml` (ya no hace falta: la
   columna nativa de Gold viene acotada) — crear `_v2` de esos YAML en vez de editar los ya
   corridos (convención del repo, §7 del plan).
7. Re-correr el baseline BiLSTM (y Ridge) sobre el dataset regenerado y comparar métricas contra
   las versiones registradas (v9-12) antes de decidir si cambia el campeón provisorio (Decisión
   046) — este paso es responsabilidad del usuario, no de esta fase.
