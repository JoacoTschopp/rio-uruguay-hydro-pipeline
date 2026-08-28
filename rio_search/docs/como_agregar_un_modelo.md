# Cómo agregar un modelo nuevo a Rio_Search

`docs/rio_search_plan.md` §3.3: *"agregar un modelo nuevo = un archivo nuevo + un YAML de
experimento"*. Este documento no es una descripción abstracta del contrato — son los pasos
**reales** que se siguieron en la Fase 9 para agregar `ridge` (`sklearn.linear_model.Ridge` con
lags), verificado corriendo una búsqueda real contra Databricks/MLflow y viéndola en la UI junto a
`persistence`/`climatology`/`seasonal_naive`/`bilstm`.

## Precondición: entender el contrato antes de escribir código

Antes de tocar nada se leyeron los dos precedentes directos:

* `rio_search/backend/rio_search/application/ports/model_adapter.py` — el `Protocol`
  `ModelAdapterPort` que cualquier adaptador implementa **por duck typing** (no hereda la clase):
  `name`, `family`, `supports`, `build()`, `fit()`, `predict()`, `save()`, `load()`.
* `rio_search/backend/rio_search/domain/models/model_registry.py` — el decorador
  `@register_model("nombre")` que registra la clase en un dict global de módulo; el `ModelRegistry`
  sólo lee ese dict.
* Un adaptador simple (`rio_search/backend/rio_search/infrastructure/models/naive/persistence.py`)
  y uno con entrenamiento real (`rio_search/backend/rio_search/infrastructure/models/torch/bilstm.py`
  + `base_torch_adapter.py`) — para ver cómo se resuelven `fit()`/`save()`/`load()` en la práctica,
  no sólo en el `Protocol`.

## Paso 1: un archivo nuevo bajo `infrastructure/models/<familia>/`

`ModelFamily` (`domain/models/model_family.py`) ya definía `NAIVE | SKLEARN | TORCH` desde la
Fase 2, pero hasta la Fase 9 sólo había adaptadores `NAIVE` y `TORCH` — `ridge` es el primero
`SKLEARN`. Se creó `rio_search/backend/rio_search/infrastructure/models/sklearn/ridge.py` con:

```python
@register_model("ridge")
class RidgeAdapter:
    name = "ridge"
    family = ModelFamily.SKLEARN
    supports = {HorizonStrategy.MULTI_OUTPUT, HorizonStrategy.PER_HORIZON}
    def build(self, spec, n_features, n_outputs, device) -> None: ...
    def fit(self, train, val, training, callbacks=None, train_y=None, val_y=None) -> FitResult: ...
    def predict(self, X) -> Predictions: ...
    def save(self, path) -> None: ...
    @classmethod
    def load(cls, path, device) -> "RidgeAdapter": ...
```

Decisiones concretas tomadas al escribirlo (el porqué de cada una, no sólo el qué):

1. **Cómo reusar `Sequences.X` (`N, lookback, n_features`)**: es el mismo tensor con el que ya
   entrena BiLSTM (una LSTM lo recorre paso a paso). `sklearn.linear_model.Ridge` no modela el
   tiempo por sí solo, así que `_flatten()` aplana `(lookback, n_features)` a un vector por fila —
   eso **es** el "ridge con lags" del plan (§5, Fase 9): cada feature rezagado dentro de la
   ventana entra como una columna explícita de la regresión.
2. **Multi-output real, sin `sklearn.multioutput.MultiOutputRegressor`**: se necesitaba enmascarar
   por columna de horizonte antes de ajustar (siguiente punto), y `MultiOutputRegressor` no separa
   máscaras distintas por columna de salida — se implementó el bucle a mano (un `Ridge` por
   columna de horizonte, guardados en `self._models: list[Ridge]`).
3. **`Targets.y` trae `NaN` reales** (huecos de calendario, §2.1, Decisión 043 ya documentó el
   mismo problema para BiLSTM) — pero `Ridge.fit()` **no acepta NaN en absoluto** (a diferencia de
   PyTorch, que sólo diverge si no se enmascara antes de la pérdida). Se enmascara **por fila,
   antes de `.fit()`**, columna por columna: `mask = np.isfinite(y_col); model.fit(X_train[mask],
   y_col[mask])`. Se agregó un test específico
   (`test_fit_masks_nan_targets_per_column_and_does_not_crash`) y otro para el caso extremo de una
   columna de horizonte enteramente en `NaN`
   (`test_fit_handles_a_horizon_column_with_no_valid_target_at_all`).
4. **`epochs=1`, no `epochs=0`**: los baselines naive (Fase 2) reportan `FitResult(epochs=0, ...)`
   porque no ajustan ningún parámetro. Ridge sí ajusta parámetros reales (se resuelve en forma
   cerrada, sin iterar) — se optó por reportar un único "epoch" con una loss real (MSE medio sobre
   los horizontes con target válido) para que `time/train_to_best_epoch_s`,
   `time/train_samples_per_s` y un punto de `train/loss`+`val/loss` en MLflow tengan contenido real
   en vez de quedar vacíos (§3.12: los tiempos son un resultado de la tesis, no telemetría
   descartable).
5. **Serialización sin flavor de MLflow**: mismo criterio pragmático que Decisión 039 (BiLSTM no
   usa `mlflow.pytorch.log_model` porque importa pandas incluso en `mlflow-skinny`) — `save()`
   hace `pickle.dump(self._models, ...)` + un `architecture.json` con metadatos, en vez de
   `mlflow.sklearn.log_model`. `pickle`/`sklearn` operan sobre `numpy.ndarray` puro en este
   adaptador (nunca un `DataFrame`), así que no viola la Decisión #9 (Polars, nunca pandas) —
   `test_no_pandas_in_env` lo sigue verificando sin cambios.

## Paso 2: registrar el import (una línea en `infrastructure/`)

`infrastructure/models/__init__.py` importa cada submódulo por su efecto secundario
(`@register_model` corre al importar el módulo). Se agregó una línea:

```python
from rio_search.infrastructure.models.sklearn import ridge as _ridge  # noqa: F401
```

Sin este import, `RidgeAdapter` nunca se registra aunque el archivo exista — `ModelRegistry.get("ridge")`
fallaría con `KeyError`. Este archivo vive en `infrastructure/`, igual que el adaptador.

## Paso 3: un YAML de experimento nuevo

`rio_search/backend/configs/experiments/ridge_baseline_v1.yaml`: mismo `dataset`/`split`/`features`/
`sequence.lookback_days` que `bilstm_baseline_v1.yaml` (Fase 3) **a propósito** — mismo dataset,
misma ventana, para que la comparación en la UI sea "manzanas con manzanas" entre bilstm y ridge, no
sólo entre ridge y los naive. Sólo cambia el bloque `model:`:

```yaml
model:
  name: ridge
  horizon_strategy: multi_output
  params: {alpha: 1.0}
tracking:
  experiment: /Users/joaquintschopp@gmail.com/rio_search/ridge
  register_model: false
```

`training:` sigue presente con valores por defecto aunque `RidgeAdapter` no itere epochs: lo exige
`TrainingSpec`/`ExperimentConfig` como VO común a todo modelo (§4.1) — el adaptador simplemente no
usa la mayoría de esos campos.

## Paso 4: correr la búsqueda real

```
uv run rio-search search run configs/experiments/ridge_baseline_v1.yaml
```

Sin ningún flag ni código adicional: `RunSearch` (`application/experiments/run_search.py`) resuelve
el adaptador vía `ModelRegistryPort.get(model.name)`, y como `RidgeAdapter.family` no es
`ModelFamily.NAIVE`, `_prepare_trial_data` ya lo enruta por `BuildFeatureMatrix` (columnas reales de
`features.groups`) exactamente igual que a BiLSTM (Decisión 040: "cualquier familia que no sea NAIVE"
usa `BuildFeatureMatrix", no hubo que tocar esa rama). Corrida real: `search_run_id` en
`/Users/joaquintschopp@gmail.com/rio_search/ridge`, 1 trial, métricas por horizonte y split en TEST/VAL,
`test/skill_vs_persistence/h01=-0.085` (mismo patrón que BiLSTM: skill negativo en h01, consistente
con la Decisión 043).

## Paso 5: verlo en la UI junto a los demás modelos

**Hallazgo real de esta fase**: `application/experiments/list_runs.py::DEFAULT_EXPERIMENT_FAMILIES`
(`("baselines", "bilstm", "smoke", "daily_forecast")`) es una lista fija de "familias" de experimento
que `GET /api/searches`/`GET /api/runs` usan **cuando no se pasa `families=` explícito** — vive en
`application/`, así que agregar `"ridge"` ahí habría violado el criterio de cierre de esta fase ("el
modelo nuevo entra sin tocar `domain/` ni `application/`"). No hizo falta tocarlo: la página
Búsquedas ya tenía un filtro de texto libre por familias (`SearchesPage.tsx`, input
`familyInput` → `GET /api/searches?families=...`) desde la Fase 5 — sólo se agregó `"ridge"` a
`KNOWN_FAMILY_HINTS` (un array de sugerencias del `<datalist>`, puramente cosmético) en
`frontend/src/pages/SearchesPage.tsx`, cambio 100% en `frontend/` (ni `domain/`, ni `application/`,
ni siquiera `backend/interfaces/`). Verificado con navegador headless real: filtrando por
`baselines,bilstm,ridge` en `http://127.0.0.1:8000/`, la búsqueda `search__ridge_baseline_v1__...`
aparece en la lista junto con `persistence`/`climatology`/`seasonal_naive`/`bilstm`, con su tag
`rio_search.model=ridge`, tiempos y estado — y el detalle del trial (`/runs/<run_id>`) muestra su
config completa, tags de procedencia/hardware y métricas por horizonte, 0 errores de consola, 0
requests fallidos.

## Paso 6: tests offline

`rio_search/backend/tests/test_ridge_adapter.py` (10 tests: contrato, `fit()` sin targets,
`FitResult` de un solo "epoch", forma de la predicción, que efectivamente aprende algo mejor que la
media, roundtrip de guardado/carga, `per_horizon` con `n_outputs=1`, dos variantes de `NaN` en el
target) + una aserción agregada a `tests/test_model_registry.py`
(`test_ridge_adapter_is_registered_after_importing_infrastructure_models`). 377 tests en verde en
total (367 previos + 10 nuevos), sin romper nada; `ruff check` limpio.

## Verificación final del criterio de extensibilidad

```
git diff --stat -- rio_search/backend/rio_search/domain rio_search/backend/rio_search/application
```

vacío (sin salida) tras agregar `ridge`: el modelo entró sin tocar ninguna de esas dos capas —
todo el cambio de "modelo" vivió en `infrastructure/` (adaptador + registro de import) y en
`configs/` (YAML). El único archivo fuera de `backend/` que se tocó para esta fase fue
`frontend/src/pages/SearchesPage.tsx`, y sólo para un atajo de UI, no para que el modelo
funcionara (el filtro de texto libre ya lo soportaba).

## Receta corta (para el próximo modelo)

1. Familia `NAIVE`/`SKLEARN`/`TORCH` según corresponda; si es `TORCH`, heredar
   `infrastructure/models/torch/base_torch_adapter.py::BaseTorchAdapter` e implementar sólo
   `_build_network()` (ver `bilstm.py`, 55 líneas en total). Si no, implementar
   `ModelAdapterPort` directo (ver `ridge.py`).
2. `@register_model("nombre")` sobre la clase.
3. Una línea en `infrastructure/models/__init__.py` importando el módulo nuevo.
4. Un YAML en `configs/experiments/` con `model.name: nombre`.
5. `rio-search search run configs/experiments/<nombre>.yaml`.
6. Si hace falta verlo sin pasar `?families=` a mano: agregar la familia de `tracking.experiment`
   a `KNOWN_FAMILY_HINTS` en `frontend/src/pages/SearchesPage.tsx` (opcional, sólo UX) — nunca a
   `DEFAULT_EXPERIMENT_FAMILIES` de `application/` si el objetivo es no tocar esa capa.
7. Tests offline del adaptador (arquitectura, `NaN`, roundtrip de serialización, ambas
   `horizon_strategy`) siguiendo `test_bilstm_adapter.py`/`test_ridge_adapter.py` como plantilla.
