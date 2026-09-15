# `rio_search` — núcleo de métricas y arnés de entrenamiento

Implementa la métrica asimétrica por régimen **G-RAL** de
`docs/funcion_ganancia_regimen.html` y un arnés que permite **entrenar con
cualquiera de las pérdidas** y comparar los resultados.

Esto **no** es todavía la aplicación completa de `docs/rio_search_plan.md`
(Onion + DDD, PyTorch, MLflow, UI React): eso arranca en la Fase 0 del plan.
Lo que hay acá es la pieza que el plan §3.7 pide como "funciones puras con
tests", más lo mínimo alrededor para poder correrla contra datos reales.

`metrics.py` y `gate.py` son NumPy puro, sin estado y sin dependencias del
arnés, así que la app los importa tal cual cuando exista.

## Requisitos

Sólo `numpy`, `pandas` y `pyarrow` — ya están en el `.venv` del repo. Sin torch,
sin sklearn, sin instalación adicional.

## Uso

```bash
# tests (71, no hace falta pytest)
.venv/Scripts/python.exe rio_search/tests/test_metrics.py
.venv/Scripts/python.exe rio_search/tests/test_gate.py
.venv/Scripts/python.exe rio_search/tests/test_data.py
.venv/Scripts/python.exe rio_search/tests/test_leakage.py
.venv/Scripts/python.exe rio_search/tests/test_runner.py

# la misma auditoría como reporte, fuera de los tests
python -m rio_search.audit
# o:  python -m pytest rio_search/tests -q

# entrenar una configuración
python -m rio_search.train --model mlp --loss gral

# la grilla completa de pérdidas, 5 semillas
python -m rio_search.train --compare --model mlp --seeds 5

# protocolo de sensibilidad de tau_max (§04 del informe)
python -m rio_search.sensitivity --seeds 3

# modulador oráculo vs modulador causal
python -m rio_search.sensitivity --tau-modes --seeds 3
```

### La búsqueda, por protocolo

Lo de arriba son los comandos sueltos. La búsqueda completa se recorre con el corredor, que
ejecuta `docs/protocolo_busqueda_modelos.md` sobre el catálogo
`rio_search/experiments/matrix.yaml` y lleva el ledger:

```bash
python -m rio_search.runner --estado        # dónde quedó la búsqueda
python -m rio_search.runner --bloque B1     # correr un bloque
python -m rio_search.runner --todo          # correr el catálogo entero (~33 min)
python -m rio_search.runner --deriva        # qué cambió al cambiar el dataset
```

**Cuando cambia el dataset, `--todo` es todo lo que hay que hacer.** El corredor compara el
snapshot contra la apertura de la campaña vigente y decide solo: si sólo se agregaron días al
final con el pasado intacto, **la campaña sigue** y no se pierde nada; si cambió el esquema o
**cambiaron los valores históricos del target**, abre campaña nueva y lo anterior queda para
`--deriva`. Esa segunda detección usa una huella de los caudales históricos, porque una
corrección del pasado puede llegar sin cambiar ni una columna ni una fila — que es exactamente
lo que hizo la Decisión 039.

Los resultados quedan en `rio_search/results/<DATASET_ID>/<celda>__<slug>.json` con el
detalle por horizonte y por semilla, y una fila por corrida en `results/ledger.jsonl`. Los
JSON sueltos en la raíz de `results/` son de antes del protocolo: se conservan y no cuentan
como celdas.

## Módulos

| Archivo | Qué hace |
| --- | --- |
| `metrics.py` | RMSE, MAE, MAPE, NSE, KGE, PBIAS, R², **G-RAL**, tasas de violación, skill score. Funciones puras. |
| `gate.py` | El modulador: de la lluvia a τ. `GateParams`, `build_tau`, y `assert_causal`, que es el test del invariante. |
| `data.py` | Snapshot Gold → features, targets por horizonte, τ y splits `rolling_365` con embargo. |
| `models.py` | Pérdidas (la pérdida es un **parámetro**, no está cableada), MLP y lineal en NumPy con Adam, y los baselines. |
| `train.py` | Arnés: preprocesamiento ajustado sólo con TRAIN, entrenamiento multi-semilla, evaluación y tabla. |
| `sensitivity.py` | Barrido de τ_max y contraste de modos de modulador. |
| `audit.py` | Auditoría de fuga sobre features, modulador y splits. Corre como CLI y como test. |
| `runner.py` | Corredor del catálogo: corre las celdas en orden, calcula el veredicto contra el ancla con el umbral de ruido, y hace append al ledger. Sostiene por código las reglas que antes dependían de la disciplina de quien ejecutaba. |
| `experiments/matrix.yaml` | Catálogo de combinaciones: 111 celdas en 12 bloques sobre 11 ejes, con su comando o con qué habría que escribir para poder correrlas. |
| `tests/` | 71 tests: métricas contra valores conocidos, invariantes del modulador, guardas de esquema y frescura, la auditoría de fuga con sus pruebas negativas, y la coherencia del catálogo más las reglas del corredor. |

## La métrica en tres líneas

```
e   = Q_obs − Q_pred                       e > 0  ⇒  el modelo subestimó
ψ_τ = 2 · |τ − 1{e < 0}| · e²              τ > 0,5 castiga más subestimar
G-RAL = √( media( ψ_τ(ln Q_obs − ln Q_pred) ) )
```

`τ` sale del modulador, un valor por día. Con `τ = 0,5` y sin log,
`gral() == rmse()` **exactamente** — hay un test que lo verifica y es la
verificación de partida de la decisión.

## Dos invariantes que no se pueden romper

1. **El modulador sólo lee información disponible en t₀.** Nunca el caudal
   observado del día a predecir. Si lo leyera, el score se vuelve manipulable:
   un modelo sesgado a crecida quedaría bien evaluado justo en los días donde se
   lo mira. `gate.assert_causal()` lo verifica y `data.build_dataset()` lo llama.

2. **La lluvia del modulador tiene que ser estacionaria.** `lluvia_acumulada_mm` de
   Gold es una *suma* sobre 0–177 estaciones según la época. Sirven la media por
   estación (`_derive_rain`) o, mejor, la grilla MERGE de CPTEC, que ya está en
   Gold y es media areal real con cobertura completa.

## Auditoría de fuga

`audit.py` la deja como reporte ejecutable (`python -m rio_search.audit`) y
`test_leakage.py` la corre como test permanente. Cubre la capa que una auditoría
sobre las columnas de Gold no ve: las features **derivadas** que arma `data.py`,
el modulador y los splits.

| Test | Qué atrapa |
| --- | --- |
| Ninguna feature predice t+1 mejor que el caudal de hoy | Un **proxy** del futuro, que no es idéntico a ninguna columna y por eso pasa cualquier comparación de valores. |
| El modulador no entra como feature | τ puede mirar lluvia futura en modo `oracle` sin que sea fuga, siempre que llegue sólo a la pérdida. Medido: \|r\| máxima de 0,42 entre τ y cualquier feature. |
| Splits sin solape y con embargo | Que el hueco entre splits supere el horizonte máximo (hoy 15 d > 14 d). |
| El preprocesamiento sólo mira TRAIN | Se altera VAL/TEST y se verifica que las medianas y escalas no se muevan. |
| Los acumulados de lluvia miran hacia atrás | Una ventana centrada o adelantada se ve normal en el código y contiene lluvia que todavía no cayó. |

**Cada guarda va con su prueba negativa.** Una guarda que nunca se vio fallar no
es evidencia de nada. Se inyecta el target con ruido creciente y se verifica que
siga disparando, porque el caso que importa no es la fuga exacta sino el proxy
transformado — la fuga de la Decisión 040 era el nivel futuro, la misma señal
pasada por la curva de aforo, y una comparación de valores no la habría visto.

Alcance medido, contra una línea base de \|r\| = 0,856 y midiendo qué le hace cada
proxy inyectado al RMSE de un modelo legítimo (`caudal_actual + caudal_media_3d`,
RMSE 1001 m³/s):

| Ruido del proxy | \|r\| marginal | ¿Pasa la guarda? | RMSE | Mejora |
| --- | ---: | :---: | ---: | ---: |
| 25 % | 0,950 | no | 528 | +473 |
| 40 % | 0,876 | no | 748 | +253 |
| 50 % | 0,826 | **sí** | 820 | **+182** |
| 100 % | 0,572 | sí | 948 | +53 |

**Un proxy con 50 % de ruido pasa la guarda y baja el RMSE un 18 %.** No es
inofensivo. Una versión anterior de este README argumentaba que por debajo de la
línea base el proxy no podía aportar nada; eso confundía correlación **marginal**
con aporte **incremental**, y está mal. Dos features de 0,7 cada una, si son
independientes entre sí, superan juntas a una de 0,85.

La correlación **parcial** (controlando por `caudal_actual`) sería el diagnóstico
teóricamente correcto y tampoco alcanza como umbral: el máximo legítimo es 0,49
(`lluvia_media_est_mm` — la lluvia de hoy sí anticipa el caudal de mañana más allá
del caudal de hoy, es hidrología) y un proxy con 100 % de ruido da 0,38. Los rangos
se superponen. `audit.py` la **reporta** para que se pueda mirar, pero no asierta
sobre ella: un corte ahí barrería señal legítima.

Lo que la guarda cubre de verdad es el **régimen realista**: el accidente que
ocurre —una columna futura olvidada en el esquema, la fuga de la Decisión 040— es
una copia exacta o casi, y nadie le agrega 50 % de ruido a una fuga por accidente.
Ahí dispara siempre.

Contra un proxy fuertemente degradado la defensa no es estadística sino
**estructural**: saber cómo se construye cada columna. Eso es lo que hacen los
tests de ventanas de lluvia y de τ, que no miden correlación sino que inyectan un
valor y verifican el mecanismo. Esa capa no la reemplaza ningún umbral.

### Cuando lleguen las features de pronóstico (Fase 4)

Son legítimamente información sobre el futuro emitida en t₀, así que pueden
superar el umbral: sería un verdadero positivo del test y no una fuga. La salida
correcta es **declararlas en `audit.FUTURO_LEGITIMO`** con su justificación, nunca
bajar el umbral — bajarlo pierde la protección entera para acomodar un caso
previsto. Hay un test que verifica que ese mecanismo funciona.

## Modos del modulador

| Modo | Qué usa | Operable |
| --- | --- | --- |
| `antecedent` | Sólo 30 d de lluvia observada | **Sí, hoy** |
| `forecast` | 30 d observados + 14 d de pronóstico real | Cuando Gold tenga las columnas (Fase 4 del roadmap) |
| `oracle` | 30 d observados + lluvia observada futura | **No** — retrospectivo, pronóstico perfecto |

La **fuente de lluvia** del modulador se elige aparte con `--gate-rain`:
`lluvia_merge_alta_frontera_mm` (grilla MERGE de CPTEC, media areal, cobertura
completa — la preferible) o `lluvia_media_est_mm` (media por estación). `auto`
usa MERGE si la columna existe. **Hay que declararla al citar V⁺ o V⁻**: las dos
series correlacionan 0,90 y sus τ 0,93, pero V⁺ se mueve 0,10–0,15 según cuál se
use. El orden entre pérdidas no cambia; el valor absoluto sí.

`oracle` es el que usa el informe para el análisis histórico. No confundirlo con
`forecast`: hay un test (`test_modo_oracle_si_mira_el_futuro`) que deja escrito
que no es causal.

## Estado de los resultados

Corridos sobre **Gold v278** (`ana_74100000`, 9.617 días, 19 features, 8 horizontes),
TEST = 285 días. Detalle en `docs/funcion_ganancia_regimen.html` §08.

Lo que resiste las 5 configuraciones probadas (snapshot viejo/corregido,
19/26 features, modulador de estaciones/MERGE):

- **`mse_log` gana RMSE 5/5.** La transformación logarítmica es el factor de
  precisión, y no es discutible.
- **`gral` gana V⁻ (estiaje) 5/5**, y le gana a `mse_log` en V⁺, V⁻ y KGE **5/5**,
  a costa de ~30 m³/s de RMSE.
- **`gral` NO gana el escalar G-RAL de forma robusta** (2 de 5 contra `mse_log`).
  El argumento para adoptarlo son las tasas de violación, no el agregado.
- **`expectile_raw` gana V⁺ (crecida) 4/5**, pagando RMSE y falsas alarmas.

## Sobre el snapshot: dos guardas

`DEFAULT_SNAPSHOT` es el parquet que `export_gold_dataset.py --refresh` baja del
Volume. Al 2026-08-30 está en **delta 278, 9.734 filas, 66 columnas, 0 de nivel**.

Cargar un snapshot viejo falla en silencio: el parquet carga, el entrenamiento
corre y los números salen — calculados contra un target que Gold ya corrigió.
Pasó de verdad entre el 28 y el 30 de agosto de 2026, porque
`Export_Gold_Snapshot` es una tarea aparte que sólo se encadena dentro de los jobs
completos y las corridas ad hoc de Gold la saltean. `load_snapshot` tiene dos
guardas contra eso, que cubren cosas distintas:

| Guarda | Detecta | Cómo |
| --- | --- | --- |
| `_assert_schema_vigente` | Columnas que no deberían estar (snapshot previo a la Decisión 040) | Busca cualquier columna con `nivel` |
| `_assert_manifest_vigente` | **Valores viejos con esquema correcto** | `manifest.delta_version` contra `MIN_DELTA_VERSION`, más el `sha256` del parquet contra su manifest |

La segunda existe porque la primera deja un hueco: un snapshot con el esquema
correcto pero con los caudales previos a la Decisión 039 pasa sin ruido. Y lo
insidioso es que el manifest guarda la `delta_version` **del momento del export**,
así que un snapshot viejo se ve internamente consistente — nada delata el
desfasaje salvo compararlo contra algo externo. Acá ese algo externo es
`MIN_DELTA_VERSION = 278`, un piso fijo en el repo, para que la capa de datos no
tenga que hablar con Databricks. Cubre quedarse atrás; que **Gold avance por
delante** lo avisa `export_gold_dataset.py`, que sí consulta la historia de la
tabla (Decisión 042).

`MIN_DELTA_VERSION` sube sólo cuando otra corrección cambie los valores del
target. No es un "última versión conocida", es un piso de validez del dato.

Además, cada JSON de resultados registra en `snapshot` la `delta_version`, el
`exported_at`, el sha256, la fuente de lluvia del modulador y los grupos de features
usados: sin eso un resultado guardado no se puede fechar contra las correcciones
de Gold.

`training_dataset_v0_PRE039.parquet` se conserva a propósito: es el snapshot
previo a la corrección de telemetría, y es lo que permite reproducir la
comparación viejo/corregido de §08. Se lee con
`load_snapshot(LEGACY_SNAPSHOT, permitir_legacy=True)`.

## Limitaciones vigentes

- El modelo es un MLP de una capa oculta en NumPy, no el BiLSTM del plan. Sirve
  para comparar pérdidas con todo lo demás fijo, no para dar el mejor pronóstico.
- TEST son 285 días de un solo año hidrológico. Por eso todo se reporta como
  media ± desvío entre semillas, y las diferencias menores al desvío no se leen.
- Sin MLflow: los resultados van a JSON más el ledger JSONL. El logueo va cuando exista la app.
- `search.py` y `walkforward.py` no tienen `--no-test`, así que siguen calculando TEST
  aunque el corredor no lo lea. En `train.py` sí es estructural.
- Las predicciones no se guardan, sólo las métricas agregadas: sin eso no hay ensembles ni
  test de Diebold-Mariano ni hidrogramas. Es la brecha `G-05` del catálogo.
