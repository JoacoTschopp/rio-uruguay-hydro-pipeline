# Análisis de la fase de estrategias — campaña d303

Documento de análisis, no de decisión. No declara campeón — esa decisión queda
explícitamente para más adelante. Cubre las 55 celdas P1 del catálogo, corridas entre
los Tramos 1 y 14 sobre la campaña `d303-a6262712` (9.754 filas, split VAL:
2024-08-11 → 2025-08-10, 365 días). Fuente de cada número: `rio_search/results/ledger.jsonl`
para el veredicto oficial, los JSON de `rio_search/results/d303-a6262712/` para el
detalle, y los parquet de `d303-a6262712/diario/` para la serie día a día.

## 1. Resumen ejecutivo

Se corrieron 18 estrategias de modelado, 5 controles/diagnósticos y 2 walk-forward de
confirmación — 25 celdas en total, todas contra el mismo ancla (MLP tanh, gral
0,4948 ± 0,0098). Seis estrategias le ganan al ancla dentro del umbral de ruido; la
mejor por un margen grande es **B2.19 (features de pronóstico ECMWF, gral 0,4204)**,
casi el doble de la mejora del segundo mejor resultado individual (XGBoost, 0,4570).
Pero el hallazgo que atraviesa toda la fase es otro: **ninguna de las 18 estrategias
— incluido el ancla que hoy está en producción — deja de sobrestimar en régimen seco
más que la simple persistencia** (V⁻). Ver la lluvia futura (ECMWF) es lo único que
se acerca. Y una segunda pieza, que viene del arnés de series diarias del Tramo 12:
los candidatos con mejor G-RAL **fallan en los mismos días**, no en días distintos —
lo que pone un techo bajo a cualquier ensemble entre ellos y sugiere que el problema
no es de qué modelo se usa, sino de qué información falta.

## 2. Tabla completa de resultados

VAL, ordenada por G-RAL (menor es mejor). `sd` es la desviación entre 5 semillas.
Skill = 1 − RMSE/RMSE(persistencia).

| Celda | Nombre | G-RAL | sd | Veredicto | V⁺ | V⁻ | Skill |
|---|---|---:|---:|---|---:|---:|---:|
| — | **persistencia** (ref.) | 0,5199 | — | — | 0,526 | 0,487 | 0,000 |
| — | climatología 30 d (ref.) | 0,6041 | — | — | 0,450 | 0,888 | — |
| **B2.19** | features ECMWF | **0,4204** | 0,0133 | **gana** | 0,380 | 0,565 | 0,202 |
| **B4.08** | XGBoost | 0,4570 | 0,0004 | **gana** | 0,352 | 0,807 | 0,129 |
| **B10.02** | ensemble huber+ph+dinámica | 0,4706 | 0,0045 | **gana** | 0,396 | 0,809 | 0,152 |
| **B1.07** | Huber en log | 0,4751 | 0,0053 | **gana** | 0,455 | 0,764 | 0,163 |
| **B10.01** | ensemble entre semillas | 0,4787 | 0,0027 | **gana** | 0,370 | 0,746 | 0,117 |
| **B5.02** | per_horizon | 0,4822 | 0,0039 | **gana** | 0,389 | 0,804 | 0,123 |
| B1.06 | expectil τ constante | 0,4871 | 0,0113 | empata | 0,355 | 0,846 | 0,103 |
| — | **ancla** (producción) | 0,4948 | 0,0098 | — | 0,380 | 0,729 | — |
| B3.03 | Box-Cox/Yeo-Johnson | 0,4948 | 0,0073 | empata | 0,387 | 0,711 | 0,059 |
| B2.13 | dinámica del caudal | 0,4921 | 0,0031 | empata | 0,364 | 0,798 | 0,092 |
| B7.02 | escalado robusto | 0,5016 | 0,0082 | empata | 0,375 | 0,579 | 0,078 |
| B4.03 | MLP profundo (2 capas) | 0,5076 | 0,0183 | empata | 0,371 | 0,739 | 0,093 |
| B2.12 | índice de precipitación (API) | 0,5148 | 0,0146 | pierde | 0,331 | 0,818 | 0,035 |
| B4.18 | TCN | 0,5155 | 0,0097 | descartado | 0,353 | 0,730 | −0,024 |
| B4.15 | BiLSTM | 0,5182 | 0,0065 | pierde | 0,395 | 0,881 | 0,064 |
| B4.14 | LSTM | 0,5196 | 0,0159 | pierde | 0,356 | 0,835 | 0,088 |
| B2.17 | ventana/lookback aplanada | 0,5720 | 0,0176 | descartado | 0,393 | 0,797 | −0,023 |
| B4.13 | DLinear/NLinear | 0,6024 | 0,0000 | descartado | 0,318 | 0,969 | −0,276 |
| B0.05 | seasonal naive | 0,6781 | — | descartado | 0,249 | 0,982 | −0,032 |
| B3.04 | target diferencial | 0,6560 | 0,0109 | descartado | 0,244 | 0,888 | −0,195 |
| B1.10 | NSE-loss | 0,6318 | 0,0652 | pierde | 0,362 | 0,793 | 0,058 |

## 3. Lectura por eje

### Pérdidas — B1.06, B1.07, B1.10

El control de atribución (B1.06, τ constante en 0,65) **empata** con el ancla
(0,4871 vs 0,4948, dentro del umbral): en VAL, la asimetría fija rinde igual que la
asimetría modulada día a día. El aporte de que τ varíe con el estado del río sigue
sin demostrarse en la media, aunque **Huber en log (B1.07) sí gana**, y con la mitad
del ruido del ancla — la lectura conjunta es que lo que sostiene la mejora no es sólo
"log + asimetría", es **"log + acotar el gradiente de los días extremos"**: Huber
gana porque los ~20 días de pico dejan de arrastrar el entrenamiento del resto del
año. NSE-loss (B1.10) pierde feo (0,6318, 6× el ruido de dispersión): normalizar por
varianza no sustituye al logaritmo.

### Features a mano — B2.12, B2.13, B2.17

Los tres pierden, empatan o se descartan en la media. B2.12 (índice de precipitación
antecedente) pierde: la humedad que resume ya está en los acumulados existentes, tres
columnas correlacionadas de más sólo agregan ruido. B2.17 (ventana cruda aplanada) se
descarta y empeora monótonamente con el largo de la ventana (30→120 días). La
excepción es **B2.13 (dinámica del caudal — razón log, curvatura, pendiente de
recesión)**: empata en media (0,4921) pero con **un tercio de la dispersión** del
ancla (sd 0,0031 vs 0,0098) — no gana por media, gana por varianza, y es insumo
natural para los modelos secuenciales.

### Target — B3.03, B3.04

**Box-Cox/Yeo-Johnson con λ libre por máxima verosimilitud** eligió λ = −0,10 —
prácticamente el logaritmo — y da el mismo resultado que el ancla (Δ = 0,0000). Esto
convierte "el log es el factor de precisión" de una comparación de dos alternativas
en una conclusión por verosimilitud: un continuo de transformaciones aterrizó solo en
el log. El target diferencial (B3.04) se descarta feo (skill −0,195): predecir el
delta ayuda contra el expectil crudo comparado limpio, pero el espacio crudo en sí
pierde igual — la síntesis (delta en log) es B3.05, no corrida en esta fase.

### Estrategia de horizonte — B5.02

Per_horizon **gana** en G-RAL (0,4822, ocho modelos especializados en vez de un
multi-salida), con la ganancia concentrada en los extremos (h01 y sobre todo h14,
donde el multi-salida es más débil). Pero la vista por horizonte con NSE (no G-RAL)
muestra una paradoja: **en h02/h03, per_horizon tiene NSE muy inferior al ancla**
(0,241/0,237 vs 0,505/0,385), pese a que el G-RAL por horizonte ahí es similar o
levemente mejor. Es una divergencia real entre lo que optimiza el criterio de la fase
(G-RAL, asimétrico y regido por régimen) y lo que mide NSE (simétrico, sensible a
varianza total) — "ganar en G-RAL" no es lo mismo que "ganar en todas las métricas
clásicas", y vale la pena mostrarlo así, no ocultarlo.

| Modelo | 1–3 d (NSE) | 4–7 d (NSE) | 8–14 d (NSE, sólo h14) |
|---|---:|---:|---:|
| ancla | 0,545 | 0,165 | −0,118 |
| huber_log | 0,561 | 0,324 | 0,000 |
| per_horizon | 0,403 | 0,216 | −0,002 |
| xgboost | 0,540 | 0,225 | −0,065 |
| ecmwf | 0,526 | **0,439** | **−0,364** |

huber_log es el más parejo entre las tres franjas horarias, sin depender de un
horizonte particular. ECMWF es el caso más extremo: lidera 4–7 días por lejos, pero es
el peor de todos en h14 — justo donde se esperaría que ver la lluvia futura ayude más.

### Preprocesamiento y arquitectura — B7.02, B4.03

Ninguno de los dos es el eje. El escalado robusto (mediana/IQR) empata (0,5016) —
mejora el V⁻ puntualmente (0,579, el mejor de toda la tabla) pero no el G-RAL. El MLP
más profundo (2 capas) empata y las exploratorias de 3–4 capas empeoran
monótonamente: el techo del MLP no es el tamaño de la red.

### Ensembles — B10.01, B10.02

**Ambos ganan.** B10.01 (promedio entre las 5 semillas del ancla) es la mejora más
barata de la fase: cero entrenamiento nuevo, gral 0,4787. B10.02 (huber_log +
per_horizon + dinámica del caudal, promediadas en m³/s) da 0,4706, el mejor de los
ensembles y confirma que huber_log y per_horizon **suman** por caminos
independientes (el par solo ya da 0,4700, mejor que cada miembro). Pero el techo es
bajo: la correlación diaria de ψ_τ entre finalistas es de 0,72 a 0,94 (sección 5) —
los modelos fallan juntos, así que promediarlos no cancela error como lo haría un
ensemble de modelos independientes. Además, **el V⁻ del ensemble (0,809) hereda el
defecto de sus miembros**, no lo arregla.

### Información nueva — B2.19 (ECMWF)

El mejor resultado individual de la fase, y por un margen grande: 0,4204, **5× el
umbral de ruido** por debajo del ancla. Verificado que no es un artefacto de la
cobertura del 68% de las columnas ECMWF: la comparación limpia, entrenando sólo sobre
el subconjunto con cobertura completa, da prácticamente el mismo número (0,4212).
Es también el único finalista que **mejora el V⁻** en vez de heredarlo (0,565 vs 0,729
del ancla) — la sección 4 muestra por qué eso importa. Su fragilidad específica: en
h14 tiene el peor NSE de todos (−0,364, sección 3), probablemente porque la cola de
8–14 días del pronóstico es poco confiable a esa distancia y el modelo sobreajusta a
una señal ruidosa ahí.

### Familia de modelo — B4.08, B4.13, B4.14, B4.15, B4.18

De cinco familias nuevas probadas, sólo **XGBoost gana** (0,4570, objetivo custom con
grad/hess analíticos de la pérdida expectil, mismas 19 features que el ancla). Las
cuatro basadas en torch pierden o se descartan: DLinear (lineal puro, 0,6024,
descartado — ni siquiera con no-linealidad la ventana cruda ayuda), LSTM (0,5196,
HP prestados del MLP con lr alto y corte temprano), BiLSTM (0,5182, HP corregidos del
arnés — un tercio de la dispersión del LSTM, pero el signo no cambia) y TCN (0,5155,
descartado, y ni siquiera fue más rápido que el LSTM como sugería la literatura para
este tamaño de ventana). La lectura honesta: **ninguna familia recurrente/convolucional
terminó de correr con una búsqueda de hiperparámetros real** — todas usaron valores
declarados, no tuneados (eso es B9, P2, no corrido en esta fase). La pregunta de si
un LSTM bien tuneado supera al MLP (Kratzert et al. 2018/2019) sigue abierta, no
cerrada en contra.

### Sensibilidad del modulador — B8.04, B8.05

El barrido de κ, pesos y ventanas del modulador (27 configuraciones) da un rango de
0,4816 a 0,5137 — cerca de 3× el umbral de ruido extremo a extremo, con un patrón
consistente: más peso al pronóstico (w_fc alto) mejora, 50/50 con ventana antecedente
larga es lo peor. La configuración declarada (κ=2,2, w_ant=0,35/w_fc=0,65, ant=30d)
queda a mitad de tabla — es sensibilidad, no un llamado a ajustar por VAL.

El modo forecast del modulador (B8.05, con el pronóstico ECMWF real en vez del
oráculo) recupera casi toda la ventaja del oráculo: oracle 0,5018, forecast 0,5068,
antecedente 0,5669, medido sobre 6.548 días de intersección común (2006-11-29 a
2026-08-24). Es la confirmación de que el modo operable en producción no pierde casi
nada frente al modo ideal que sólo se puede correr en retrospectiva.

## 4. El problema transversal: V⁻

Ningún candidato de las 25 celdas corridas deja de sobrestimar en régimen seco más
que la persistencia (V⁻ de referencia: 0,487). Ni siquiera el ancla que está en
producción (0,729) lo cumple. Ordenados de mejor a peor V⁻:

| Celda | V⁻ | Distancia a persistencia (0,487) |
|---|---:|---:|
| persistencia (ref.) | 0,487 | — |
| **B2.19 ecmwf** | **0,565** | +0,078 |
| B7.02 escalado robusto | 0,579 | +0,092 |
| B3.03 Box-Cox/Yeo-Johnson | 0,711 | +0,224 |
| ancla (producción) | 0,729 | +0,242 |
| B4.18 tcn | 0,730 | +0,243 |
| B10.01 ensemble semillas | 0,746 | +0,259 |
| B4.03 MLP profundo | 0,739 | +0,252 |
| B1.07 huber_log | 0,764 | +0,277 |
| B1.10 nse_loss | 0,793 | +0,306 |
| B2.13 dinámica del caudal | 0,798 | +0,311 |
| B2.17 lookback | 0,797 | +0,310 |
| B5.02 per_horizon | 0,804 | +0,317 |
| B4.08 xgboost | 0,807 | +0,320 |
| B10.02 ensemble top3 | 0,809 | +0,322 |
| B2.12 API | 0,818 | +0,331 |
| B4.14 lstm | 0,835 | +0,348 |
| B1.06 τ constante | 0,846 | +0,359 |
| B4.15 bilstm | 0,881 | +0,394 |
| B3.04 target delta | 0,888 | +0,401 |
| B4.13 dlinear | 0,969 | +0,482 |
| B0.05 seasonal naive | 0,982 | +0,495 |

Ninguna de las 18 estrategias de modelado atacó el V⁻ de frente — es un efecto
lateral que unas empeoran más que otras, nunca el objetivo. ECMWF es la única señal
que lo mueve de forma sustancial, y sigue sin cerrar la brecha. Esto sugiere que el
sesgo en seco no es un problema de qué modelo se entrena sobre las features actuales,
sino de qué información le falta al conjunto de features para anticipar esos días.

## 5. La correlación diaria (Tramo 12)

Sobre h01, correlación de ψ_τ diario entre los 5 finalistas con serie guardada:

| | ancla | ecmwf | huber_log | per_horizon | xgboost |
|---|---:|---:|---:|---:|---:|
| ancla | 1,000 | 0,801 | 0,910 | 0,941 | 0,793 |
| ecmwf | 0,801 | 1,000 | 0,728 | 0,799 | 0,724 |
| huber_log | 0,910 | 0,728 | 1,000 | 0,900 | 0,788 |
| per_horizon | 0,941 | 0,799 | 0,900 | 1,000 | 0,828 |
| xgboost | 0,793 | 0,724 | 0,788 | 0,828 | 1,000 |

Todos los pares correlacionan entre 0,72 y 0,94 — **los modelos fallan en los mismos
días**. ECMWF es el más distinto del grupo (0,72–0,80 con el resto), consistente con
que trae información genuinamente nueva; los otros cuatro, que comparten las mismas
19 features, están más pegados entre sí (0,79–0,94). Esto explica por qué B10.02
(ensemble) mejora pero no arrasa: promediar modelos que fallan juntos no cancela
error de la forma en que lo haría un ensemble de modelos independientes.

Cruzando con τ: en los 20 peores días del ancla (h01), τ medio es 0,608, casi igual
al 0,651 del resto de los días — no hay una concentración clara en régimen extremo.
Entre los 10 peores días hay tanto τ=0,269 como τ=0,836. **Lo que hace difíciles a
esos días no es el régimen que el modulador ya captura** — es otra cosa (posiblemente
transiciones abruptas o eventos que ninguna de las features actuales anticipa), y es
un candidato concreto para mirar caso por caso si eso resulta de interés.

## 6. Walk-forward de confirmación (B6.02, B6.04)

Corridas independientes, con re-tuneo de hiperparámetros por fold (TPE, 30 trials),
sobre folds de TEST — no comparables directamente con la tabla VAL de la sección 2,
pero confirman la estabilidad de lo encontrado en 2026-09-05 sobre d278:

| Config | gral (test, 4 folds) | sd entre folds |
|---|---:|---:|
| expandible (10 años train) | 0,6334 | 0,196 |
| deslizante (10 años train) | 0,6390 | 0,184 |
| deslizante (5 años train) | 0,6563 | 0,212 |

Expandible y deslizante de 10 años empatan — la ventana de entrenamiento no es el
eje. La deslizante de 5 años es claramente peor (menos historia, peor resultado). La
deriva de hiperparámetros entre folds es grande (lr de 0,006 a 0,095, hidden de 16 a
234) — la búsqueda encuentra óptimos muy distintos según qué años caen en TRAIN, señal
de que el problema está lejos de estar sobre-ajustado a una configuración fija.

## 7. Qué queda abierto

- **B9 (búsqueda de HP real)**: LSTM, BiLSTM, TCN y XGBoost corrieron con
  hiperparámetros declarados, no tuneados. La pregunta de si alguna familia nueva
  destrona al MLP con HP propios sigue sin cerrarse.
- **ECMWF combinado con huber_log/per_horizon**: nunca se probó esa combinación —
  B10.02 combinó huber_log+per_horizon+dinámica del caudal, pero no incluyó ECMWF, que
  es el eje más distinto (correlación 0,72–0,80 con el resto) y el único candidato
  natural para bajar más el techo del ensemble.
- **El V⁻ en sí mismo**: ninguna de las 18 estrategias lo atacó de frente. Sigue sin
  investigarse qué distingue a los días de sobrestimación sistemática.
- **Celdas P2/P3 no corridas**: 51 celdas fuera del alcance P1 de esta fase (ver
  `rio_search/experiments/matrix.yaml`, incluye B3.05 razón logarítmica, CatBoost,
  N-BEATS/N-HiTS, Transformer, modelos conceptuales GR4J/HBV, entre otras).
- **B2.11** (sub-cuencas aguas abajo) sigue bloqueada por `requiere_autorizacion` —
  contradice la Decisión 018, no se tocó.
