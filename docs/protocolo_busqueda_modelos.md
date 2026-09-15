# Protocolo de búsqueda de modelos — Rio_Search

Fecha: **2026-09-05**
Estado: **aceptado** — registrado en `decisions.md` como **Decisión 045** (2026-09-05).
Ejecutor previsto: **un agente Claude**, corriendo sin supervisión continua.
Catálogo de combinaciones: **`rio_search/experiments/matrix.yaml`**.
Código que ejecuta: `rio_search/` (ver su `README.md`); el corredor es `rio_search/runner.py`.

Este documento es **normativo**: define qué se corre, en qué orden, cómo se lee cada
resultado, cuándo se sigue, cuándo se para y cuándo hay que detenerse a preguntar. El
catálogo dice *qué* combinaciones existen; este protocolo dice *cómo* se recorren.

Está escrito para que un agente lo pueda ejecutar leyendo sólo esto y el catálogo, sin
reconstruir el contexto del proyecto. Todo lo que necesita decidir está acá como regla,
no como criterio.

---

## 0. Lectura mínima antes de ejecutar

En este orden, y nada más que esto:

1. Este documento, completo.
2. `rio_search/experiments/matrix.yaml` — las celdas y su estado.
3. La salida de `python -m rio_search.runner --estado` — dónde quedó la búsqueda.
4. `rio_search/README.md` — qué hace cada módulo y cuáles son sus invariantes.

El **corredor** (`rio_search/runner.py`) ejecuta este protocolo sobre el catálogo: corre las
celdas en orden, calcula el veredicto contra el ancla y escribe el ledger. Lo normal es
usarlo (§12) y leer el ledger a través de él; correr celdas a mano es para depurar.

`docs/funcion_ganancia_regimen.html` (definición de G-RAL y del modulador) y
`docs/decisions.md` se consultan **sólo** cuando una regla de este protocolo lo pide
explícitamente. No hace falta leerlos para ejecutar.

---

## 1. Qué se busca

Predecir el **caudal del Río Uruguay en `ana_74100000`** a 8 horizontes
(t+1…t+7, t+14), a partir de `weather.gold.training_dataset_v0`.

La búsqueda no busca "el mejor modelo" en abstracto: busca **la metodología** —
combinación de features, target, pérdida, arquitectura, estrategia de horizonte, ventana
de entrenamiento y validación — que mejor pronostica bajo la función de ganancia por
régimen del proyecto, y **deja escrito por qué**. Un número sin la comparación que lo
sostiene no es un resultado.

### Métrica objetivo y guardas

| Rol | Métrica | Regla |
| --- | --- | --- |
| **Objetivo** | `val/gral` (media sobre los 8 horizontes) | Es lo que se minimiza y lo que ordena el leaderboard. |
| Guarda de admisión | *skill* de RMSE contra persistencia | Si no le gana a persistencia, la celda **no entra** al leaderboard, gane lo que gane en G-RAL. |
| Guarda de régimen | `v_plus`, `v_minus`, `fa_wet` | Se reportan siempre. Un G-RAL que mejora empeorando V⁺ y V⁻ a la vez es un artefacto: hay que decirlo. |
| Desempate | `kge`, después `rmse` | Sólo cuando el objetivo empata (§5). |

`gral` con τ = 0,5 y sin log **es exactamente** el RMSE — hay un test que lo verifica. No
son métricas de familias distintas; G-RAL es RMSE con dos ingredientes agregados.

---

## 2. Reglas invariantes

Diez reglas. No se negocian, no se saltean y no dependen del bloque que se esté corriendo.

**R1 — Nada corre sobre un snapshot no verificado.** Antes de la primera celda de cada
sesión se ejecuta F1 (§4). Si el snapshot no pasa sus dos guardas, la sesión termina ahí.

**R2 — Guardas verdes antes de entrenar.** Tests y auditoría de fuga en verde antes de la
primera celda. Una guarda en rojo es **alto total**, no una advertencia: el modo de fallar
de una fuga es que los números *mejoren*.

**R3 — TEST se mira una sola vez, en B11.** Para las celdas de entrenamiento la regla es
**estructural**: el corredor les agrega `--no-test` fuera de B11 y el bloque directamente no
se calcula ni se escribe en el JSON. Para `search` y `walkforward`, que no tienen ese flag,
la regla sigue siendo de lectura: el corredor no mira TEST y el ledger guarda
`"test": "no_leido"`. Mirar TEST en cada celda convierte la búsqueda entera en un ajuste
sobre el conjunto de prueba.

**R4 — Una celda cambia una cosa.** Toda comparación es contra la **configuración ancla**
(§3.2) con todo lo demás idéntico: mismo snapshot, mismos splits, mismas semillas, mismo
preprocesamiento. Si una celda cambia dos ejes a la vez, no se puede atribuir el efecto y
no sirve.

**R5 — Una diferencia menor al ruido no es un resultado.** Se compara con el criterio de
§5.1. Por debajo de ese umbral el veredicto es `empata`, nunca `gana`.

**R6 — Persistencia es el piso.** Todo bloque reporta los baselines sobre sus mismos
splits. Un modelo que no le gana a persistencia en RMSE se registra con
`veredicto: "descartado"` y no compite.

**R7 — Ninguna celda `estado: falta` se implementa sin autorización.** El agente
**reporta** qué haría falta y **espera**. Implementar una celda por iniciativa propia
—aunque sea "una línea"— viola el alcance: el usuario decide qué se implementa.

**R8 — Toda corrida deja fila en el ledger.** Una corrida sin fila no existe: no se puede
repetir, no se puede fechar contra la versión del dato y no cuenta para el criterio de
finalización.

**R9 — τ_max no se ajusta a los datos.** Codifica un costo operativo declarado
(τ_max = 0,85 ⇒ subestimar en crecida cuesta 5,7 veces sobrestimar). Se explora su
**sensibilidad** en B8; no se elige por métrica. Lo mismo vale para los umbrales de régimen
(`WET_THRESHOLD`, `DRY_THRESHOLD`).

**R10 — Los bloques van en orden.** Cada bloque cierra fijando el ancla del siguiente
(§3.2). Saltear un bloque deja el ancla sin definir y hace incomparables todas las celdas
posteriores.

---

## 3. Estado de la búsqueda

### 3.1. Identidad del dato

Todo resultado se fecha contra el snapshot que lo produjo:

```
DATASET_ID = d<delta_version>-<primeros 8 del sha256 del parquet>
```

Al 2026-09-05 el snapshot vigente es `d278-76b949a2` (delta 278, exportado el 2026-08-30,
9.734 filas, 66 columnas). Los dos valores salen de
`notebooks_local/gold_export/cache/manifest.json`.

**Árbol de resultados:**

```
rio_search/results/
  ledger.jsonl                      # una fila por celda ejecutada (append-only)
  d278-76b949a2/                    # un directorio por DATASET_ID
    B0.06__ancla.json
    B1.03__mse_log.json
    ...
  <archivos sueltos anteriores>     # corridas previas al protocolo; se conservan
```

Los JSON que ya están sueltos en `results/` (`compare_gold278.json`,
`search_gral_tpe_60.json`, `walkforward_gral.json`, …) son de antes de este protocolo. No
se mueven, no se borran y **no cuentan** como celdas: si una celda los reproduce, se corre
igual y se guarda en su lugar nuevo.

### 3.2. La configuración ancla

El ancla es la fila de referencia contra la que se mide cada celda. Arranca en la
configuración que hoy está mejor documentada y **se actualiza al cerrar cada bloque**: si
un bloque produjo una celda con veredicto `gana`, esa celda pasa a ser el ancla del bloque
siguiente. La versión vigente vive en `matrix.yaml → ancla`, y cada actualización deja
constancia en el ledger con `celda: "ANCLA"`.

Ancla inicial (`d278-76b949a2`):

| Eje | Valor | De dónde sale |
| --- | --- | --- |
| modelo | `mlp`, 1 capa oculta | lo único entrenable hoy además de `linear` |
| pérdida | `gral` (expectil + log) | la propuesta de la tesis |
| features | `caudal_estado, caudal_agregado_alta_frontera, lluvia_ratio, estacionalidad` (19) | `DEFAULT_GROUPS` |
| horizontes | `multi_output`, 8 salidas | lo único implementado |
| split | `rolling_365`, embargo 14 d | `make_splits` |
| modulador | `oracle`, `tau_max=0.85` | modo del análisis retrospectivo |
| lluvia del modulador | `lluvia_media_est_mm` | ver abajo — **no** es la fuente preferible |
| hiperparámetros | `hidden=38, lr=0.0492, l2=2.17e-4, epochs=378` | mejor trial de `search_gral_tpe_60.json` |
| semillas | 5 | mínimo para tener desvío |

**Medido el 2026-09-05 sobre `d278-76b949a2`** (9.617 días; TRAIN 8.939 / VAL 365 / TEST 285):

```
ancla         val/gral = 0.4969 ± 0.0096   RMSE 1030   NSE 0.18   KGE 0.49   V+ 0.365   V− 0.747
persistencia  val/gral = 0.5145            RMSE 1083          → skill_rmse del ancla = 0.049
umbral de ruido = 0.0121
```

Dos cosas que ese número obliga a decir en cualquier informe:

* **La fuente de lluvia del ancla no es la preferible.** La grilla MERGE lo es (media areal
  real, cobertura completa, estacionaria), mientras que la media por estación sigue
  dependiendo de qué pluviómetros reportaron ese día. El ancla usa estaciones porque es la
  fuente bajo la que se buscaron sus hiperparámetros y bajo la que corrieron todos los
  resultados previos de `results/`. Con HP idénticos, pasar a MERGE mueve `val/gral` de
  0,4969 a 0,5488 — **cuatro veces el umbral de ruido** — y da vuelta el perfil de régimen
  (V⁺ 0,365 → 0,530; V⁻ 0,747 → 0,657). Ponerla en el ancla mezclaría dos cambios (R4), así
  que MERGE se prueba como celda de un solo cambio en **B8.03**. Si gana, se vuelve el ancla
  y hay que re-correr B9.01 bajo esa fuente antes de seguir.
* **El ancla apenas le gana al piso.** 4,9 % de *skill* de RMSE, y en G-RAL su ventaja sobre
  el mejor baseline (persistencia ×1,10, 0,5044) es 0,0075 — por debajo del umbral, o sea
  **un empate**. El año de VAL es bastante más duro que el de TEST, donde el *skill* era
  ~22 %. R6 es una restricción viva acá, no una formalidad.

El mejor trial usaba además `patience=81` y el CLI de `train.py` **no expone `--patience`**
(brecha `G-01`), así que el ancla corre con el default 60. Medido: da exactamente el mismo
`val/gral` que el `final_multisemilla` de aquella búsqueda — en esta configuración corta el
early stopping antes, así que la brecha existe pero no afecta al ancla.

**El ancla declara su fuente de lluvia siempre.** Las dos series correlacionan 0,90 pero
V⁺ se mueve 0,10–0,15 según cuál se use: un V⁺ sin la fuente al lado no se puede comparar
con nada.

### 3.3. El ledger

`rio_search/results/ledger.jsonl`, una línea JSON por corrida, **append-only**. Nunca se
edita una fila: un resultado que se re-corre agrega una fila nueva.

```json
{"celda":"B1.03","nombre":"mse_log","bloque":"B1","dataset":"d278-76b949a2",
 "corrida_at":"2026-09-05T14:22:11-03:00","estado":"ok","seeds":5,
 "cmd":".venv/Scripts/python.exe -m rio_search.train --loss mse_log --seeds 5 ...",
 "salida":"rio_search/results/d278-76b949a2/B1.03__mse_log.json",
 "val":{"gral":0.4902,"gral_sd":0.0088,"rmse":1011.0,"kge":0.51,"v_plus":0.44,"v_minus":0.62},
 "test":"no_leido","skill_rmse_vs_persistencia":0.066,
 "delta_vs_ancla":{"gral":-0.0067,"ee_combinado":0.0058},
 "veredicto":"empata","tiempo_s":48.2,
 "nota":"la transformación log sola explica casi toda la ganancia de gral"}
```

| Campo | Valores |
| --- | --- |
| `estado` | `ok` · `error` · `bloqueado` (celda `falta` o dato ausente) · `historico` (dataset viejo) |
| `veredicto` | `gana` · `empata` · `pierde` · `descartado` (no supera persistencia) · `—` (celdas de guarda) |
| `test` | `"no_leido"` fuera de B11; el objeto de métricas dentro de B11 |

---

## 4. El ciclo

Siete fases. F0–F3 corren **una vez por sesión**; F4–F6 se repiten por bloque; F7 cierra.

### F0 — Orientación (sin correr nada)

```bash
.venv/Scripts/python.exe -m rio_search.runner --estado
```

Imprime el DATASET_ID vigente, cuántas celdas están ok / bloqueadas / con error / sin
correr, el ancla con su desvío y el umbral de ruido que se deriva de él, cuántas P1 faltan
y **cuál es la próxima celda**. Si el ledger no existe, la próxima celda es `B0.01`.

### F1 — Frescura y validez del dato (R1)

```bash
.venv/Scripts/python.exe notebooks_local/gold_export/export_gold_dataset.py --refresh
```

El script consulta la historia de la tabla Delta, regenera el snapshot del Volume si Gold
avanzó, baja el parquet y verifica su `sha256`. Después:

```bash
.venv/Scripts/python.exe -c "import json;m=json.load(open('notebooks_local/gold_export/cache/manifest.json',encoding='utf-8'));print('d%s-%s'%(m['delta_version'],m['file_sha256'][:8]),m['rows'],len(m['columns']))"
```

* **Si el DATASET_ID cambió** respecto del ledger → ir a §7 (protocolo de cambio de
  dataset) antes de seguir.
* **Si el script falla** por falta de credenciales de Databricks → no improvisar: reportar
  y ofrecer correr sobre el snapshot en cache tal como está, dejándolo escrito en el
  informe. Sólo con autorización.
* **Si `_assert_manifest_vigente` rechaza el parquet** → alto total (R1). El snapshot y su
  manifest describen datos distintos.

### F2 — Guardas (R2)

```bash
.venv/Scripts/python.exe -m pytest rio_search/tests -q
.venv/Scripts/python.exe -m rio_search.audit
```

45 tests + la auditoría de fuga. Cualquier rojo = alto total, con el output textual en el
informe. La auditoría cubre lo que una revisión de columnas de Gold no ve: las features
derivadas, el modulador y los splits.

Si aparece una feature legítima de pronóstico que dispara la guarda (Fase 4 del roadmap),
la salida correcta es **declararla en `audit.FUTURO_LEGITIMO`** con justificación —
**nunca** bajar el umbral. Y eso es una celda `falta`: se reporta y se espera (R7).

### F3 — Piso y ancla (R6)

Correr `B0.04` (baselines) y `B0.06` (ancla, 5 semillas). Sin estas dos filas en el ledger
no se puede leer ninguna celda posterior.

### F4 — Ejecutar el bloque

```bash
.venv/Scripts/python.exe -m rio_search.runner --bloque B1
```

El corredor hace, para cada celda del bloque y en orden de `id`:

1. Si `estado` no es `implementado` → fila de ledger con `estado: bloqueado` y el motivo;
   sigue con la siguiente. **No implementa nada** (R7).
2. Corre el `cmd` del catálogo agregando `--out rio_search/results/<DATASET_ID>/<id>__<slug>.json`
   y, si es una celda de entrenamiento fuera de B11, `--no-test`.
3. Lee del JSON el bloque `val`, calcula el veredicto (§5) contra el ancla vigente y hace
   append al ledger.
4. Si la corrida falla, deja `estado: error` con la cola del traceback y sigue — salvo que
   sea una guarda de B0, donde **corta** (R1/R2).
5. Salta las celdas de más de 600 s estimados salvo `--incluir-largas`, y las que ya tienen
   fila `ok` para este DATASET_ID salvo `--rehacer`.

Lo que el corredor **no** hace y sigue siendo del agente: decidir si un resultado contradice
una Decisión vigente, redactar el informe y pedir autorización para lo que falta.

### F5 — Leer el bloque

Tabla comparativa de todas las celdas del bloque contra el ancla, con Δ y error estándar
combinado. Identificar la celda ganadora si existe.

### F6 — Cerrar el bloque

* Si hay exactamente una celda `gana` → **pasa a ser el ancla** del bloque siguiente; fila
  de ledger con `celda: "ANCLA"` y `matrix.yaml → ancla` actualizado.
* Si hay varias `gana` en el mismo eje → gana la de mejor objetivo; las otras quedan
  anotadas como candidatas para B10 (ensembles).
* Si no hay ninguna `gana` → el ancla no se mueve y el eje queda marcado
  `saturado: true` en el catálogo.

Emitir el **informe de bloque** (§6) y seguir con el bloque siguiente.

### F7 — Confirmación y cierre

Es el bloque B11 y **es el único lugar donde se mira TEST**. Ver §8.

---

## 5. Cómo se lee un resultado

### 5.1. El umbral de ruido (R5)

Con `n` semillas, el error estándar de la media entre semillas es `ee = sd / √n`. Dos
configuraciones se comparan así:

```
Δ            = objetivo(celda) − objetivo(ancla)          (negativo = la celda mejora)
ee_combinado = √( ee_celda² + ee_ancla² )
gana   si   Δ < −2 · ee_combinado
pierde si   Δ > +2 · ee_combinado
empata en el resto
```

Con el ancla medido (`val/gral` = 0,4969, sd entre semillas = 0,0096, n = 5) el umbral
queda en **0,0121 de G-RAL**. Una celda que mejora 0,005 **empata**, por más que la tabla
la muestre primera. El umbral se recalcula con el sd real que devuelva B0.06 en cada
DATASET_ID: no es una constante del protocolo.

**Este umbral cubre el ruido de inicialización, no el del año.** VAL son 365 días de un
solo año hidrológico: dos configuraciones pueden separarse limpiamente entre semillas y dar
vuelta el orden en otro año. Por eso ninguna conclusión se cierra sin B11 (walk-forward),
y por eso el criterio de finalización (§8) exige tasa de victorias entre folds, no un
único número.

### 5.2. Guarda de admisión (R6)

```
skill_rmse = 1 − RMSE(celda) / RMSE(persistencia)      sobre el mismo split
```

`skill_rmse ≤ 0` ⇒ `veredicto: "descartado"`, sin importar el objetivo.

Referencia medida sobre `d278-76b949a2`, **en VAL**, que es el split que decide:

| | G-RAL | RMSE m³/s | KGE |
| --- | ---: | ---: | ---: |
| persistencia | 0,5145 | 1.083 | 0,53 |
| persistencia × 0,90 | 0,5468 | 1.044 | 0,51 |
| persistencia × 1,10 | 0,5044 | 1.151 | 0,51 |
| climatología 30 d | 0,6056 | 1.197 | 0,24 |
| **ancla** (mlp · gral) | **0,4969** | **1.030** | 0,49 |

En TEST el mismo tipo de modelo llega a *skill* ≈ 0,18–0,22 contra una persistencia de
RMSE ≈ 1.648. **Los dos conjuntos de números no son intercambiables**: citar los de TEST
al leer una celda de VAL es el error más fácil de cometer con este arnés, porque el JSON
trae los dos bloques uno al lado del otro.

### 5.3. Lectura de régimen

Además del escalar, toda celda reporta `v_plus` (subestimar en régimen húmedo),
`v_minus` (sobrestimar en régimen seco) y `fa_wet` (falsa alarma). Reglas de lectura:

* Una mejora de `v_plus` pagada con `fa_wet` **no es una mejora**: es correr el sesgo. Se
  reportan juntas siempre.
* Una celda que mejora el escalar y empeora `v_plus` **y** `v_minus` a la vez se marca
  `nota: "sospechosa"` — el agregado está escondiendo el comportamiento.
* La evidencia acumulada del proyecto dice que `mse_log` gana RMSE de forma robusta, que
  `gral` gana V⁻ y KGE, y que `gral` **no** gana el escalar G-RAL de forma robusta. Un
  resultado que contradiga esto es interesante, no es un error — pero dispara §9.

### 5.4. Cuándo el ancla no es una comparación justa

R4 pide que una celda cambie una cosa, y en la mayoría de los ejes eso se cumple solo. Hay
dos donde **no**, y hay que declararlo en el informe en vez de leer el veredicto como si
nada:

* **Celdas que cambian la cantidad de features** (todo B2). Los hiperparámetros del ancla se
  buscaron con 19 features; correrlos con 26 o con 7 no los deja neutrales, porque la
  capacidad que le sobra o le falta al modelo se mezcla con el efecto de las features. El
  veredicto sigue siendo informativo —dice qué pasa *a igual capacidad*— pero no separa
  "estas features aportan" de "este modelo tiene el tamaño equivocado para estas features".
* **Celdas que cambian la familia de modelo** (todo B4). Un LightGBM con los
  hiperparámetros de un MLP no significa nada; cada familia trae su propio espacio.

En los dos casos la lectura correcta es: el bloque **ordena candidatos**, y el ganador entra
a **B9 con su propia búsqueda de hiperparámetros** antes de que su ventaja se considere
real. Un `gana` de B2 o B4 es una nominación, no una conclusión. Al cerrar esos bloques, el
ancla se mueve dejando anotado que sus hiperparámetros están heredados, y B9.07 es el que
resuelve la confusión.

---

## 6. Informe de bloque

Al cerrar cada bloque, en el chat (no como archivo), en este formato y sin adornos:

```
BLOQUE B1 — Pérdida · dataset d278-76b949a2 · 5 semillas · split VAL
ancla (B0.06): mlp · gral · 19 feats · lluvia_media_est_mm · val/gral = 0.4969 ± 0.0096
piso: persistencia val/gral = 0.5145 · RMSE 1083

celda    configuración   val/gral         Δ vs ancla   RMSE   KGE    V+     V−     skill  veredicto
B1.01    mse             0.5410 ± 0.0104  +0.044 ✗     1044   0.52   0.41   0.55   0.036  pierde
B1.03    mse_log         0.4902 ± 0.0088  −0.007       1011   0.51   0.44   0.62   0.066  empata
B1.06    expectil τ fijo —                —             —      —      —      —      —     bloqueado
...

umbral de ruido: ±0.0121 (2 · ee combinado, n = 5)
ganador: ninguno — el ancla no se mueve, eje `pérdida` marcado saturado
bloqueadas: B1.06, B1.07, B1.10 (τ constante, huber, NSE-loss) — las tres son P1, ver §9
próxima celda: B2.02
```

Los valores de arriba son un ejemplo de formato, no resultados: sólo la fila del ancla y
la de persistencia están medidas.

Reportar el número **y** su desvío. Un resultado sin desvío no se puede leer.

---

## 7. Cuando cambia el dataset

Es el caso central: el pipeline sigue corrigiendo Gold, y una corrección del target
invalida todas las conclusiones anteriores en silencio — el parquet carga, el
entrenamiento corre y los números salen, calculados contra un target que ya cambió.

Cuando F1 detecta un DATASET_ID nuevo:

1. **Marcar como histórico.** Todas las filas del ledger con el DATASET_ID anterior pasan
   a `estado: "historico"` agregando una fila de cierre (no se editan las viejas, R8).
2. **Elegir el modo de replay:**

El corredor clasifica el cambio solo, comparando el snapshot contra la **apertura de la
campaña vigente**. Lo que decide **no** es que haya subido la versión Delta —sube todos los
días, porque la cadena diaria agrega un día de datos— sino qué cambió de verdad:

| Qué cambió | Modo | Qué pasa |
| --- | --- | --- |
| Sólo se agregaron filas al final, con el pasado intacto | `filas_nuevas` | **La campaña sigue.** Lo ya corrido vale y se continúa donde quedó. |
| Aparecieron o desaparecieron columnas | `esquema` | Campaña nueva: hay atributos que el catálogo puede querer usar. |
| **Cambiaron los valores históricos del target** | `valores` | Campaña nueva. Es el caso de la Decisión 039 y **el más peligroso: llega sin cambiar ni el esquema ni el número de filas.** |
| Hay menos filas que antes | `filas_perdidas` | Campaña nueva: se rehízo historia y no se sabe qué se movió. |
| No se pudo calcular la huella de valores | `indeterminado` | Campaña nueva, por precaución. |

La detección de `valores` usa una **huella de los caudales históricos** —el target y el caudal
actual, excluyendo los últimos 45 días, que se reescriben solos por telemetría tardía y por la
regeneración mensual de MERGE. Sin esa huella una corrección del pasado se vería idéntica a
«no pasó nada», y todas las conclusiones quedarían calculadas contra un target que ya cambió.

Una **campaña** agrupa los snapshots equivalentes para las conclusiones. Cada fila del ledger
guarda las dos cosas: `dataset`, el snapshot exacto que la produjo, para procedencia; y
`campana`, el grupo bajo el que se la busca. Ante la duda, campaña nueva: es caro en reloj, no
en riesgo.

3. **Re-correr en orden**, con el mismo `id` de celda y el DATASET_ID nuevo en la ruta de
   salida. Los `id` son estables justamente para esto: la misma celda es comparable a
   través de versiones del dato. Los pasos 1 a 3 son un comando:

   ```bash
   .venv/Scripts/python.exe -m rio_search.runner --todo --incluir-largas
   ```

   El corredor detecta el DATASET_ID nuevo, cierra las filas viejas como históricas antes de
   correr nada y recorre el catálogo entero. Sin las tres celdas de walk-forward son ~33
   minutos; con ellas, ~90.

4. **Emitir el informe de deriva** — la única salida que importa de un replay:

   ```bash
   .venv/Scripts/python.exe -m rio_search.runner --deriva
   ```

```
DERIVA d278-76b949a2 → d291-a13f0c22
celda    objetivo antes   objetivo ahora   veredicto antes → ahora
B1.03    0.4351           0.4102           empata → gana        ⚠ cambió
B2.02    0.4290           0.4285           gana   → gana
...
conclusiones que se dieron vuelta: 1 de 24
```

Una conclusión que se da vuelta con el dato nuevo **no se resuelve en el informe**: se
reporta y se espera (§9).

---

## 8. Cuándo se termina

### 8.1. Criterio de finalización

La búsqueda se declara **cerrada** cuando se cumplen las cuatro:

1. **Cobertura** — todas las celdas de prioridad `P1` del catálogo tienen fila en el
   ledger con `estado: ok` o `bloqueado` para el DATASET_ID vigente.
2. **Saturación** — dos bloques consecutivos cerraron sin ninguna celda `gana`.
3. **Confirmación** — el campeón de VAL corrió walk-forward anidado (B11.01) y **gana al
   ancla en ≥ 3 de los 4 folds completos**. La media entre folds sola no alcanza: un año
   raro la mueve entera.
4. **TEST único** — se evaluó TEST **una vez** sobre el campeón confirmado (B11.02), se
   reportó con su desvío entre semillas y quedó en el ledger. No se vuelve a tocar.

Con las cuatro cumplidas: informe final + propuesta de entrada en `decisions.md`. La
entrada la **propone** el agente y la **aprueba** el usuario.

### 8.2. Criterio de continuación

Si falta alguna, la búsqueda **sigue** y el ledger dice exactamente dónde: la próxima celda
es la primera del catálogo, en orden de bloque, sin fila `ok` para el DATASET_ID vigente.
No hay estado en ningún otro lado — el ledger es la única fuente.

### 8.3. Lo que *no* es criterio de cierre

* Un objetivo "suficientemente bueno". No hay umbral absoluto: el piso es persistencia y
  el techo lo pone la comparación.
* El presupuesto de reloj. Sin límite de tiempo por decisión del plan (`rio_search_plan.md`
  §0, Decisión #13): el entrenamiento dura lo que dure, corta el early stopping.
* Que TEST dé bien. TEST no selecciona nada (R3).

---

## 9. Cuándo detenerse y preguntar

El agente **para, reporta y espera** —sin implementar, sin improvisar y sin seguir con el
bloque siguiente— cuando pasa cualquiera de estas:

| Disparador | Por qué se para |
| --- | --- |
| La próxima celda del camino está `estado: falta` | El usuario decide qué se implementa (R7). Reportar qué haría falta, en cuánto se estima y qué desbloquea. |
| Una guarda de F2 falla | Un rojo en fuga o en los tests invalida todo lo posterior. |
| `_assert_schema_vigente` o `_assert_manifest_vigente` rechazan el snapshot | El dato no es el que dice ser. |
| Una celda pide un dato que no existe (grupo `forecast`, modo `forecast` del modulador) | Depende de la Fase 4 del roadmap del dataset, no de esta búsqueda. |
| Un resultado contradice una Decisión vigente | Ej.: que las sub-cuencas de aguas abajo aporten contradice la Decisión 018; que el nivel aporte contradice la 040. Es un hallazgo, no un permiso para revertirla. |
| Una celda necesita una dependencia nueva en el entorno | `torch`, `scikit-learn`, `lightgbm`, `statsmodels` no están instalados. Instalar es una decisión del usuario. |
| El informe de deriva (§7) da vuelta una conclusión | Cambia lo que la tesis va a defender. |
| Una celda estima más de 2 h de reloj | Confirmar antes de arrancarla, no después. |

En todos los casos: **qué se intentó, qué pasó, qué hace falta, y cuál es la celda
siguiente si se autoriza**. Nada más.

---

## 10. Por qué barrido coordinado y no producto cartesiano

El catálogo tiene 11 ejes. El producto cartesiano de sus valores razonables está en el
orden de 10⁸ combinaciones; a ~10 s por corrida de 5 semillas son decenas de miles de años
de reloj. No es una restricción de presupuesto: es que la pregunta que el producto
cartesiano responde —cuál es el óptimo global— no es la que la tesis necesita responder.

El diseño es **descenso coordinado sobre los ejes**, con un ancla explícita: un eje por
bloque, todo lo demás fijo, y el ganador de cada bloque pasa a ser el ancla del siguiente.
Eso da ~120 celdas, cada una atribuible a un cambio, que es exactamente lo que se puede
defender en un capítulo.

Lo que el método **no** ve, y hay que decirlo en la tesis: las **interacciones**. Un modelo
secuencial puede pedir un lookback largo que al MLP no le sirve, y el barrido coordinado
—que fijó la representación de la entrada antes de llegar al modelo— nunca lo prueba. Dos
mitigaciones, ambas en el catálogo:

* **B9 (búsqueda bayesiana conjunta)** sobre los 2–3 finalistas, con los ejes que
  interactúan liberados a la vez. Es donde se recuperan las interacciones que el descenso
  coordinado se perdió.
* **El orden de los bloques no es arbitrario.** Va de lo que menos interactúa a lo que más:
  pérdida y features primero (efectos mayormente aditivos), arquitectura y estrategia de
  horizonte después (donde el acoplamiento con la representación de la entrada es fuerte).

Un eje marcado `saturado` en el catálogo **no se re-explora** en bloques posteriores salvo
que B9 lo reabra explícitamente.

---

## 11. Mapa del catálogo

111 celdas en 12 bloques. **37 corren hoy** (26 con comando propio, 11 que reusan la
corrida de otra celda); 71 necesitan código; 2 dependen de un dato que Gold todavía no
tiene; 1 contradice una Decisión vigente.

| Bloque | Eje | Celdas | Corren hoy | Reloj estimado |
| --- | --- | ---: | ---: | --- |
| B0 | piso y guardas | 6 | 5 | ~3 min |
| B1 | pérdida | 14 | 5 | ~1 min |
| B2 | features y representación | 19 | 7 | ~2 min |
| B3 | parametrización del target | 6 | 2 (alias) | — |
| B4 | familia de modelo | 28 | 2 | ~1 min |
| B5 | estrategia de horizonte | 5 | 1 (alias) | — |
| B6 | ventana de entrenamiento | 6 | 4 | ~43 min |
| B7 | preprocesamiento | 5 | 1 (alias) | — |
| B8 | modulador τ (sensibilidad) | 5 | 3 | ~9 min |
| B9 | búsqueda de hiperparámetros | 7 | 3 | ~20 min |
| B10 | ensembles | 5 | 0 | — |
| B11 | confirmación y cierre | 5 | 4 | ~14 min |

Todo lo implementado son ~90 minutos de reloj, de los cuales **~57 se los llevan las tres
celdas de walk-forward** (B6.02, B6.04, B11.01). Sin ellas, el catálogo entero corre en
**~33 minutos**. Los tiempos de las celdas de entrenamiento están recalibrados contra lo
medido: una corrida de 5 semillas con `--no-test` tarda 3–7 s, no el minuto que se había
estimado.

**Con lo que corre hoy la búsqueda no puede cerrar.** Alcanza para saturar el eje
`pérdida`, hacer la ablación de features y medir la sensibilidad del modulador; no alcanza
para la cobertura de P1. Las ocho celdas que faltan en el camino crítico, en orden de
impacto:

| Celda | Qué desbloquea |
| --- | --- |
| `B2.17` ventana / lookback | 13 celdas de B4 (todos los secuenciales) |
| `G-05` guardar predicciones | todo B10 (ensembles) y B11.03 (Diebold-Mariano) |
| `B4.09` LightGBM (o `B4.08` XGBoost) | la comparación tabular fuerte, que hoy no existe |
| `B4.13` DLinear | el control obligatorio antes de cualquier transformer |
| `B4.14` LSTM | la referencia de la literatura de rainfall-runoff |
| `B5.02` per_horizon | la comparación que la Decisión #2 del plan promete |
| `B3.04` target diferencial | la parametrización que más suele mover la aguja |
| `B1.06` expectil con τ constante | el control que separa "la asimetría ayuda" de "el modulador ayuda" |

Ninguna de las ocho se implementa sin autorización (R7). El catálogo lleva, para cada una,
dónde tocaría, qué habría que escribir, de qué depende y el esfuerzo estimado.

---

## 12. El corredor

`rio_search/runner.py` ejecuta este protocolo. Lo que antes era una instrucción a seguir a
mano pasa a ser un comando, y las reglas que dependían de la disciplina de quien ejecutaba
pasan a estar en el código.

| Comando | Qué hace |
| --- | --- |
| `--estado` | La fase F0: DATASET_ID, celdas ok/bloqueadas/con error/sin correr, ancla con su desvío, umbral de ruido, P1 sin cubrir y próxima celda. |
| `--bloque B1` | Corre un bloque completo y emite su informe. |
| `--celda B1.03` | Corre una celda. |
| `--todo` | Recorre el catálogo entero en orden de bloque. **Es el replay de §7.** |
| `--deriva` | Compara contra el DATASET_ID anterior y lista las conclusiones que se dieron vuelta. |

Modificadores: `--dry-run` (mostrar sin correr), `--rehacer` (re-correr celdas ya `ok`),
`--incluir-largas` (las de más de 600 s, que si no se saltean), `--timeout` por celda.

Lo que el corredor sostiene por código y ya no por disciplina:

* **R3** — agrega `--no-test` a toda celda de entrenamiento fuera de B11, así que el bloque
  TEST no existe en el JSON. En `search` y `walkforward`, que no tienen el flag, no lo lee.
* **R5** — el veredicto sale del umbral de ruido, no de comparar dos números.
* **R6** — `skill_rmse ≤ 0` da `descartado` antes de mirar el objetivo.
* **R7** — una celda que no está implementada deja fila `bloqueado` con su motivo y sigue.
  El corredor **no escribe código**.
* **R8** — el ledger es append-only; una re-corrida agrega fila, no edita.
* **R1/R2** — si falla una guarda de B0, corta con código de salida 2.

Lo que **no** hace y sigue siendo del agente: decidir si un resultado contradice una
Decisión vigente, redactar el informe de bloque en prosa y pedir la autorización de §9.
