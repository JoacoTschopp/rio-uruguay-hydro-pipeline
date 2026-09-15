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


#: Grilla de B8.04. κ = 2,2 / 0,35-0,65 / 30 d es la configuración declarada.
GATE_GRID_KAPPAS = (1.5, 2.2, 3.0)
GATE_GRID_PESOS = ((0.5, 0.5), (0.35, 0.65), (0.2, 0.8))
GATE_GRID_ANT_DAYS = (15, 30, 60)


def _gate_grid(kappas=GATE_GRID_KAPPAS, pesos=GATE_GRID_PESOS,
               ant_days=GATE_GRID_ANT_DAYS) -> list[tuple[str, gate_mod.GateParams]]:
    """El producto completo de la grilla, con una etiqueta estable por punto."""
    out = []
    for kappa in kappas:
        for w_ant, w_fc in pesos:
            for ad in ant_days:
                etiqueta = f"k{kappa:g}_w{w_ant:g}/{w_fc:g}_ant{ad}"
                out.append((etiqueta, gate_mod.GateParams(
                    kappa=kappa, w_ant=w_ant, w_fc=w_fc, ant_days=int(ad))))
    return out


def sweep_gate_params(*, seeds, model="mlp", loss="gral", split="val",
                      gate_rain="auto", **kw) -> dict:
    """B8.04: la misma pérdida bajo cada punto de la grilla del modulador.

    Igual que el barrido de τ_max, **se mide siempre con el τ de la configuración
    declarada** (GateParams por defecto): lo que cambia entre filas es con qué τ
    se entrena. Cada punto reporta además su reparto húmedo/neutro/seco — sin eso
    las filas no son comparables, porque κ y los pesos mueven el umbral de "día
    húmedo" (con κ = 1,5 casi no hay días fuera del centro).

    `ant_days` cambia cuántas filas iniciales quedan sin τ (la suma móvil
    estricta necesita ventana completa), así que cada punto se alinea por fecha
    contra la referencia antes de entrenar o medir nada.
    """
    ref_full = data_mod.build_dataset(tau_mode="oracle", gate_rain_col=gate_rain)
    out = {"grid": {"kappa": list(GATE_GRID_KAPPAS),
                    "pesos_w_ant_w_fc": [list(p) for p in GATE_GRID_PESOS],
                    "ant_days": list(GATE_GRID_ANT_DAYS)},
           "split": split, "ref_params": gate_mod.DEFAULT_PARAMS.as_dict(),
           "loss": loss, "runs": {}}
    _header(f"barrido del modulador · loss={loss} · split {split.upper()}"
            f"  [medido siempre con la configuración declarada]")
    for etiqueta, params in _gate_grid():
        ds_full = data_mod.build_dataset(tau_mode="oracle", gate_rain_col=gate_rain,
                                         gate_params=params)
        ds, ref = ds_full.align_to(ref_full)
        splits = data_mod.make_splits(ds.fecha)
        r = run_experiment_seeds(ds, splits, model=model, loss=loss, seeds=seeds,
                                 eval_tau=ref.tau, **kw)
        m = r[split]["mean"]
        reparto = {
            "humedo_pct": round(100 * float(np.mean(ds.tau > 0.65)), 1),
            "neutro_pct": round(100 * float(np.mean((ds.tau >= 0.35) & (ds.tau <= 0.65))), 1),
            "seco_pct": round(100 * float(np.mean(ds.tau < 0.35)), 1),
        }
        out["runs"][etiqueta] = {**m, "_tau_reparto": reparto, "n_dias": len(ds)}
        _print_row(etiqueta, m)
        print(f"    reparto τ: húmedo {reparto['humedo_pct']} % · neutro "
              f"{reparto['neutro_pct']} % · seco {reparto['seco_pct']} %")
    print("-" * 104)
    return out


def compare_tau_modes(*, seeds, model="mlp", losses=("mse", "gral"),
                      modes=("oracle", "antecedent"), split="test",
                      gate_rain="auto", **kw) -> dict:
    """Misma pérdida, con el modulador en cada modo pedido.

    Los modos filtran filas distintas (la ventana antecedente come el arranque de
    la serie; el pronóstico ECMWF empieza en 2006-11 y tiene el hueco de 2017),
    así que **todos los modos corren sobre la intersección común de fechas**: si
    no, un modo con menos historia parecería distinto sólo por el período.
    """
    out = {"modes": list(modes), "split": split, "runs": {}}
    _header(f"modulador por modo ({', '.join(modes)}) · split {split.upper()}")
    ref_full = data_mod.build_dataset(tau_mode="oracle", gate_rain_col=gate_rain)
    ds_fulls = {m: data_mod.build_dataset(tau_mode=m, gate_rain_col=gate_rain)
                for m in modes}
    fechas = ref_full.fecha
    for d in ds_fulls.values():
        fechas = fechas.intersection(d.fecha)
    ref = ref_full.subset(ref_full.fecha.isin(fechas))
    out["n_dias_comun"] = len(ref)
    out["rango_comun"] = [str(fechas.min().date()), str(fechas.max().date())]
    for mode in modes:
        ds_full = ds_fulls[mode]
        ds = ds_full.subset(ds_full.fecha.isin(fechas))
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
    p.add_argument("--gate-grid", action="store_true",
                   help="B8.04: barrido de κ, pesos y ventanas del modulador")
    p.add_argument("--modes", default="oracle,antecedent",
                   help="modos del modulador a contrastar con --tau-modes, separados "
                        "por coma. B8.05 agrega `forecast` (pronóstico ECMWF real)")
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

    if args.gate_grid:
        results = sweep_gate_params(seeds=seeds, model=args.model, split=args.split,
                                    gate_rain=gate_rain, **kw)
        name = "gate_params"
    elif args.tau_modes:
        modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
        results = compare_tau_modes(seeds=seeds, model=args.model, split=args.split,
                                    gate_rain=gate_rain, modes=modes, **kw)
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
