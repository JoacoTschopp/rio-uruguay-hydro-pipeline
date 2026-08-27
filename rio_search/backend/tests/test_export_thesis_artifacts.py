"""Tests offline de `application.thesis.export_thesis_artifacts` (Fase 8, docs/rio_search_plan.md
§3.11, §5): un `TrackingReadPort` falso con metricas sinteticas `test/<metrica>/hNN` (mismo
formato que loguea `domain.experiments.metric_set.MetricSet.as_mlflow_metrics`, Fase 2), sin
tocar Databricks/MLflow real. Verifica que los `.tex`/`.pdf` se escriben, que llevan el `run_id`
en un comentario LaTeX (§3.11) y los casos de error (`run_id` inexistente o sin metricas)."""

from __future__ import annotations

import pytest

from rio_search.application.ports.tracking_read import RunRecord
from rio_search.application.thesis.export_thesis_artifacts import (
    ExportThesisArtifacts,
    ThesisExportError,
)


def _run(
    run_id: str, model: str, strategy: str, kge_by_h: dict[int, float], rmse_by_h: dict[int, float]
) -> RunRecord:
    metrics: dict[str, float] = {}
    for h, v in kge_by_h.items():
        metrics[f"test/kge/h{h:02d}"] = v
    for h, v in rmse_by_h.items():
        metrics[f"test/rmse/h{h:02d}"] = v
    metrics["val/kge/mean"] = sum(kge_by_h.values()) / len(kge_by_h)  # no debe filtrar a TEST
    return RunRecord(
        run_id=run_id,
        experiment_id="exp-1",
        status="FINISHED",
        start_time_ms=0,
        end_time_ms=100,
        artifact_uri=f"dbfs:/{run_id}",
        tags={"rio_search.model": model, "rio_search.horizon_strategy": strategy},
        params={},
        metrics=metrics,
    )


class FakeReader:
    def __init__(self, runs: list[RunRecord]) -> None:
        self._runs = {r.run_id: r for r in runs}

    def list_runs(self, experiment_names, max_results: int = 500) -> list[RunRecord]:
        return list(self._runs.values())

    def get_run(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list_children(self, parent_run_id, experiment_id, max_results: int = 200):
        return []

    def get_metric_history(self, run_id: str, metric_key: str):
        return []


BILSTM_RUN_ID = "bilstm0000001"
PERSISTENCE_RUN_ID = "persist0000002"


def _reader() -> FakeReader:
    bilstm = _run(
        BILSTM_RUN_ID,
        model="bilstm",
        strategy="multi_output",
        kge_by_h={1: -0.1, 2: 0.4, 7: 0.6, 14: 0.5},
        rmse_by_h={1: 120.0, 2: 150.0, 7: 200.0, 14: 210.0},
    )
    persistence = _run(
        PERSISTENCE_RUN_ID,
        model="persistence",
        strategy="multi_output",
        kge_by_h={1: 0.95, 2: 0.2, 7: -0.3, 14: -0.5},
        rmse_by_h={1: 20.0, 2: 180.0, 7: 400.0, 14: 450.0},
    )
    return FakeReader([bilstm, persistence])


def test_execute_writes_table_and_figure_with_run_id_comment(tmp_path) -> None:
    export = ExportThesisArtifacts(
        reader=_reader(), figures_dir=tmp_path / "figures", tables_dir=tmp_path / "tables"
    )

    result = export.execute(BILSTM_RUN_ID)

    assert result.table.path.exists()
    table_text = result.table.path.read_text(encoding="utf-8")
    assert f"run_id={BILSTM_RUN_ID}" in table_text
    assert "t+01" in table_text and "t+14" in table_text
    assert "-0.100" in table_text  # KGE h01, formateado a 3 decimales

    assert result.figure.pdf_path.exists()
    assert result.figure.pdf_path.stat().st_size > 0
    tex_text = result.figure.tex_path.read_text(encoding="utf-8")
    assert f"run_ids={BILSTM_RUN_ID}" in tex_text
    assert "includegraphics" in tex_text

    assert result.compare_table is None


def test_execute_with_compare_writes_comparison_table(tmp_path) -> None:
    export = ExportThesisArtifacts(
        reader=_reader(), figures_dir=tmp_path / "figures", tables_dir=tmp_path / "tables"
    )

    result = export.execute(BILSTM_RUN_ID, compare_run_ids=[PERSISTENCE_RUN_ID])

    assert result.compare_table is not None
    assert result.compare_table.path.exists()
    text = result.compare_table.path.read_text(encoding="utf-8")
    assert f"run_ids={BILSTM_RUN_ID},{PERSISTENCE_RUN_ID}" in text
    assert "bilstm" in text and "persistence" in text

    figure_tex = result.figure.tex_path.read_text(encoding="utf-8")
    assert f"run_ids={BILSTM_RUN_ID},{PERSISTENCE_RUN_ID}" in figure_tex


def test_execute_raises_for_unknown_run(tmp_path) -> None:
    export = ExportThesisArtifacts(
        reader=_reader(), figures_dir=tmp_path / "figures", tables_dir=tmp_path / "tables"
    )
    with pytest.raises(ThesisExportError):
        export.execute("no-existe")


def test_execute_raises_for_unknown_compare_run(tmp_path) -> None:
    export = ExportThesisArtifacts(
        reader=_reader(), figures_dir=tmp_path / "figures", tables_dir=tmp_path / "tables"
    )
    with pytest.raises(ThesisExportError):
        export.execute(BILSTM_RUN_ID, compare_run_ids=["no-existe"])


def test_execute_raises_when_run_has_no_horizon_metrics(tmp_path) -> None:
    parent = RunRecord(
        run_id="search-parent",
        experiment_id="exp-1",
        status="FINISHED",
        start_time_ms=0,
        end_time_ms=100,
        artifact_uri="dbfs:/search-parent",
        tags={},
        params={},
        metrics={"time/search_total_s": 123.0},  # run padre: sin metricas de horizonte
    )
    reader = FakeReader([parent])
    export = ExportThesisArtifacts(
        reader=reader, figures_dir=tmp_path / "figures", tables_dir=tmp_path / "tables"
    )
    with pytest.raises(ThesisExportError):
        export.execute("search-parent")
