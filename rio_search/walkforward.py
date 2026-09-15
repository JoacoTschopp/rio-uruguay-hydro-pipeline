"""Validación temporal caminando hacia adelante, con búsqueda bayesiana por fold.

    python -m rio_search.walkforward --trials 30 --seeds-per-trial 2
    python -m rio_search.walkforward --ventanas expandible --trials 60

Cada fold prueba **un año calendario**, usa el año anterior como VAL y entrena
con lo anterior a eso. La búsqueda de hiperparámetros corre **dentro de cada
fold**, sobre su propio VAL: es la forma anidada, la única que no usa información
del futuro del fold para elegir su configuración.

Se corren dos formas de ventana de entrenamiento y se comparan:

- ``expandible`` — TRAIN desde el inicio de la serie, creciendo fold a fold.
- ``deslizante`` — TRAIN de largo fijo (`--train-years`), que va olvidando.

La comparación entre las dos es el punto del ejercicio. Si gana expandible, la
historia vieja aporta y conviene usarla toda. Si gana deslizante, el río cambió
lo suficiente como para que el pasado lejano confunda más de lo que ayuda — y eso
tiene consecuencias directas sobre cómo se entrena el modelo definitivo.

Tres cosas que este diseño mezcla a propósito, y hay que leerlas juntas:

1. **El año de TEST cambia entre folds.** Un año hidrológicamente raro va a dar
   peores métricas sin que el modelo tenga nada que ver. Por eso se reporta cada
   fold por separado además del promedio: el promedio solo esconde eso.
2. **Los hiperparámetros cambian entre folds**, porque cada uno hace su propia
   búsqueda. Es lo correcto metodológicamente, pero significa que una diferencia
   entre folds mezcla el efecto del año con el de la configuración. El reporte de
   deriva de hiperparámetros sirve para ver cuánto se movieron.
3. **El último fold suele ser parcial** (la serie corta a mitad de año). Queda
   marcado y conviene no promediarlo con los demás sin pensarlo.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import data as data_mod
from . import gate as gate_mod
from .search import run_search
from .train import _utf8_console, run_baselines, run_experiment_seeds

__all__ = ["run_fold", "run_walkforward", "main"]

VENTANAS = ("expandible", "deslizante")
METRICAS = ("gral", "rmse", "nse", "kge", "v_plus", "v_minus")


def run_fold(ds, fold, *, trials: int, model: str, loss: str, metric: str,
             sampler: str, seed: int, seeds_final: int, seeds_per_trial: int,
             startup: int, buscar: bool = True, params_fijos: dict | None = None) -> dict:
    """Un fold: busca hiperparámetros en su VAL y evalúa una vez en su TEST."""
    t0 = time.perf_counter()
    if buscar:
        res = run_search(ds, fold.splits, trials=trials, model=model, loss=loss,
                         metric=metric, sampler=sampler, seed=seed,
                         seeds_final=seeds_final, seeds_per_trial=seeds_per_trial,
                         startup=startup)
        params = res["mejor"]["params"]
        final = res["final_multisemilla"]
        extra = {"trials_completados": res["resumen"]["completados"],
                 "trials_podados": res["resumen"]["podados"],
                 "importancias": res["importancias"]}
    else:
        params = dict(params_fijos or {})
        out = run_experiment_seeds(ds, fold.splits, model=model, loss=loss,
                                   seeds=[seed + i for i in range(seeds_final)],
                                   **params)
        final = {"val": out["val"]["mean"], "test": out["test"]["mean"],
                 "seeds": out["seeds"]}
        extra = {}

    return {
        "fold": fold.nombre, "ventana": fold.ventana, "parcial": fold.parcial,
        "splits": fold.describe(ds.fecha),
        "params": params,
        "val": {k: final["val"].get(k) for k in METRICAS},
        "test": {k: final["test"].get(k) for k in METRICAS},
        "test_sd": {k: final["test"].get(f"{k}_sd") for k in METRICAS},
        "tiempo_s": round(time.perf_counter() - t0, 1),
        **extra,
    }


def run_walkforward(ds, *, ventanas=VENTANAS, n_folds: int = 5, train_years: int = 10,
                    trials: int = 30, model: str = "mlp", loss: str = "gral",
                    metric: str = "gral", sampler: str = "tpe", seed: int = 20260828,
                    seeds_final: int = 3, seeds_per_trial: int = 2,
                    startup: int = 8) -> dict:
    out = {"config": {"ventanas": list(ventanas), "n_folds": n_folds,
                      "train_years": train_years, "trials_por_fold": trials,
                      "model": model, "loss": loss, "metric_objetivo": f"val/{metric}",
                      "sampler": sampler, "seeds_per_trial": seeds_per_trial,
                      "seeds_final": seeds_final, "seed": seed},
           "folds": {}, "baselines": {}}

    for ventana in ventanas:
        folds = data_mod.make_walkforward_folds(
            ds.fecha, n_folds=n_folds, ventana=ventana, train_years=train_years)
        out["folds"][ventana] = []
        for fold in folds:
            print(f"  [{ventana:11s}] fold {fold.nombre}"
                  f"{' (parcial)' if fold.parcial else ''} — BO de {trials} trials ...",
                  flush=True)
            r = run_fold(ds, fold, trials=trials, model=model, loss=loss, metric=metric,
                         sampler=sampler, seed=seed, seeds_final=seeds_final,
                         seeds_per_trial=seeds_per_trial, startup=startup)
            print(f"      TEST {metric} = {r['test'][metric]:.4f}   "
                  f"RMSE = {r['test']['rmse']:.0f}   ({r['tiempo_s']:.0f} s)", flush=True)
            out["folds"][ventana].append(r)

            # persistencia sobre el mismo TEST, como piso de referencia por año
            if fold.nombre not in out["baselines"]:
                base = run_baselines(ds, fold.splits)["persistencia"]["test"]["mean"]
                out["baselines"][fold.nombre] = {k: base.get(k) for k in METRICAS}

    out["resumen"] = _resumir(out)
    return out


def _resumir(res: dict) -> dict:
    """Promedios por ventana, excluyendo el fold parcial, y deriva de HP."""
    resumen = {}
    for ventana, folds in res["folds"].items():
        completos = [f for f in folds if not f["parcial"]]
        resumen[ventana] = {
            "n_folds_completos": len(completos),
            "test": {k: float(np.mean([f["test"][k] for f in completos
                                       if f["test"][k] is not None
                                       and np.isfinite(f["test"][k])]))
                     for k in METRICAS},
            "test_sd_entre_folds": {
                k: float(np.std([f["test"][k] for f in completos
                                 if f["test"][k] is not None
                                 and np.isfinite(f["test"][k])], ddof=1))
                if len(completos) > 1 else 0.0
                for k in METRICAS},
            "deriva_hp": {
                p: [f["params"].get(p) for f in folds]
                for p in (folds[0]["params"] if folds else {})
            },
        }
    return resumen


def _fmt(v, nd=3):
    return "—" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def print_report(res: dict) -> None:
    cfg = res["config"]
    ancho = 92
    print("\n" + "=" * ancho)
    print(f"  WALK-FORWARD · {cfg['n_folds']} folds anuales · BO anidada "
          f"({cfg['trials_por_fold']} trials/fold, {cfg['seeds_per_trial']} semillas/trial)")
    print(f"  modelo {cfg['model']} · loss {cfg['loss']} · objetivo {cfg['metric_objetivo']}")
    print("=" * ancho)

    for ventana, folds in res["folds"].items():
        print(f"\n  ── {ventana.upper()} ──")
        print(f"  {'año':6s}{'n train':>9s}{'G-RAL':>9s}{'RMSE':>8s}{'NSE':>7s}"
              f"{'KGE':>7s}{'V+':>7s}{'V-':>7s}{'persist RMSE':>14s}")
        for f in folds:
            b = res["baselines"].get(f["fold"], {})
            marca = " *" if f["parcial"] else "  "
            print(f"  {f['fold']:6s}{f['splits']['train']['n']:>9d}"
                  f"{_fmt(f['test']['gral']):>9s}{_fmt(f['test']['rmse'], 0):>8s}"
                  f"{_fmt(f['test']['nse'], 2):>7s}{_fmt(f['test']['kge'], 2):>7s}"
                  f"{_fmt(f['test']['v_plus']):>7s}{_fmt(f['test']['v_minus']):>7s}"
                  f"{_fmt(b.get('rmse'), 0):>12s}{marca}")
        r = res["resumen"][ventana]
        print(f"  {'media':6s}{'':>9s}{_fmt(r['test']['gral']):>9s}"
              f"{_fmt(r['test']['rmse'], 0):>8s}{_fmt(r['test']['nse'], 2):>7s}"
              f"{_fmt(r['test']['kge'], 2):>7s}{_fmt(r['test']['v_plus']):>7s}"
              f"{_fmt(r['test']['v_minus']):>7s}"
              f"   (sin el fold parcial, n={r['n_folds_completos']})")
        print(f"  {'sd':6s}{'':>9s}{_fmt(r['test_sd_entre_folds']['gral']):>9s}"
              f"{_fmt(r['test_sd_entre_folds']['rmse'], 0):>8s}"
              f"   ← dispersión ENTRE AÑOS, no entre semillas")

    if len(res["folds"]) > 1:
        a, b = list(res["folds"])
        ra, rb = res["resumen"][a]["test"], res["resumen"][b]["test"]
        print(f"\n  ── {a} vs {b} ──")
        for k in ("gral", "rmse", "kge"):
            d = ra[k] - rb[k]
            mejor = a if (d < 0 if k != "kge" else d > 0) else b
            print(f"  {k:6s}  {a} {_fmt(ra[k], 3 if k != 'rmse' else 0)}"
                  f"   {b} {_fmt(rb[k], 3 if k != 'rmse' else 0)}"
                  f"   → mejor: {mejor}")

    print(f"\n  ── deriva de hiperparámetros entre folds ──")
    for ventana, r in res["resumen"].items():
        print(f"  [{ventana}]")
        for p, valores in r["deriva_hp"].items():
            vs = [v for v in valores if v is not None]
            if not vs:
                continue
            fmt = (lambda v: f"{v:.4g}")
            print(f"    {p:10s} {' → '.join(fmt(v) for v in vs)}")

    print("\n  * fold parcial (el año no está completo en la serie); excluido de las medias.")
    print("  Cada fold eligió sus propios hiperparámetros: una diferencia entre años")
    print("  mezcla el efecto del año con el de la configuración.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ventanas", default="expandible,deslizante",
                   help="expandible, deslizante, o las dos separadas por coma")
    p.add_argument("--n-folds", type=int, default=5)
    p.add_argument("--train-years", type=int, default=10,
                   help="largo de la ventana deslizante, en años")
    p.add_argument("--trials", type=int, default=30, help="trials de BO por fold")
    p.add_argument("--seeds-per-trial", type=int, default=2)
    p.add_argument("--seeds-final", type=int, default=3)
    p.add_argument("--startup", type=int, default=8)
    p.add_argument("--model", choices=["mlp", "linear"], default="mlp")
    p.add_argument("--loss", default="gral")
    p.add_argument("--metric", default="gral")
    p.add_argument("--sampler", choices=["tpe", "gp", "random"], default="tpe")
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--tau-mode", choices=["oracle", "antecedent", "forecast"], default="oracle")
    p.add_argument("--tau-max", type=float, default=gate_mod.DEFAULT_PARAMS.tau_max)
    p.add_argument("--gate-rain", default="auto")
    p.add_argument("--groups", default=None)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    _utf8_console()

    ventanas = tuple(v.strip() for v in args.ventanas.split(","))
    params = gate_mod.GateParams(tau_max=args.tau_max)
    groups = (tuple(g.strip() for g in args.groups.split(","))
              if args.groups else data_mod.DEFAULT_GROUPS)

    print("cargando snapshot Gold ...", flush=True)
    ds = data_mod.build_dataset(tau_mode=args.tau_mode, gate_params=params,
                                snapshot_path=args.snapshot, groups=groups,
                                gate_rain_col=args.gate_rain)
    print(f"  {len(ds)} días · {ds.X.shape[1]} features · τ modo {ds.tau_mode}")
    total = len(ventanas) * args.n_folds
    print(f"  {total} folds ({len(ventanas)} ventanas × {args.n_folds} años), "
          f"{args.trials} trials cada uno\n", flush=True)

    t0 = time.perf_counter()
    res = run_walkforward(ds, ventanas=ventanas, n_folds=args.n_folds,
                          train_years=args.train_years, trials=args.trials,
                          model=args.model, loss=args.loss, metric=args.metric,
                          sampler=args.sampler, seed=args.seed,
                          seeds_final=args.seeds_final,
                          seeds_per_trial=args.seeds_per_trial, startup=args.startup)
    res["tiempo_total_s"] = round(time.perf_counter() - t0, 1)

    manifest = data_mod.read_manifest(
        Path(args.snapshot) if args.snapshot else data_mod.DEFAULT_SNAPSHOT)
    res["snapshot"] = {"delta_version": (manifest or {}).get("delta_version"),
                       "exported_at": (manifest or {}).get("exported_at"),
                       "gate_rain": args.gate_rain, "groups": list(groups)}

    print_report(res)
    print(f"\n  tiempo total: {res['tiempo_total_s'] / 60:.1f} min")

    out = Path(args.out) if args.out else (
        data_mod.REPO_ROOT / "rio_search" / "results" /
        f"walkforward_{args.model}_{args.loss}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    try:
        mostrar = out.resolve().relative_to(data_mod.REPO_ROOT)
    except ValueError:
        mostrar = out.resolve()
    print(f"  resultados → {mostrar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
