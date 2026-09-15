# Santos, Thirel & Perrin (2018) — Pitfalls in using log-transformed flows within the KGE

**Rol: es una advertencia que roza a este proyecto.** Hay que leerla con cuidado para saber
si aplica o no, porque la respuesta es «no, pero por poco» y eso hay que poder explicarlo.

## Qué dice

El caudal log-transformado se usa habitualmente para enfocar el desempeño en caudales bajos:
limita la heterocedasticidad de los residuos y **se aplicó largamente en criterios basados en
residuos cuadráticos, como el NSE**. Pero usarlo **dentro del KGE** (o KGE') no es adecuado y
puede producir problemas numéricos y una **evaluación sesgada** del desempeño.

## Por qué NO invalida el diseño de esta tesis

Hay que ser preciso acá:

- **G-RAL aplica el log dentro de un criterio cuadrático** (`psi_tau` es error cuadrático
  ponderado). Ése es justamente el uso que el paper describe como establecido y correcto.
- **El KGE de este proyecto se calcula sobre caudal SIN transformar.** Verificado en
  `rio_search/metrics.py`: `kge()` recibe los valores en m³/s, y `_evaluate_split` le pasa
  las series crudas. No se hace lo que el paper desaconseja.

**Conviene decir las dos cosas explícitamente en la tesis**, porque un lector que conozca
este paper va a levantar la mano al ver «log» y «KGE» en la misma tabla de resultados.

## Qué me llevo

1. Es la cita que **respalda** la decisión de la escala, no la que la ataca — siempre que se
   aclare dónde se aplica el log.
2. **Es también una guarda de regresión conceptual**: si alguna vez alguien decide reportar
   KGE sobre caudal transformado «para que sea coherente con G-RAL», este paper dice por qué
   no.
3. Su continuación, [[thirel-2024-streamflow-transformations]], compara transformaciones y
   concluye que log, Box-Cox y potencia 0,2 son las mejores de propósito general. Eso nombra
   a las competidoras del log y es exactamente la celda **B3.03** del catálogo de búsqueda.

## Enlaces

- Sostiene: §06 (decisión «medir el error en logaritmo») de `docs/funcion_ganancia_regimen.html`.
- Relacionado con la celda B3.03 de `rio_search/experiments/matrix.yaml`.
