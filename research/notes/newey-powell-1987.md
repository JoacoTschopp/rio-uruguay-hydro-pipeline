# Newey & Powell (1987) — Asymmetric Least Squares Estimation and Testing

**Rol:** de acá sale la familia de la función. Es la fuente primaria de `psi_tau`.

## Metodología

Define el **expectil** de nivel τ como el minimizador de una pérdida de mínimos cuadrados
asimétricos: `psi_tau(e) = |tau - 1{e < 0}| * e^2`. Es a la media lo que el cuantil de
Koenker & Bassett es a la mediana — con τ = 0,5 recupera la media condicional exactamente.

## Qué me llevo

1. **La identidad con el RMSE no es una casualidad del diseño**, es la propiedad definitoria
   de la familia: el expectil 0,5 *es* la media. Por eso G-RAL(τ=0,5) = RMSE hasta precisión
   de máquina, y por eso el test de partida del proyecto vale como verificación.
2. **La ventaja computacional que el paper destaca es exactamente la que importa acá**: la
   pérdida asimétrica cuadrática es diferenciable en todo el dominio, mientras la pinball no
   lo es en cero. Eso es lo que permite *entrenar* con G-RAL y no sólo evaluar.
3. El factor 2 de `psi_tau` en este proyecto es una normalización para que τ = 0,5 devuelva
   `e^2` y no `e^2/2`. No cambia nada del argumento, sólo hace que la identidad con RMSE se
   lea sin constantes.

## Lo que el paper NO da

El nivel τ es **fijo** — un parámetro del estimador. Que τ varíe día a día en función de una
covariable exógena es la extensión de esta tesis, y no está acá.

## Enlaces

- Sostiene: §01 y §06 de `docs/funcion_ganancia_regimen.html`.
- Implementado en `rio_search/models.py::ExpectileLoss` y `rio_search/metrics.py::gral`.
- Ver también [[koenker-bassett-1978]] (la familia alternativa) y
  [[ehm-2016-quantiles-expectiles]] (cuándo un score es consistente para un expectil).
