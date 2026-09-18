"""Serie diaria de ψ_τ por modelo y horizonte — vista de análisis, no una celda.

    python -m rio_search.daily_series --modelo ancla
    python -m rio_search.daily_series --todos

Pedido directo de Joaquín: "ver si los modelos fallan en los mismos días o en
días distintos, y cruzarlo con el régimen (τ) de esos días". El escalar de VAL
que guarda cada celda del catálogo (`results/<campana>/<celda>__*.json`) ya
promedia sobre 365 días y 8 horizontes — a propósito, es lo que hace comparable
una celda con otra. Este módulo abre esa media: para un finalista puntual,
guarda `(fecha, horizonte, τ, ψ_τ)` fila por fila.

**No toca el criterio de gana/empata/pierde.** No corre por `runner.py`, no
escribe en `results/ledger.jsonl`, no cambia ningún `estado` de
`experiments/matrix.yaml`. Es opt-in por diseño: hay que invocar este módulo a
mano, nunca se dispara desde una corrida normal del catálogo.

Reglas, iguales a las de `ensemble.py` porque responden a la misma pregunta
("qué predicción publicaría un operador"):
- La predicción es la media de las 5 semillas en el **espacio de evaluación
  (m³/s)** — una serie por (modelo, horizonte), no cinco.
- Sólo VAL. TEST no se toca acá (R3).
- ψ_τ es la pieza elemento a elemento que `gral()` promedia
  (`metrics.expectile_se_series`, log=True, la misma convención que reportan
  los JSON de las celdas) — así el promedio de esta serie reproduce el `gral`
  por horizonte ya guardado, verificado en los tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as data_mod
from . import gate as gate_mod
from . import metrics as metrics_mod
from . import runner as runner_mod
from .ensemble import promedio_predicciones
from .train import run_experiment, _utf8_console

__all__ = ["FINALISTAS", "serie_diaria", "_a_serie_larga", "main"]

#: Los 5 finalistas identificados al cierre del grupo B/C de la fase
#: (rio_search/PLAN.md). `kw` va a `run_experiment`; `groups` a
#: `data.build_dataset`. Replica exactamente el `cmd` de la celda en
#: `experiments/matrix.yaml`, no una config nueva.
FINALISTAS: dict[str, dict] = {
    "ancla":       {"celda": "B0.06", "kw": {"model": "mlp", "loss": "gral",
                    "hidden": 38, "lr": 0.0492, "l2": 0.000217, "epochs": 378}},
    "huber_log":   {"celda": "B1.07", "kw": {"model": "mlp", "loss": "huber_log",
                    "hidden": 38, "lr": 0.0492, "l2": 0.000217, "epochs": 378}},
    "per_horizon": {"celda": "B5.02", "kw": {"model": "mlp", "loss": "gral",
                    "hidden": 38, "lr": 0.0492, "l2": 0.000217, "epochs": 378,
                    "per_horizon": True}},
    "xgboost":     {"celda": "B4.08", "kw": {"model": "xgb", "loss": "gral",
                    "lr": 0.05, "l2": 1.0, "epochs": 500, "patience": 30}},
    "ecmwf":       {"celda": "B2.19", "kw": {"model": "mlp", "loss": "gral",
                    "hidden": 38, "lr": 0.0492, "l2": 0.000217, "epochs": 378},
                    "groups": ("caudal_estado", "caudal_agregado_alta_frontera",
                              "lluvia_ratio", "estacionalidad", "pronostico_ecmwf")},
}


def _dataset(groups, snapshot):
    params = gate_mod.GateParams(tau_max=0.85)
    ds = data_mod.build_dataset(target="caudal", tau_mode="oracle", gate_params=params,
                                snapshot_path=snapshot, groups=groups,
                                gate_rain_col="lluvia_media_est_mm")
    return ds, data_mod.make_splits(ds.fecha)


def _a_serie_larga(ds, splits, pred: np.ndarray, modelo: str) -> pd.DataFrame:
    """La parte pura: de `(ds, splits, predicción (n_val, H) en m³/s)` a la tabla
    larga `(modelo, fecha, horizonte, tau, psi_tau)`.

    Separada de `serie_diaria` para poder testearla con un dataset sintético,
    sin tocar el snapshot real ni entrenar nada.
    """
    va = splits.val
    fecha_va = ds.fecha[va].to_numpy()
    tau_va = ds.tau[va]
    filas = []
    for j, h in enumerate(ds.horizons):
        psi, ok = metrics_mod.expectile_se_series(ds.Y[va][:, j], pred[:, j], tau_va)
        filas.append(pd.DataFrame({
            "fecha": fecha_va[ok], "horizonte": f"h{h:02d}",
            "tau": tau_va[ok], "psi_tau": psi,
        }))
    df = pd.concat(filas, ignore_index=True)
    df.insert(0, "modelo", modelo)
    return df.sort_values(["horizonte", "fecha"]).reset_index(drop=True)


def serie_diaria(nombre: str, seeds, *, snapshot=None) -> pd.DataFrame:
    """`(fecha, horizonte, tau, psi_tau)` de VAL, un finalista, media de semillas.

    `psi_tau` reproduce el `gral` por horizonte del **ensemble de semillas**
    (la misma predicción que evaluaría B10.01 para este miembro, no el
    promedio-de-métricas que guarda la celda individual — son números
    distintos a propósito, ver `ensemble.py`): `sqrt(psi_tau.groupby(
    'horizonte').mean())` reproduce ese `gral` por horizonte exactamente
    (test `test_daily_series.py::test_serie_real_reproduce_el_ensemble_de_semillas`).
    """
    conf = FINALISTAS[nombre]
    groups = tuple(conf.get("groups") or data_mod.DEFAULT_GROUPS)
    ds, splits = _dataset(groups, snapshot)
    preds = [run_experiment(ds, splits, seed=s, evaluar_test=False,
                            return_predictions=True, **conf["kw"])["predicciones"]["val"]
             for s in seeds]
    pred = promedio_predicciones(np.stack(preds))   # (n_val, H), m3/s
    return _a_serie_larga(ds, splits, pred, nombre)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--modelo", choices=list(FINALISTAS))
    g.add_argument("--todos", action="store_true")
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--out-dir", default=None,
                   help="default: rio_search/results/<campana>/diario/")
    args = p.parse_args(argv)
    _utf8_console()

    seeds = [args.seed + i for i in range(max(1, args.seeds))]
    campana, _ = runner_mod.dataset_id(Path(args.snapshot) if args.snapshot else None)
    out_dir = Path(args.out_dir) if args.out_dir else (
        data_mod.REPO_ROOT / "rio_search" / "results" / campana / "diario")
    out_dir.mkdir(parents=True, exist_ok=True)

    nombres = list(FINALISTAS) if args.todos else [args.modelo]
    for nombre in nombres:
        df = serie_diaria(nombre, seeds, snapshot=args.snapshot)
        out_path = out_dir / f"{nombre}.parquet"
        df.to_parquet(out_path, index=False)
        resumen = df.groupby("horizonte")["psi_tau"].apply(lambda s: np.sqrt(s.mean()))
        print(f"  {nombre:12s} → {out_path}  ({len(df)} filas, "
              f"gral por horizonte: {resumen.round(4).to_dict()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
