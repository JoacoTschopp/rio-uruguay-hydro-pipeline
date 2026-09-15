"""B11.03: significancia entre finalistas — test de Diebold-Mariano sobre VAL.

    python -m rio_search.dm --seeds 5 --hac-h 14

El umbral de ruido del corredor cubre el ruido de **inicialización** (desvío
entre semillas). Este módulo cubre el que queda: el ruido de la **muestra
temporal**. Dos configuraciones pueden separarse limpiamente entre semillas y
aun así no diferir de verdad, porque VAL es un solo año hidrológico.

Cada finalista se entrena con los hiperparámetros del ancla, se promedian las
predicciones entre semillas (una serie por configuración, que es lo que el test
compara), y se corre `metrics.dm_test` sobre las pérdidas diarias en VAL con dos
pérdidas: ψ_τ en log (el integrando de G-RAL, la que importa acá) y el error
cuadrático en log (la simétrica, de control). TEST no se toca: la versión sobre
TEST corre una sola vez en el cierre (B11), sobre el campeón ya elegido.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import data as data_mod
from . import metrics as metrics_mod
from .models import LOSSES, MLPCore, PersistenceBaseline
from .train import LOSS_CONFIGS, Preprocessor, _utf8_console

#: Los finalistas por defecto: el ancla contra las otras pérdidas de la grilla
#: 2×2 del informe, más la persistencia como piso.
CONTRA_DEFAULT = "mse,mse_log,expectile_raw,persistencia"


def _pred_val_promedio(ds, splits, *, loss: str, seeds, hidden, lr, l2,
                       epochs, patience) -> np.ndarray:
    """Predicciones de VAL promediadas entre semillas, en m³/s."""
    loss_name, transform = LOSS_CONFIGS[loss]
    loss_fn = LOSSES[loss_name]
    tr, va = splits.train, splits.val
    pre = Preprocessor(target_transform=transform).fit(ds.X[tr], ds.Y[tr])
    Xtr, Xva = pre.transform_x(ds.X[tr]), pre.transform_x(ds.X[va])
    Ztr, Zva = pre.transform_y(ds.Y[tr]), pre.transform_y(ds.Y[va])
    acum = None
    for seed in seeds:
        core = MLPCore(hidden=hidden, loss=loss_fn, epochs=epochs, lr=lr, l2=l2,
                       patience=patience, seed=seed)
        core.fit(Xtr, Ztr, tau=ds.tau[tr] if loss_fn.uses_tau else None,
                 X_val=Xva, Y_val=Zva,
                 tau_val=ds.tau[va] if loss_fn.uses_tau else None)
        pred = np.maximum(pre.inverse_y(core.predict(Xva)), 0.0)
        acum = pred if acum is None else acum + pred
    return acum / len(seeds)


def perdidas_diarias(y_true, y_pred, tau, *, q_floor: float = metrics_mod.Q_FLOOR) -> dict:
    """Las dos pérdidas por día (media sobre los horizontes disponibles)."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    eps = np.log(np.maximum(yt, q_floor)) - np.log(np.maximum(yp, q_floor))
    tau_col = np.asarray(tau, dtype=float).reshape(-1, 1)
    with np.errstate(invalid="ignore"):
        psi = metrics_mod.expectile_se(np.where(np.isfinite(eps), eps, 0.0), tau_col)
        psi = np.where(np.isfinite(eps), psi, np.nan)
        return {"psi_tau": np.nanmean(psi, axis=1),
                "sq_log": np.nanmean(eps ** 2, axis=1)}


def comparar_finalistas(*, seeds, contra, hac_h, gate_rain, hidden, lr, l2,
                        epochs, patience) -> dict:
    ds = data_mod.build_dataset(tau_mode="oracle", gate_rain_col=gate_rain)
    splits = data_mod.make_splits(ds.fecha)
    va = splits.val
    n_h = len(ds.horizons)

    def _series(nombre: str) -> dict:
        if nombre == "persistencia":
            pred = PersistenceBaseline().predict(ds.q_actual, n_h)[va]
        else:
            pred = _pred_val_promedio(ds, splits, loss=nombre, seeds=seeds,
                                      hidden=hidden, lr=lr, l2=l2,
                                      epochs=epochs, patience=patience)
        return perdidas_diarias(ds.Y[va], pred, ds.tau[va])

    print(f"entrenando el ancla (gral, {len(seeds)} semillas) ...", flush=True)
    ancla = _series("gral")
    out = {"split": "val", "n_dias": int(va.sum()), "hac_h": hac_h,
           "seeds": list(seeds), "ancla": "gral",
           "hp": {"hidden": hidden, "lr": lr, "l2": l2, "epochs": epochs,
                  "patience": patience, "gate_rain": gate_rain},
           "pares": {}}
    print(f"\n{'par (ancla vs …)':26s}{'pérdida':>9s}{'dm':>9s}{'p':>9s}{'n':>6s}"
          f"   dm < 0: el ancla pierde menos")
    print("-" * 78)
    for nombre in contra:
        print(f"entrenando {nombre} ...", flush=True)
        rival = _series(nombre)
        par = {}
        for clave in ("psi_tau", "sq_log"):
            par[clave] = metrics_mod.dm_test(ancla[clave], rival[clave], h=hac_h)
            r = par[clave]
            print(f"{'gral vs ' + nombre:26s}{clave:>9s}{r['dm']:>9.3f}{r['p']:>9.4f}"
                  f"{r['n']:>6d}")
        out["pares"][f"gral vs {nombre}"] = par
    print("-" * 78)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--seed", type=int, default=20260828)
    p.add_argument("--hac-h", type=int, default=14,
                   help="rezago HAC: el horizonte más largo del pronóstico (14)")
    p.add_argument("--contra", default=CONTRA_DEFAULT,
                   help="finalistas contra los que se testea el ancla, por coma")
    p.add_argument("--gate-rain", default="lluvia_media_est_mm")
    p.add_argument("--hidden", type=int, default=38)
    p.add_argument("--lr", type=float, default=0.0492)
    p.add_argument("--l2", type=float, default=0.000217)
    p.add_argument("--epochs", type=int, default=378)
    p.add_argument("--patience", type=int, default=60)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    _utf8_console()

    seeds = [args.seed + i for i in range(max(1, args.seeds))]
    contra = [c.strip() for c in args.contra.split(",") if c.strip()]
    desconocidas = [c for c in contra if c != "persistencia" and c not in LOSS_CONFIGS]
    if desconocidas:
        p.error(f"finalistas desconocidos: {desconocidas}")

    results = comparar_finalistas(seeds=seeds, contra=contra, hac_h=args.hac_h,
                                  gate_rain=args.gate_rain, hidden=args.hidden,
                                  lr=args.lr, l2=args.l2, epochs=args.epochs,
                                  patience=args.patience)
    manifest = data_mod.read_manifest(data_mod.DEFAULT_SNAPSHOT) or {}
    results["snapshot"] = {"delta_version": manifest.get("delta_version"),
                           "sha256": (manifest.get("file_sha256") or "")[:12] or None}

    out_path = (Path(args.out) if args.out
                else data_mod.REPO_ROOT / "rio_search" / "results" / "dm_finalistas.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    print(f"\n  resultados → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
