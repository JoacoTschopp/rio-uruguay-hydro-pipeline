# Plan de implementación — fase de estrategias

Una fase, muchos commits, un merge. `main` queda reservada al armado del dataset
(Databricks); la integración de predicción vive en **`main-predic`**, y el merge que
cierra la fase va ahí.

Estado al arrancar (2026-09-15): campaña vigente `d303`, ancla en val/gral
**0,4948 ± 0,0098**, 75 celdas sin implementar en `experiments/matrix.yaml`.
El alcance de esta fase es **los controles y diagnósticos (todos) y las 19
estrategias P1**. Las P2/P3 quedan para la fase siguiente. Los resultados son
orientativos, no concluyentes.

## Disciplina de ramas y de agentes

- `main` es sólo dataset (Databricks); `main-predic` es la integración de predicción.
  El agente del dataset trabaja en su propio worktree y en rama propia colgada de
  `main`; las ramas de predicción cuelgan de `main-predic`.
- Cada tramo/PR lo **desarrolla un sub-agente**. El orquestador define el encargo y,
  una vez realizado, verifica que los tests pasen y que el commit esté hecho antes de
  dar el tramo por cerrado.

## La regla de cada celda

Se trabaja **una celda por vez**, nunca dos estrategias abiertas a la vez:

1. Implementar lo mínimo que la celda pide, con test unitario si hay lógica nueva.
2. Correrla contra la campaña vigente: `python -m rio_search.runner --celda <id>`.
   Sólo VAL — TEST no se mira hasta el cierre (B11).
3. El veredicto contra el ancla lo da el umbral de ruido (2σ); la fila queda en el
   ledger. Si **gana**, pasa a candidata; el campeón sólo cambia por el criterio
   completo (menor G-RAL con V⁺/V⁻ no peores que la persistencia).
4. Actualizar `estado` en `matrix.yaml` y **commit** (una celda, o un par natural,
   por commit).
5. Recién entonces, la siguiente.

Presupuesto por corrida: 600 s. Lo que excede se anota y se corre junto al final del
tramo con `--incluir-largas`.

## Tramo 0 — base y cirugía de ramas

1. El agente del dataset commitea lo suyo pendiente en el árbol
   (`notebooks_local/catalogo.py` y el destino del zip de la estación ANA).
2. Commits lógicos de la base de predicción — framework, protocolo, investigación,
   documentos — hoy sin versionar, para que cada tramo posterior tenga un diff legible.
3. Nace `main-predic` desde `main` y se le mergea lo actual de
   `feature/ana-backfill-automation`. Desde acá, todo lo futuro de predicción integra
   contra `main-predic`; `main` queda sólo para el dataset.
4. Los tramos siguientes corren en una rama de trabajo colgada de `main-predic`.

## Tramo 1 (PR-1) — controles y diagnósticos, todos, testeados con lo de hoy

No compiten por el campeonato: informan. Sin ellos, ninguna ganancia posterior es
atribuible ni creíble.

| Celda | Qué es | Qué responde |
| --- | --- | --- |
| B0.05 | seasonal naive | Tercera vara junto a persistencia y climatología. Sin entrenamiento. |
| B1.06 | expectil con τ constante | **El control de atribución**: separa «la asimetría ayuda» de «el modulador ayuda». |
| B8.04 | barrido de κ, pesos y ventanas | ¿Las conclusiones dependen de la perilla del modulador o son robustas? |
| B8.05 | modulador en modo forecast | Desbloqueada por las columnas ECMWF: τ calculado con el pronóstico real en vez del oráculo. Antes de correr, medir la cobertura temporal de `ecmwf_cf_tp_mm_*`. |
| B11.03 | significancia entre finalistas | Diebold-Mariano sobre las diferencias diarias de pérdida (en VAL), complementa el umbral de ruido. |

Además, dentro del tramo: correr las largas ya implementadas que `--todo` salteó
(B6.02, B6.04, walk-forward, ~35 min) con `--incluir-largas`.

Cierre del tramo: informe corto — qué mueve, qué no, y si el control B1.06 confirma
que el modulador aporta algo por encima de la asimetría fija.

## Tramos 2+ — una estrategia P1 por tramo

Orden por costo de implementación creciente y dependencias agrupadas. Cada ítem es un
tramo con la regla de arriba.

**A — baratas, sin dependencias nuevas (NumPy):**

1. B2.17 — lookback / ventana explícita de features
2. B2.12 — índice de precipitación antecedente (API)
3. B2.13 — derivadas de recesión del caudal
4. B5.02 — un modelo por horizonte (per_horizon)
5. B3.04 — target diferencial
6. B3.03 — raíz cuarta / Box-Cox / Yeo-Johnson
7. B7.02 — escalado robusto (mediana / IQR)
8. B1.07 — Huber
9. B1.10 — NSE-loss
10. B4.03 — MLP profundo
11. B10.01 — promedio entre semillas (casi gratis: reutiliza corridas existentes)
12. B10.02 — promedio entre configuraciones

**B — la apuesta del dato nuevo:**

13. B2.19 — features de pronóstico numérico (ECMWF). Desbloqueada por las 35 columnas
    nuevas. Es la celda con más potencial de la fase: el modelo pasa a ver la lluvia
    futura. Misma advertencia que B8.05: primero medir cobertura.

**C — nueva dependencia (pip install xgboost lightgbm):**

14. B4.08 — XGBoost
15. B4.09 — LightGBM

**D — torch (instalación CUDA local, GPU disponible):**

16. B4.13 — DLinear / NLinear
17. B4.14 — LSTM
18. B4.15 — BiLSTM
19. B4.18 — TCN

Instalar torch desbloquea de paso B9.02 (GPSampler); queda para la fase P2, no se
corre en esta.

El orden dentro de A–D se puede alterar si un resultado lo justifica (p. ej., si
B2.19 gana fuerte, adelantar las familias que mejor la exploten); el cambio se anota
en el ledger, no se discute en silencio.

## Cierre — un merge

1. Elegir campeón por el criterio completo (G-RAL + V⁺/V⁻ vs. persistencia) sobre VAL.
2. Correr B11 sólo para el campeón: walk-forward de confirmación y la **única** mirada
   a TEST de toda la fase, más B11.03 entre finalistas.
3. Registrar la decisión de cierre en `docs/decisions.md` (resultados orientativos,
   campeón, controles).
4. Merge a `main-predic`.

## Qué queda explícitamente afuera

- Todas las P2/P3 (incluye B4.28 GR4J/HBV, transformers, DeepAR, etc.).
- B2.11 (sub-cuencas aguas abajo): sigue `requiere_autorizacion`, riesgo de fuga.
- B9 completo (infraestructura de búsqueda de HP): se implementa cuando haya más de
  una familia ganadora que tunear.
