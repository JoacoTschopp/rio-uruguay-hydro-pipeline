"""Puerto de tracking (Fase 2, docs/rio_search_plan.md §3.5): jerarquia de runs
busqueda -> trial (-> horizonte), tags/params/metricas, artefactos y `MetaDataset`. Precedente
directo: `infrastructure.tracking.smoke` (Fase 0) probo que `mlflow-skinny` alcanza sin pandas
para exactamente estos caminos (tags, tiempos, procedencia, `MetaDataset`, artefactos); este
puerto generaliza ese mismo patron para que `application.experiments.run_search.RunSearch` no
dependa de `mlflow` directamente (testeable offline con un `TrackingPort` falso, §5).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class RunHandle:
    run_id: str
    experiment_id: str


class TrackingPort(Protocol):
    def start_run(
        self, experiment_path: str, run_name: str, nested: bool = False
    ) -> AbstractContextManager[RunHandle]:
        """`with tracking.start_run(...) as run: ...`. `nested=False` asegura que exista el
        experimento y arranca el run padre (busqueda); `nested=True` abre un run hijo (trial u
        horizonte) dentro del run activo (§3.5: jerarquia busqueda -> trial -> horizonte)."""
        ...

    def set_tags(self, tags: dict[str, str]) -> None:
        """Tags `rio_search.*` (§3.5): el adaptador antepone el prefijo; este puerto recibe
        nombres sin prefijo (`git_sha`, no `rio_search.git_sha`)."""
        ...

    def log_params(self, params: dict[str, Any]) -> None:
        """Config YAML aplanada (§3.5, p. ej. `model.hidden_size`), sin prefijo."""
        ...

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        """Metricas jerarquicas (`test/rmse/h01`, `time/train_total_s`, §3.5/§3.12), sin
        prefijo."""
        ...

    def log_artifact_dir(self, local_dir: Path, artifact_path: str) -> None:
        """Sube todo el contenido de `local_dir` bajo `artifact_path` (p. ej. `code/`,
        `timings/`, `predictions/`, §3.5)."""
        ...

    def log_meta_dataset(self, name: str, digest: str, source_path: str, context: str) -> None:
        """`MetaDataset` (§3.5): nombre, digest y origen del dataset sin materializarlo."""
        ...

    def register_model(self, run_id: str, artifact_path: str, name: str) -> str:
        """Registro en Unity Catalog (Decision #12, §3.5, Fase 3): `name` con formato completo
        `<catalog>.<schema>.<model>` (p. ej. `weather.ml.rio_search_bilstm`), `artifact_path`
        el artefacto plano ya subido por `save()`/`log_artifact_dir` (Decision 039 -- **no**
        `mlflow.pytorch.log_model`, esta llamada no depende de ese flavor). Devuelve la version
        registrada como `str` (p. ej. `"1"`)."""
        ...
