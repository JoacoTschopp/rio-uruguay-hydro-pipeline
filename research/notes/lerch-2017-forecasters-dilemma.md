# Lerch, Thorarinsdottir, Ravazzolo & Gneiting (2017) — Forecaster's Dilemma

**Rol: es el fundamento teórico del Invariante 1** (§07 de la especificación). Sin este
paper, «el modulador no puede mirar el caudal observado» es una intuición; con él, es un
resultado publicado.

## Metodología

Muestran —con teoría, simulación y un caso real sobre inflación y PBI de EE.UU.— qué pasa
cuando se evalúa un pronóstico **restringiendo la muestra a los casos extremos observados**.

## El resultado que importa

**Condicionar la verificación sobre el resultado observado es incompatible con los supuestos
de los métodos de evaluación establecidos.** El score deja de ser propio, y el efecto no es
una pérdida de potencia sino una **inversión del ranking**: el procedimiento premia
sistemáticamente al pronosticador sesgado hacia el extremo y desacredita al pronosticador
calibrado. Es peor cuanto menor es la relación señal/ruido — que en caudal diario a 14 días
es exactamente el caso.

La salida que proponen no es dejar de mirar los extremos: son las **reglas de score
ponderadas propias**, donde el peso depende de la predicción o de un umbral fijo, nunca de
la observación (ver [[gneiting-ranjan-2011-weighted-scoring]]).

## Qué me llevo

1. **La tentación que el proyecto descartó tiene nombre y bibliografía.** «Esto fue una
   crecida, entonces la evalúo con τ = 0,8» es literalmente el dilema del pronosticador, y
   habría producido un ranking invertido, no un ranking ruidoso.
2. Justifica que el modulador se alimente de **lluvia** (antecedente y pronosticada) y no del
   caudal futuro: la lluvia está disponible en t₀, el caudal objetivo no.
3. **También ilumina la elección menos obvia**: no usar el caudal *actual* como modulador. Es
   más sutil que el caso prohibido —el caudal de hoy sí está disponible en t₀, así que no
   viola la propiedad de score propio— pero la evidencia de §02 muestra que selecciona la
   rama equivocada de la onda. Son dos objeciones distintas y conviene no mezclarlas: una es
   teórica, la otra es empírica.
4. Es la cita correcta para la frase «G-RAL sigue siendo un score propio».

## Enlaces

- Sostiene: §07 (Invariantes) de `docs/funcion_ganancia_regimen.html`.
- Implementado como test permanente en `rio_search/gate.py::assert_causal`.
- Ver también [[gneiting-raftery-2007-scoring-rules]] (qué es un score propio).
