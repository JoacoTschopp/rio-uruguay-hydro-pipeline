# Toth (2016) — Asymmetric error functions for flood warning thresholds

**Rol:** el precedente operativo. Demuestra que la asimetría en alerta de crecidas ya se
usa, se publica y funciona — y **mide el precio que cobra**, que es el mismo que paga G-RAL.

## Metodología

Estima umbrales de alerta de crecida en cuencas no aforadas con redes neuronales entrenadas
con **funciones de error asimétricas**, con grados crecientes de asimetría, contra el
entrenamiento simétrico tradicional.

## El argumento de costo

Las consecuencias de un umbral de alerta **sobrestimado** (que lleva a **perder alarmas**)
tienen mucha menos aceptación que las de un umbral subestimado (que lleva a falsas alarmas).
Es el mismo razonamiento asimétrico que esta tesis, aplicado al umbral en vez de al caudal.

**Ojo con el signo al citarlo.** Toth penaliza *sobrestimar el umbral*; esta tesis penaliza
*subestimar el caudal*. Las dos apuntan a lo mismo —evitar la alarma perdida— pero la
dirección aritmética es opuesta porque el objeto es distinto. Es un error fácil de cometer
al escribir el capítulo.

## Qué me llevo

1. **El intercambio está medido y es el mismo que acá**: la función asimétrica reduce
   sustancialmente los errores de sobrestimación, a costa de **aumentar** los de
   subestimación, y aun así la precisión global sigue siendo aceptable. Es exactamente lo
   que muestra §08 (`gral` compra V⁻ y KGE pagando unos 30 m³/s de RMSE).
2. Que la conclusión «la precisión global sigue siendo aceptable» ya esté publicada en HESS
   le saca a esta tesis la carga de defender por primera vez que degradar el RMSE a
   propósito es legítimo.
3. Toth usa una asimetría **fija**; el modulador variable sigue siendo el aporte.

## Pendiente

El resumen accesible no da la forma funcional exacta de su función de error asimétrica.
**Hay que bajar el PDF y verificarla** antes de afirmar en la tesis que es o no de la familia
expectil — es una comparación que el tribunal puede pedir.

## Enlaces

- Sostiene: §06 (decisión «familia expectil») de `docs/funcion_ganancia_regimen.html`.
- Ver también [[matte-2017-beyond-cost-loss]] para la formalización económica del costo.
