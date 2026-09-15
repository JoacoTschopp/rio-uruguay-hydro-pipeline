"""Protocolo de sensibilidad de τ_max, y contraste oráculo vs causal.

Es el protocolo prometido en §04 del informe: τ_max codifica un
costo operativo declarado, no un parámetro ajustable, así que lo mínimo que hay
que mostrar es **si la conclusión depende de él**.

    python -m rio_search.sensitivity                      # barrido de τ_max
    python -m rio_search.sensitivity --tau-modes          # oráculo vs causal

El segundo contraste importa porque hoy no hay columnas de pronóstico en Gold
(Fase 4 del roadmap). El modo `oracle` usa lluvia observada futura como
sustituto de un pronóstico perfecto — sirve para análisis retrospectivo y **no**
es operable. El modo `antecedent` usa sólo el pasado y sí lo es. Si la conclusión
sólo se sostiene con el oráculo, hay que decirlo.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from . import data as data_mod
from . import gate as gate_mod
from .train import (_utf8_console, run_baselines, run_experiment_seeds,
                    _fmt, _fmt_sd)

TAU_MAX_GRID = (0.60, 0.70, 0.80, 0.85, 0.90, 0.95)


def _header(title: str, width: int = 104) -> None:
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)
    print(f"{'configuración':26s}{'RMSE m3/s':>11s}{'NSE':>7s}{'KGE':>7s}"
          f"{'G-RAL':>15s}{'V+ húm':>15s}{'V− seco':>15s}{'FA húm':>8s}")
    print("-" * width)


def _print_row(label: str, m: dict) -> None:
    g = lambda k: m.get(f"{k}_sd", 0.0)
    print(f"{label:26s}{_fmt(m['rmse'], 0):>11s}{_fmt(m['nse'], 2):>7s}{_fmt(m['kge'], 2):>7s}"
          f"{_fmt_sd(m['gral'], g('gral')):>15s}"
          f"{_fmt_sd(m['v_plus'], g('v_plus')):>15s}"
          f"{_fmt_sd(m['v_minus'], g('v_minus')):>15s}"
          f"{_fmt(m['fa_wet'], 2):>8s}")


#: τ_max de referencia para **medir**. Fijo a propósito: el barrido cambia con
#: qué fuerza se entrena, no con qué vara se mide.
REF_TAU_MAX = 0.85


def sweep_tau_max(*, seeds, model="mlp", losses=("gral", "expectile_raw"),
                  tau_mode="oracle", grid=TAU_MAX_GRID, split="test",
                  gate_rain="auto", **kw) -> dict:
    """Entrena la misma pérdida con distintos τ_max y mide con un τ de referencia fijo.

    Sin el τ de referencia el barrido no dice nada: el umbral de "día húmedo"
    (τ > 0,65) se movería junto con τ_max, así que cada fila mediría V+ sobre un
    conjunto de días distinto — y con τ_max = 0,60 directamente no habría ningún
    día húmedo que medir.
    """
    ref = data_mod.build_dataset(
        tau_mode=tau_mode, gate_rain_col=gate_rain,
        gate_params=gate_mod.GateParams(tau_max=REF_TAU_MAX))
    splits = data_mod.make_splits(ref.fecha)
    out = {"grid": list(grid), "tau_mode": tau_mode, "split": split,
           "ref_tau_max": REF_TAU_MAX, "runs": {}}
    for loss in losses:
        _header(f"τ_max sweep · loss={loss} · τ modo {tau_mode} · split {split.upper()}"
                f"  [medido siempre con τ_max={REF_TAU_MAX}]")
        out["runs"][loss] = {}
        for tau_max in grid:
            ds = data_mod.build_dataset(
                tau_mode=tau_mode, gate_rain_col=gate_rain,
                gate_params=gate_mod.GateParams(tau_max=tau_max))
            if len(ds) != len(ref):
                raise RuntimeError("el filtro de filas cambió con τ_max; no comparable")
            r = run_experiment_seeds(ds, splits, model=model, loss=loss, seeds=seeds,
                                     eval_tau=ref.tau, **kw)
            m = r[split]["mean"]
            out["runs"][loss][f"{tau_max:.2f}"] = m
            _print_row(f"τ_max={tau_max:.2f} ({tau_max / (1 - tau_max):.1f}x)", m)
        print("-" * 104)
    return out


def compare_tau_modes(*, seeds, model="mlp", losses=("mse", "gral"),
                      modes=("oracle", "antecedent"), split="test",
                      gate_rain="auto", **kw) -> dict:
    """Misma pérdida, modulador oráculo vs modulador causal."""
    out = {"modes": list(modes), "split": split, "runs": {}}
    _header(f"modulador oráculo vs causal · split {split.upper()}")
    ref_full = data_mod.build_dataset(tau_mode="oracle", gate_rain_col=gate_rain)
    for mode in modes:
        ds_full = data_mod.build_dataset(tau_mode=mode, gate_rain_col=gate_rain)
        # cada modo filtra distinto: alinear por fecha antes de comparar nada
        ds, ref = ds_full.align_to(ref_full)
        splits = data_mod.make_splits(ds.fecha)
        out["runs"][mode] = {"n_dias": len(ds)}
        # se mide siempre con el modulador oráculo para que V+ y V− hablen del mismo
        # conjunto de días; lo que cambia entre modos es con qué τ se entrenó
        base = run_baselines(data_mod.Dataset(
            fecha=ds.fecha, X=ds.X, Y=ds.Y, q_actual=ds.q_actual, tau=ref.tau,
            feature_names=ds.feature_names, horizons=ds.horizons,
            tau_mode="oracle(ref)"), splits)
        _print_row(f"[{mode}] persistencia", base["persistencia"][split]["mean"])
        out["runs"][mode]["persistencia"] = base["persistencia"][split]["mean"]
        assert ds.fecha.equals(ref.fecha), "alineación de fechas rota"
        for loss in losses:
            r = run_experiment_seeds(ds, splits, model=model, loss=loss, seeds=seeds,
                                     eval_tau=ref.tau, **kw)
            m = r[split]["mean"]
            out["runs"][mode][loss] = m
            _print_row(f"[{mode}] mlp · {loss}", m)
        reparto = {
            "humedo_pct": round(100 * float(np.mean(ds.tau > 0.65)), 1),
            "seco_pct": round(100 * float(np.mean(ds.tau < 0.35)), 1),
        }
        out["runs"][mode]["_tau_reparto"] = reparto
        print(f"   reparto τ en modo {mode}: húmedo {reparto['humedo_pct']} % · "
              f"seco {reparto['seco_pct']} %")
    print("-" * 104)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", choices=["mlp", "linear"], default="mlp")
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--split", choices=["val", "test"], default="val",
                   help="split sobre el que se reporta el barrido. El default es VAL: un "
                        "barrido de sensibilidad se corre muchas veces y leerlo en TEST "
                        "convierte el conjunto de prueba en un criterio de selección")
    p.add_argument("--tau-modes", action="store_true",
                   help="corre el contraste oráculo vs causal en vez del barrido")
    p.add_argument("--epochs", type=int, default=600)
    p.add_argument("--hidden", type=int, default=64)
    p.add_argument("--gate-rain", default="auto")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    _utf8_console()

    seeds = [args.seed + i for i in range(max(1, args.seeds))]
    kw = dict(epochs=args.epochs, hidden=args.hidden)
    gate_rain = args.gate_rain
    print(f"semillas: {seeds}")

    if args.tau_modes:
        results = compare_tau_modes(seeds=seeds, model=args.model, split=args.split,
                                    gate_rain=gate_rain, **kw)
        name = "tau_modes"
    else:
        results = sweep_tau_max(seeds=seeds, model=args.model, split=args.split,
                                gate_rain=gate_rain, **kw)
        name = "tau_max_sweep"

    out_path = (data_mod.REPO_ROOT / "rio_search" / "results" / f"{name}_{args.model}.json"
                if args.out is None else __import__("pathlib").Path(args.out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    print(f"\n  resultados → {out_path.relative_to(data_mod.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
