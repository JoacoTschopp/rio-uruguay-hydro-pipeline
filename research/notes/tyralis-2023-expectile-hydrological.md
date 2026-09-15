# Tyralis, Papacharalampous & Khatami (2023) — Expectile-based hydrological modelling

**Rol: es el precedente más cercano que existe.** Cualquier defensa de esta tesis pasa por
explicar en qué se parece y en qué no.

## Metodología

Calibran modelos conceptuales de la familia GR usando **pérdida expectil** en lugar de
mínimos cuadrados, sobre **511 cuencas** de EE.UU. Estiman expectiles a niveles
**0,5 / 0,9 / 0,95 / 0,975** y los usan para construir bandas de incertidumbre.

## En qué coincide con esta tesis

- La maquinaria matemática es **la misma**: mínimos cuadrados asimétricos de
  [[newey-powell-1987]] aplicados a caudal diario.
- El argumento de que los expectiles son más sensibles a la cola que los cuantiles, porque
  usan la distancia y no sólo la frecuencia.
- La conclusión de que se puede calibrar un modelo hidrológico con una pérdida asimétrica
  sin que se rompa nada.

## En qué se separa — y esto es el aporte

| | Tyralis et al. 2023 | Esta tesis |
| --- | --- | --- |
| **τ** | Fijo por corrida (0,5 / 0,9 / 0,95 / 0,975) | **Varía día a día**: τ(t) |
| **Qué determina τ** | Lo elige el modelador: es el nivel del expectil que se quiere estimar | Una **señal exógena**: lluvia antecedente + pronóstico |
| **Para qué** | Estimar **incertidumbre** — varias corridas dan una banda | Codificar **costo operativo** — una sola corrida, asimetría que cambia con el régimen |
| **Salida** | Una familia de expectiles = distribución predictiva | Un pronóstico puntual evaluado con un peso que depende del día |
| **Modelo** | Conceptual (GR) | ML (MLP hoy; el catálogo abre a LSTM/GBM) |

**La diferencia de fondo:** ellos usan el expectil como *estimador de un funcional de la
distribución*; acá se usa como *función de costo declarada*. Son dos usos legítimos y
distintos de la misma pérdida, y conviene decirlo así en la tesis para no parecer que se
está reinventando lo que ellos hicieron.

## Qué me llevo

1. **El aporte no es "usar expectiles en hidrología"** — eso ya está hecho y publicado en
   Journal of Hydrology. El aporte es **hacer que τ dependa del estado de la cuenca**.
2. Que ellos hayan corrido 511 cuencas y acá haya una sola es una limitación real que hay
   que declarar, no esconder.
3. Su enfoque de bandas es complementario, no competidor: si esta tesis llega al pronóstico
   probabilístico, el camino natural es el de ellos más el modulador como función de peso.

## Pendiente

Bajar el PDF a `research/documents/` y verificar si en algún lado consideran τ variable. Si
lo descartan explícitamente, esa frase es la mejor cita posible para justificar el aporte.

## Enlaces

- Contrasta con: §01 y §06 de `docs/funcion_ganancia_regimen.html`.
- Ver también [[gneiting-ranjan-2011-weighted-scoring]] para el camino probabilístico.
