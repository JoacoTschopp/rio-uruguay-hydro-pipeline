"""Migra a MLflow los resultados de la fase de estrategias corrida en `feature/fase-estrategias`
(el framework `rio_search/` sin MLflow, worktree `rio-uruguay-hydro-pipeline`), para que queden
visibles en la UI de esta app bajo la familia de experimento `fase_estrategias`.

Script standalone de infraestructura/tooling: NO toca `domain/`/`application/` de la app, sólo
los importa como librería (reusa `MlflowDatabricksTracking` y `flatten_params` reales, para
garantizar el mismo prefijo de tags / misma URI de tracking que un run real de la app).

Mapeo (documentado acá porque no hay un único lugar natural del dominio para esto):

  - Un run padre ("search", `nested=False`) agrupa toda la fase: `search__fase_estrategias_d303__<fecha>`
    bajo `/Users/<profile>/rio_search/fase_estrategias`.
  - Cada celda del ledger con `salida` (JSON propio) -> un run hijo ("trial", `nested=True`).
    - Celdas `tipo=train` (21): métricas en el mismo formato `{split}/{metrica}/h{NN}` y
      `{split}/{metrica}/mean` que ya usa `domain.experiments.metric_set.MetricSet.as_mlflow_metrics`
      (mismo patrón, sin reusar la clase porque el JSON de origen no tiene el mismo dataclass).
      Además `{split}/{metrica}/sd` (desviación entre semillas) porque el patrón de la app no
      tiene un concepto de "semilla" — ver limitación abajo.
    - Celdas `tipo=sensitivity|walkforward` (5): forma ad-hoc por celda (barrido, comparación de
      modos, walk-forward), sin un `models.<key>.val.mean/per_horizon` único. Se loguean con un
      flattener genérico (todo valor numérico del JSON, con su ruta como nombre de métrica) en
      vez de forzarlas al patrón de las 21 anteriores.
  - Idempotente: cada trial lleva los tags `rio_search.origen=fase_estrategias_migracion` y
    `rio_search.celda_id=<id>`; una corrida repetida del script salta las celdas que ya
    encuentra con esos tags bajo el experimento, no duplica.

Limitación consciente (no forzada): las 5 semillas de cada celda NO se loguean como runs nietos
(el patrón `nested=True` de horizonte que usa `per_horizon` es de la app, no hay un patrón
análogo para "semilla" en ningún lugar del código real) — se resumen como `mean` + `sd` en el
mismo run del trial. Si más adelante se necesita el detalle por semilla, es una extensión
aparte, no algo que este script debía inventar.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import mlflow  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402

from rio_search.infrastructure.databricks.sdk_client import DEFAULT_PROFILE  # noqa: E402
from rio_search.infrastructure.tracking.mlflow_databricks import MlflowDatabricksTracking  # noqa: E402
from rio_search.infrastructure.tracking.params import flatten_params  # noqa: E402

SOURCE_REPO = Path(r"C:\Users\tschoppj\proyectos_maestria\rio-uruguay-hydro-pipeline")
SOURCE_RESULTS = SOURCE_REPO / "rio_search" / "results"
LEDGER = SOURCE_RESULTS / "ledger.jsonl"
CAMPANA = "d303-a6262712"

EXPERIMENT_PATH = f"/Users/{DEFAULT_PROFILE}/rio_search/fase_estrategias"
GITHUB_URL = "https://github.com/JoacoTschopp/rio-uruguay-hydro-pipeline"
ORIGEN_TAG = "fase_estrategias_migracion"
VOLUME_PARQUET = "/Volumes/weather/raw/gold_export_volume/training_dataset_v0.parquet"

TRAIN_METRIC_NAMES = (
    "rmse", "mae", "nse", "kge", "gral", "pbias", "v_plus", "v_minus", "fa_wet", "fa_dry",
)


def git_sha_for(relpath: str) -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relpath],
        cwd=SOURCE_REPO, capture_output=True, text=True, encoding="utf-8",
    )
    sha = out.stdout.strip()
    return sha or "desconocido"


def load_ledger_rows() -> list[dict[str, Any]]:
    rows = []
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("campana") == CAMPANA and (r.get("salida") or "").endswith(".json"):
                rows.append(r)
    return rows


def already_migrated(client: MlflowClient, experiment_id: str, celda_id: str) -> bool:
    filt = (
        f"tags.`rio_search.origen` = '{ORIGEN_TAG}' "
        f"AND tags.`rio_search.celda_id` = '{celda_id}'"
    )
    runs = client.search_runs([experiment_id], filter_string=filt, max_results=1)
    return len(runs) > 0


def flatten_numeric(obj: Any, prefix: str = "", out: dict[str, float] | None = None) -> dict[str, float]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}/{k}" if prefix else str(k)
            flatten_numeric(v, key, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if obj == obj and abs(obj) != float("inf"):  # descarta NaN/inf, MLflow no las acepta bien
            out[prefix] = float(obj)
    return out


def log_train_cell(tracking: MlflowDatabricksTracking, row: dict, data: dict, rel_json: str) -> None:
    celda_id = row["celda"]
    model_key = next(iter(data["models"].keys()))
    model_block = data["models"][model_key]
    run_config = data.get("run_config", {})
    snapshot = data.get("snapshot", {})

    run_name = f"{celda_id}__{model_key}__{CAMPANA}"
    with tracking.start_run(EXPERIMENT_PATH, run_name, nested=True):
        tags = {
            "origen": ORIGEN_TAG,
            "tipo": "train",
            "celda_id": celda_id,
            "bloque": row.get("bloque", ""),
            "nombre": row.get("nombre", ""),
            "veredicto": row.get("veredicto", ""),
            "campana": CAMPANA,
            "model": model_block.get("model", model_key),
            "loss": model_block.get("loss", ""),
            "target_transform": model_block.get("target_transform", ""),
            "target_param": model_block.get("target_param", ""),
            "scaling": model_block.get("scaling", ""),
            "horizonte": run_config.get("horizonte", ""),
            "lookback": str(run_config.get("lookback", "")),
            "dataset_delta_version": str(snapshot.get("delta_version", "")),
            "dataset_sha256": snapshot.get("sha256", ""),
            "git_sha": git_sha_for(rel_json),
            "git_branch": "feature/fase-estrategias",
            "github_url": GITHUB_URL,
        }
        tracking.set_tags(tags)

        tracking.log_params({
            **flatten_params(model_block.get("model_hp", {}) or {}, prefix="model_hp"),
            **flatten_params(run_config, prefix="run_config"),
            "n_seeds": str(model_block.get("n_seeds", "")),
        })

        for split in ("val", "test"):
            split_block = model_block.get(split)
            if not split_block:
                continue
            metrics: dict[str, float] = {}
            mean = split_block.get("mean", {})
            for name in TRAIN_METRIC_NAMES:
                if name in mean and mean[name] == mean[name]:
                    metrics[f"{split}/{name}/mean"] = float(mean[name])
                sd_key = f"{name}_sd"
                if sd_key in mean and mean[sd_key] == mean[sd_key]:
                    metrics[f"{split}/{name}/sd"] = float(mean[sd_key])
            per_h = split_block.get("per_horizon", {})
            for h_key, h_block in per_h.items():
                if not h_key.startswith("h"):
                    continue
                hnum = int(h_key[1:])
                for name in TRAIN_METRIC_NAMES:
                    if name in h_block and h_block[name] == h_block[name]:
                        metrics[f"{split}/{name}/h{hnum:02d}"] = float(h_block[name])
                if "coverage" in h_block:
                    metrics[f"{split}/coverage/h{hnum:02d}"] = float(h_block["coverage"])
            if metrics:
                tracking.log_metrics(metrics)


def log_diagnostic_cell(tracking: MlflowDatabricksTracking, row: dict, data: dict, rel_json: str) -> None:
    celda_id = row["celda"]
    run_name = f"{celda_id}__{row.get('tipo', 'diagnostico')}__{CAMPANA}"
    with tracking.start_run(EXPERIMENT_PATH, run_name, nested=True):
        tracking.set_tags({
            "origen": ORIGEN_TAG,
            "tipo": row.get("tipo", "diagnostico"),
            "celda_id": celda_id,
            "bloque": row.get("bloque", ""),
            "nombre": row.get("nombre", ""),
            "campana": CAMPANA,
            "git_sha": git_sha_for(rel_json),
            "git_branch": "feature/fase-estrategias",
            "github_url": GITHUB_URL,
        })
        metrics = flatten_numeric(data)
        if metrics:
            items = list(metrics.items())
            for i in range(0, len(items), 200):
                tracking.log_metrics(dict(items[i : i + 200]))


def main() -> None:
    tracking = MlflowDatabricksTracking(profile=DEFAULT_PROFILE)
    client = MlflowClient()

    rows = load_ledger_rows()
    print(f"{len(rows)} celdas con JSON propio en la campana {CAMPANA}")

    started_at = datetime.now(timezone.utc)
    search_run_name = f"search__fase_estrategias_{CAMPANA}__{started_at.strftime('%Y%m%d-%H%M')}"

    # crea/reusa el experimento antes de decidir si el padre ya existe
    workspace_parent = "/".join(EXPERIMENT_PATH.split("/")[:-1])
    from rio_search.infrastructure.databricks.sdk_client import build_workspace_client
    build_workspace_client(profile=DEFAULT_PROFILE).workspace.mkdirs(workspace_parent)
    mlflow.set_tracking_uri(f"databricks://{DEFAULT_PROFILE}")
    mlflow.set_experiment(EXPERIMENT_PATH)
    experiment = client.get_experiment_by_name(EXPERIMENT_PATH)

    existing_parents = client.search_runs(
        [experiment.experiment_id],
        filter_string=f"tags.`rio_search.origen` = '{ORIGEN_TAG}' AND tags.`rio_search.tipo` = 'search'",
        max_results=1,
    )
    if existing_parents:
        parent_run_id = existing_parents[0].info.run_id
        print(f"search padre ya existe (run_id={parent_run_id}), no se crea de nuevo")
        mlflow.start_run(run_id=parent_run_id)
        parent_ctx = None
    else:
        parent_ctx = tracking.start_run(EXPERIMENT_PATH, search_run_name, nested=False)
        parent_ctx.__enter__()
        tracking.set_tags({
            "origen": ORIGEN_TAG,
            "tipo": "search",
            "campana": CAMPANA,
            "dataset_delta_version": "303",
            "git_sha": git_sha_for("rio_search"),
            "git_branch": "feature/fase-estrategias",
            "github_url": GITHUB_URL,
            "started_at": started_at.isoformat(),
        })
        tracking.log_params({"total_celdas": str(len(rows))})

    migrados, saltados, fallidos = 0, 0, []
    for row in rows:
        celda_id = row["celda"]
        if already_migrated(client, experiment.experiment_id, celda_id):
            print(f"  {celda_id}: ya migrada, salteo")
            saltados += 1
            continue
        rel_json = row["salida"].replace("\\", "/")
        json_path = SOURCE_REPO / rel_json
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if row.get("tipo") == "train":
                log_train_cell(tracking, row, data, rel_json)
            else:
                log_diagnostic_cell(tracking, row, data, rel_json)
            print(f"  {celda_id}: migrada ({row.get('tipo')})")
            migrados += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  {celda_id}: FALLO -- {exc}")
            fallidos.append((celda_id, str(exc)))

    if parent_ctx is not None:
        tracking.set_tags({"ended_at": datetime.now(timezone.utc).isoformat()})
        parent_ctx.__exit__(None, None, None)
    else:
        mlflow.end_run()

    print()
    print(f"Resumen: {migrados} migradas, {saltados} salteadas (ya existian), {len(fallidos)} fallidas")
    for celda_id, err in fallidos:
        print(f"  FALLO {celda_id}: {err}")


if __name__ == "__main__":
    main()
