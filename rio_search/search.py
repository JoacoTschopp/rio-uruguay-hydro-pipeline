"""Búsqueda de hiperparámetros por optimización bayesiana, con Optuna.

    python -m rio_search.search --trials 60
    python -m rio_search.search --trials 100 --sampler gp --seeds-final 5

El objetivo que se minimiza es **G-RAL sobre VAL** — la función de ganancia
propuesta en `docs/funcion_ganancia_regimen.html` — y la pérdida de entrenamiento
es la misma métrica. Es la decisión que hace coherente todo el ciclo: se entrena
con G-RAL, se buscan los hiperparámetros que minimizan G-RAL, y se selecciona por
G-RAL. Sin eso, la búsqueda optimizaría una cosa distinta de la que el modelo
aprende.

**TEST no se toca durante la búsqueda.** El objetivo sale de VAL; TEST se evalúa
una sola vez, al final, sobre la mejor configuración. Reportar TEST en cada trial
convertiría la búsqueda en un ajuste sobre el conjunto de prueba, que es la forma
más fácil de producir un resultado que no se sostiene.

Sampler por defecto: **TPE** (Tree-structured Parzen Estimator), que es la
optimización bayesiana estándar de Optuna — modela p(x|y) en vez de p(y|x), y
funciona bien con pocas decenas de trials y espacios mixtos. `--sampler gp` usa
procesos gaussianos, más adecuado si el presupuesto de trials es chico y el
espacio es todo continuo.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import data as data_mod
from . import gate as gate_mod
from .train import (LOSS_CONFIGS, _utf8_console, run_baselines, run_experiment,
                    run_experiment_seeds)

__all__ = ["SPACE", "objective_factory", "run_search", "main"]

#: Espacio de búsqueda. Sólo hiperparámetros del modelo y del optimizador —
#: τ_max no entra acá a propósito: codifica un costo operativo declarado, no algo
#: que se ajuste a los datos (§04 del informe). Su sensibilidad se explora aparte,
#: con `rio_search.sensitivity`.
SPACE = {
    "hidden": ("int", 16, 256, True),        # log
    "lr": ("float", 1e-4, 1e-1, True),       # log
    "l2": ("float", 1e-7, 1e-1, True),       # log
    "epochs": ("int", 200, 1500, False),
    "patience": ("int", 20, 150, False),
}


def _suggest(trial) -> dict:
    """Traduce SPACE a llamadas de Optuna."""
    out = {}
    for nombre, spec in SPACE.items():
        tipo, lo, hi, log = spec
        if tipo == "int":
            out[nombre] = trial.suggest_int(nombre, lo, hi, log=log)
        else:
            out[nombre] = trial.suggest_float(nombre, lo, hi, log=log)
    return out


def objective_factory(ds, splits, *, model: str, loss: str, seed: int,
                      metric: str = "gral", seeds_per_trial: int = 1):
    """Objetivo de Optuna: la métrica en **VAL**, a minimizar.

    El podado usa la pérdida de validación que ya calcula el bucle de
    entrenamiento por época; el valor que se devuelve al final es la métrica
    completa sobre VAL, agregada sobre los 8 horizontes.

    `seeds_per_trial` promedia varias inicializaciones dentro de cada trial.
    Con 1 el objetivo es ruidoso: sobre este dataset el desvío entre semillas de
    `val/gral` es del orden de 0,01, comparable a la diferencia total que la
    búsqueda logra entre su mejor y su peor configuración razonable. Un objetivo
    así hace que el sampler persiga inicializaciones afortunadas en vez de
    hiperparámetros. Cuesta lineal en trials, así que es un cambio de precio, no
    de diseño. Sólo se poda con la primera semilla, para no cortar a mitad de un
    promedio.
    """
    import optuna

    def objective(trial) -> float:
        params = _suggest(trial)
        semillas = [seed + 1000 * i for i in range(max(1, seeds_per_trial))]
        valores, ultimo = [], None

        for i, s in enumerate(semillas):
            def on_epoch(epoch: int, val_loss: float) -> bool:
                trial.report(val_loss, epoch)
                return trial.should_prune()

            try:
                out = run_experiment(ds, splits, model=model, loss=loss, seed=s,
                                     on_epoch=on_epoch if i == 0 else None,
                                     **params)
            except optuna.TrialPruned:
                raise
            except (np.linalg.LinAlgError, FloatingPointError, ValueError) as exc:
                # Un lr disparatado puede divergir; eso es información para el
                # sampler, no un fallo de la búsqueda.
                trial.set_user_attr("error", str(exc))
                return float("inf")

            if out.get("pruned"):
                raise optuna.TrialPruned()

            v = out["val"]["mean"].get(metric)
            if v is None or not np.isfinite(v):
                return float("inf")
            valores.append(float(v))
            ultimo = out

        val = ultimo["val"]["mean"]
        for k in ("rmse", "nse", "kge", "v_plus", "v_minus"):
            trial.set_user_attr(f"val_{k}", val.get(k))
        trial.set_user_attr("best_epoch", ultimo.get("best_epoch"))
        trial.set_user_attr("n_semillas", len(valores))
        if len(valores) > 1:
            trial.set_user_attr("val_objetivo_sd", float(np.std(valores, ddof=1)))
        return float(np.mean(valores))

    return objective


def run_search(ds, splits, *, trials: int, model: str = "mlp", loss: str = "gral",
               metric: str = "gral", sampler: str = "tpe", seed: int = 20260828,
               seeds_final: int = 5, seeds_per_trial: int = 1, startup: int = 10,
               timeout: float | None = None, verbose: bool = False) -> dict:
    """Corre la búsqueda y re-evalúa la mejor configuración con varias semillas."""
    import optuna
    from optuna.pruners import MedianPruner
    from optuna.samplers import GPSampler, RandomSampler, TPESampler

    if not verbose:
        optuna.logging.set_verbosity(optuna.logging.WARNING)

    muestreadores = {
        "tpe": lambda: TPESampler(seed=seed, n_startup_trials=startup),
        "gp": lambda: GPSampler(seed=seed, n_startup_trials=startup),
        "random": lambda: RandomSampler(seed=seed),   # referencia, no es BO
    }
    if sampler not in muestreadores:
        raise KeyError(f"sampler desconocido: {sampler}. Opciones: {list(muestreadores)}")

    estudio = optuna.create_study(
        direction="minimize",
        sampler=muestreadores[sampler](),
        pruner=MedianPruner(n_startup_trials=startup, n_warmup_steps=50),
        study_name=f"{model}__{loss}__{metric}",
    )

    t0 = time.perf_counter()
    estudio.optimize(objective_factory(ds, splits, model=model, loss=loss,
                                       seed=seed, metric=metric,
                                       seeds_per_trial=seeds_per_trial),
                     n_trials=trials, timeout=timeout, show_progress_bar=False)
    segundos = time.perf_counter() - t0

    completados = [t for t in estudio.trials if t.state.name == "COMPLETE"]
    podados = [t for t in estudio.trials if t.state.name == "PRUNED"]
    mejor = estudio.best_trial

    # La mejor configuración se re-evalúa con varias semillas: un único trial
    # puede haber ganado por la inicialización y no por los hiperparámetros.
    final = run_experiment_seeds(ds, splits, model=model, loss=loss,
                                 seeds=[seed + i for i in range(seeds_final)],
                                 **mejor.params)

    return {
        "config": {"model": model, "loss": loss, "metric_objetivo": f"val/{metric}",
                   "sampler": sampler, "trials_pedidos": trials, "seed": seed,
                   "seeds_final": seeds_final, "seeds_per_trial": seeds_per_trial, "espacio": {k: list(v) for k, v in SPACE.items()}},
        "resumen": {"completados": len(completados), "podados": len(podados),
                    "tiempo_total_s": round(segundos, 1),
                    "mejor_valor_val": mejor.value},
        "mejor": {"numero": mejor.number, "params": mejor.params,
                  "val": dict(mejor.user_attrs)},
        "final_multisemilla": {"val": final["val"]["mean"], "test": final["test"]["mean"],
                               "seeds": final["seeds"]},
        "historia": [{"numero": t.number, "valor": t.value, "estado": t.state.name,
                      "params": t.params} for t in estudio.trials],
        "importancias": _importancias(estudio),
    }


def _importancias(estudio) -> dict:
    """Cuánto explica cada hiperparámetro la variación del objetivo.

    El evaluador por defecto de Optuna necesita scikit-learn, que este entorno no
    tiene a propósito (todo el arnés corre con numpy/pandas). `PedAnova` es puro
    Python y da el mismo tipo de lectura, así que se intenta primero.
    """
    import optuna

    for evaluador in (optuna.importance.PedAnovaImportanceEvaluator(), None):
        try:
            imp = optuna.importance.get_param_importances(estudio, evaluator=evaluador)
            return {k: round(float(v), 4) for k, v in imp.items()}
        except Exception:
            continue
    return {"_no_disponible": "hacen falta más trials completados"}


def _fmt(v, nd=4):
    return "—" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def print_report(res: dict) -> None:
    cfg, resumen, mejor = res["config"], res["resumen"], res["mejor"]
    print("\n" + "=" * 78)
    print(f"  BÚSQUEDA BAYESIANA · {cfg['model']} · loss={cfg['loss']} · "
          f"objetivo {cfg['metric_objetivo']} · sampler {cfg['sampler']}")
    print("=" * 78)
    print(f"  trials completados: {resumen['completados']}   podados: {resumen['podados']}"
          f"   tiempo: {resumen['tiempo_total_s']:.0f} s")
    print(f"\n  mejor trial: #{mejor['numero']}   {cfg['metric_objetivo']} = "
          f"{_fmt(resumen['mejor_valor_val'])}")
    for k, v in mejor["params"].items():
        print(f"    {k:12s} {v}")

    if res["importancias"] and "_no_disponible" not in res["importancias"]:
        print("\n  importancia de cada hiperparámetro:")
        for k, v in res["importancias"].items():
            barra = "#" * int(round(v * 40))
            print(f"    {k:12s} {v:6.3f}  {barra}")

    fin = res["final_multisemilla"]
    print(f"\n  mejor configuración re-evaluada con {len(fin['seeds'])} semillas:")
    print(f"    {'':10s}{'G-RAL':>10s}{'RMSE':>10s}{'NSE':>8s}{'KGE':>8s}"
          f"{'V+':>8s}{'V-':>8s}")
    for split in ("val", "test"):
        m = fin[split]
        print(f"    {split.upper():10s}{_fmt(m['gral'], 3):>10s}{_fmt(m['rmse'], 0):>10s}"
              f"{_fmt(m['nse'], 2):>8s}{_fmt(m['kge'], 2):>8s}"
              f"{_fmt(m['v_plus'], 3):>8s}{_fmt(m['v_minus'], 3):>8s}")
    print("\n  TEST se evaluó una sola vez, sobre esta configuración. La búsqueda")
    print("  entera se guió por VAL.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trials", type=int, default=60)
    p.add_argument("--model", choices=["mlp", "linear"], default="mlp")
    p.add_argument("--loss", choices=list(LOSS_CONFIGS), default="gral",
                   help="pérdida de entrenamiento (default: la propuesta)")
    p.add_argument("--metric", default="gral",
                   help="métrica de VAL a minimizar (default: gral)")
    p.add_argument("--sampler", choices=["tpe", "gp", "random"], default="tpe")
    p.add_argument("--startup", type=int, default=10,
                   help="trials iniciales al azar antes de que el modelo bayesiano tome el control")
    p.add_argument("--seeds-final", type=int, default=5)
    p.add_argument("--seeds-per-trial", type=int, default=1,
                   help="semillas promediadas dentro de cada trial. Con 1 el "
                        "objetivo queda dominado por el ruido de inicialización")
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--timeout", type=float, default=None, help="segundos")
    p.add_argument("--tau-mode", choices=["oracle", "antecedent", "forecast"], default="oracle")
    p.add_argument("--tau-max", type=float, default=gate_mod.DEFAULT_PARAMS.tau_max)
    p.add_argument("--gate-rain", default="auto")
    p.add_argument("--groups", default=None)
    p.add_argument("--snapshot", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    _utf8_console()

    params = gate_mod.GateParams(tau_max=args.tau_max)
    groups = (tuple(g.strip() for g in args.groups.split(","))
              if args.groups else data_mod.DEFAULT_GROUPS)
    print("cargando snapshot Gold ...", flush=True)
    ds = data_mod.build_dataset(tau_mode=args.tau_mode, gate_params=params,
                                snapshot_path=args.snapshot, groups=groups,
                                gate_rain_col=args.gate_rain)
    splits = data_mod.make_splits(ds.fecha)
    print(f"  {len(ds)} días · {ds.X.shape[1]} features · τ modo {ds.tau_mode} "
          f"(τ_max = {params.tau_max})")
    for nombre, info in splits.describe(ds.fecha).items():
        print(f"  {nombre:5s} n={info['n']:5d}  {info['desde']} → {info['hasta']}")
    print(f"\ncorriendo {args.trials} trials ...", flush=True)

    res = run_search(ds, splits, trials=args.trials, model=args.model, loss=args.loss,
                     metric=args.metric, sampler=args.sampler, seed=args.seed,
                     seeds_final=args.seeds_final, seeds_per_trial=args.seeds_per_trial,
                     startup=args.startup,
                     timeout=args.timeout, verbose=args.verbose)
    res["baselines"] = {n: r["test"]["mean"] for n, r in run_baselines(ds, splits).items()}
    manifest = data_mod.read_manifest(
        Path(args.snapshot) if args.snapshot else data_mod.DEFAULT_SNAPSHOT)
    res["snapshot"] = {"delta_version": (manifest or {}).get("delta_version"),
                       "exported_at": (manifest or {}).get("exported_at"),
                       "gate_rain": args.gate_rain, "groups": list(groups)}

    print_report(res)

    out = Path(args.out) if args.out else (
        data_mod.REPO_ROOT / "rio_search" / "results" /
        f"search_{args.model}_{args.loss}_{args.sampler}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    try:
        mostrar = out.resolve().relative_to(data_mod.REPO_ROOT)
    except ValueError:                       # --out apuntando fuera del repo
        mostrar = out.resolve()
    print(f"\n  resultados → {mostrar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
