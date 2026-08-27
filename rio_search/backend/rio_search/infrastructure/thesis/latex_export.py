"""Render de figuras/tablas para la tesis (Fase 8, docs/rio_search_plan.md §3.11): recibe
metricas ya extraidas de MLflow (nunca DataFrames -- Decision #9, Polars nunca pandas; aca ni
siquiera Polars hace falta, son ``dict[tuple[str, int], float]``) y escribe:

* ``thesis/tables/*.tex``: tablas LaTeX (``booktabs``, igual estilo que el modelo del usuario en
  ``research/templates/``) con el/los ``run_id`` de origen en un comentario al inicio del archivo.
* ``thesis/figures/*.pdf`` + ``thesis/figures/*.tex``: la figura (matplotlib, backend ``Agg``,
  sin GUI -- corre igual en un servidor sin display) y un snippet ``\\begin{figure}...\\end{figure}``
  que la incluye, tambien con el/los ``run_id`` en un comentario -- es el archivo que un capitulo
  de la tesis hace ``\\input``.

``application.thesis.export_thesis_artifacts.ExportThesisArtifacts`` es el unico llamador; este
modulo no conoce ``TrackingReadPort`` ni MLflow, solo recibe ``SeriesData`` ya armado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")  # sin GUI/display -- corre en CLI y en CI (§3.11)

import matplotlib.pyplot as plt  # noqa: E402

GENERATED_HEADER = (
    "% Generado por `rio-search thesis export` (ExportThesisArtifacts, "
    "docs/rio_search_plan.md S3.11/S4.2). No editar a mano: volver a correr el comando "
    "despues de una corrida nueva en MLflow.\n"
)

METRIC_LABELS: dict[str, str] = {
    "rmse": "RMSE (m$^3$/s)",
    "mae": "MAE (m$^3$/s)",
    "mape": "MAPE (\\%)",
    "kge": "KGE",
    "nse": "NSE",
    "pbias": "PBIAS (\\%)",
    "r2": "R$^2$",
    "skill_vs_persistence": "Skill vs. persistencia",
    "peak_mae": "MAE en picos (m$^3$/s)",
    "peak_bias": "Sesgo en picos (m$^3$/s)",
    "coverage": "Cobertura",
}


def _escape(text: str) -> str:
    """Escapado minimo para texto libre (etiquetas de modelo/tag) en modo texto de LaTeX."""
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("_", r"\_")
        .replace("%", r"\%")
        .replace("&", r"\&")
        .replace("#", r"\#")
    )


def _fmt(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "--"
    return f"{value:.3f}"


def _short(run_id: str) -> str:
    return f"{run_id[:12]}..." if len(run_id) > 12 else run_id


@dataclass(frozen=True, slots=True)
class SeriesData:
    """Una corrida (``run_id``) con sus metricas ``horizonte -> {metrica: valor}`` para un split
    fijo (``test`` por defecto, §3.7: "TEST se reporta una vez") y una etiqueta legible para
    leyenda/tabla (p. ej. ``"bilstm (multi_output)"``)."""

    run_id: str
    label: str
    horizons: tuple[int, ...]
    values: dict[tuple[str, int], float]  # (metrica, horizonte) -> valor

    def get(self, metric: str, horizon: int) -> float | None:
        return self.values.get((metric, horizon))


@dataclass(frozen=True, slots=True)
class ExportedTable:
    path: Path
    run_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExportedFigure:
    pdf_path: Path
    tex_path: Path
    run_ids: tuple[str, ...]


def write_metrics_table(
    output_path: Path,
    series: SeriesData,
    metrics: Sequence[str],
    split: str = "test",
) -> ExportedTable:
    """Tabla de una sola corrida: filas = horizonte, columnas = metricas pedidas."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = " & ".join(METRIC_LABELS.get(m, m) for m in metrics)
    col_spec = "l" + "r" * len(metrics)
    lines = [
        GENERATED_HEADER,
        f"% run_id={series.run_id}\n",
        "\\begin{table}[H]\n",
        "\\centering\n",
        f"\\caption{{M\\'etricas por horizonte en {split.upper()} -- {_escape(series.label)} "
        f"(\\texttt{{run\\_id={_escape(_short(series.run_id))}}}).}}\n",
        f"\\label{{tab:metrics-{series.run_id[:12]}}}\n",
        f"\\begin{{tabular}}{{{col_spec}}}\n",
        "\\toprule\n",
        f"Horizonte & {columns} \\\\\n",
        "\\midrule\n",
    ]
    for h in series.horizons:
        row = " & ".join(_fmt(series.get(m, h)) for m in metrics)
        lines.append(f"t+{h:02d} & {row} \\\\\n")
    lines += ["\\bottomrule\n", "\\end{tabular}\n", "\\end{table}\n"]
    output_path.write_text("".join(lines), encoding="utf-8")
    return ExportedTable(path=output_path, run_ids=(series.run_id,))


def write_comparison_table(
    output_path: Path,
    series: Sequence[SeriesData],
    metrics: Sequence[str],
    split: str = "test",
) -> ExportedTable:
    """Tabla comparativa: filas = horizonte, columnas = (corrida x metrica)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    horizons = sorted({h for s in series for h in s.horizons})
    header_cells = [f"{_escape(s.label)} {METRIC_LABELS.get(m, m)}" for s in series for m in metrics]
    col_spec = "l" + "r" * len(header_cells)
    run_ids = tuple(s.run_id for s in series)
    caption_ids = ", ".join(_escape(_short(r)) for r in run_ids)
    lines = [
        GENERATED_HEADER,
        f"% run_ids={','.join(run_ids)}\n",
        "\\begin{table}[H]\n",
        "\\centering\n",
        f"\\caption{{Comparaci\\'on de m\\'etricas en {split.upper()} por horizonte "
        f"(\\texttt{{run\\_ids: {caption_ids}}}).}}\n",
        f"\\label{{tab:compare-{run_ids[0][:12]}}}\n",
        f"\\begin{{tabular}}{{{col_spec}}}\n",
        "\\toprule\n",
        "Horizonte & " + " & ".join(header_cells) + " \\\\\n",
        "\\midrule\n",
    ]
    for h in horizons:
        row_cells = [_fmt(s.get(m, h)) for s in series for m in metrics]
        lines.append(f"t+{h:02d} & " + " & ".join(row_cells) + " \\\\\n")
    lines += ["\\bottomrule\n", "\\end{tabular}\n", "\\end{table}\n"]
    output_path.write_text("".join(lines), encoding="utf-8")
    return ExportedTable(path=output_path, run_ids=run_ids)


def write_metric_figure(
    output_stem: Path,
    metric: str,
    series: Sequence[SeriesData],
    split: str = "test",
) -> ExportedFigure:
    """``<output_stem>.pdf`` (matplotlib) + ``<output_stem>.tex`` (snippet ``figure`` que lo
    incluye desde un capitulo, con el/los ``run_id`` en comentario, §3.11)."""
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    pdf_path = output_stem.with_suffix(".pdf")
    tex_path = output_stem.with_suffix(".tex")
    run_ids = tuple(s.run_id for s in series)

    fig, ax = plt.subplots(figsize=(6, 4))
    for s in series:
        xs = list(s.horizons)
        ys = [s.get(metric, h) for h in xs]
        ax.plot(xs, ys, marker="o", label=s.label)
    ax.set_xlabel("Horizonte (dias)")
    ax.set_ylabel(METRIC_LABELS.get(metric, metric))
    ax.set_title(f"{METRIC_LABELS.get(metric, metric)} vs. horizonte ({split.upper()})")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(
        pdf_path,
        metadata={
            "Subject": f"run_ids={','.join(run_ids)}",
            "Title": f"{metric} vs horizonte ({split})",
        },
    )
    plt.close(fig)

    caption = (
        f"{METRIC_LABELS.get(metric, metric)} vs. horizonte en {split.upper()} para "
        + ", ".join(_escape(s.label) for s in series)
    )
    caption_ids = ", ".join(_escape(_short(r)) for r in run_ids)
    tex_content = (
        GENERATED_HEADER
        + f"% run_ids={','.join(run_ids)}\n"
        + "\\begin{figure}[H]\n"
        "\\centering\n"
        f"\\includegraphics[width=0.85\\textwidth]{{../figures/{pdf_path.name}}}\n"
        f"\\caption{{{caption} (\\texttt{{run\\_ids: {caption_ids}}}).}}\n"
        f"\\label{{fig:{output_stem.name}}}\n"
        "\\end{figure}\n"
    )
    tex_path.write_text(tex_content, encoding="utf-8")
    return ExportedFigure(pdf_path=pdf_path, tex_path=tex_path, run_ids=run_ids)
