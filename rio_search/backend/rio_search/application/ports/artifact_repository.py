"""Puerto de descarga de artefactos de un run de MLflow (Fase 6, docs/rio_search_plan.md §3.8,
paso 2: "carga el campeon (`run_id` -> `model/`, `preprocess/pipeline.pkl`, `features/spec.json`)
-- exactamente los artefactos del run"). Separado de `TrackingReadPort` (Fase 4) a proposito: ese
puerto lee metadatos de runs (tags/params/metricas/series), nunca contenido binario de
artefactos -- ampliarlo hubiera significado tocar `MlflowDatabricksTrackingReader`/
`CachedTrackingReader`, ya cerrados y testeados en la Fase 4, sin necesidad (la cache de lectura
de esa fase es para metadatos livianos, no para bajar checkpoints de varios KB en cada consulta
de la UI -- este puerto lo usa una sola vez por corrida de `IssueDailyForecast`, no en el camino
caliente de la API).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ArtifactRepositoryPort(Protocol):
    def download(self, run_id: str, artifact_path: str, dst_dir: Path) -> Path:
        """Descarga `artifact_path` (archivo o directorio) del run `run_id` a `dst_dir` y
        devuelve la ruta local resultante (archivo o directorio, segun lo pedido)."""
        ...
