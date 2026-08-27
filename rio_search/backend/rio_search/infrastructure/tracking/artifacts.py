"""Helpers de artefactos (Fase 2, docs/rio_search_plan.md §3.5, §3.12, §3.13): escriben archivos
a un directorio temporal para que `TrackingPort.log_artifact_dir` los suba de una vez. Reimplementa
(no importa) el patron de `infrastructure.tracking.smoke` (Fase 0, ya verificado contra
Databricks real) para no tocar ese modulo -- Fase 0 quedo cerrada y su run `smoke` es la
referencia de que este mismo patron (patch + zip del paquete) funciona sin pandas.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from rio_search.application.ports.stopwatch import Stopwatch
from rio_search.domain.experiments.code_provenance import CodeProvenance


def write_code_artifacts(tmp_dir: Path, provenance: CodeProvenance, package_dir: Path) -> None:
    """`code/uncommitted.patch` + `code/package.zip` (§3.13): procedencia del codigo."""
    (tmp_dir / "uncommitted.patch").write_text(provenance.uncommitted_patch, encoding="utf-8")
    package_zip = tmp_dir / "package.zip"
    with zipfile.ZipFile(package_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in package_dir.rglob("*.py"):
            zf.write(path, arcname=str(path.relative_to(package_dir.parent)))


def write_json_artifact(tmp_dir: Path, filename: str, data: Any) -> None:
    (tmp_dir / filename).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def timings_payload(stopwatch: Stopwatch) -> dict[str, Any]:
    """`timings/timings.json` (§3.12): ultima medicion de cada clave `time/*` + historial
    completo (para series como `train_epoch_s` por epoch, aun sin uso en la Fase 2)."""
    metrics = stopwatch.as_metrics()
    names = [key[len("time/") :] for key in metrics if key.startswith("time/")]
    return {"metrics": metrics, "history": {name: stopwatch.history(name) for name in names}}
