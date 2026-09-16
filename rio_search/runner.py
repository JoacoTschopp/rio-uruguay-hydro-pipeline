"""Corredor del catálogo de búsqueda: ejecuta celdas y lleva el ledger.

    python -m rio_search.runner --estado          # dónde está la búsqueda (fase F0)
    python -m rio_search.runner --bloque B1       # corre un bloque
    python -m rio_search.runner --celda B1.03     # corre una celda
    python -m rio_search.runner --todo            # corre todo lo implementado, en orden
    python -m rio_search.runner --deriva          # qué cambió al cambiar el dataset

Implementa el procedimiento de `docs/protocolo_busqueda_modelos.md` sobre el catálogo
`rio_search/experiments/matrix.yaml`. Lo que antes era una instrucción para que un agente
la siguiera a mano pasa a ser un comando: **cuando cambia el dataset, volver a correr todo
es `--todo`**, y el ledger queda igual de completo que si lo hubiera escrito una persona.

Tres reglas del protocolo dejan de depender de la disciplina de quien ejecuta:

* **TEST no se calcula fuera de B11.** El corredor agrega `--no-test` a toda celda de
  entrenamiento que no esté en B11, así que el bloque directamente no existe en el JSON.
  Para las celdas de `search` y `walkforward`, que no tienen ese flag, el corredor no lee
  TEST y el ledger guarda `"no_leido"`.
* **El veredicto sale del umbral de ruido**, no de mirar cuál número es más chico:
  `2·√(ee_celda² + ee_ancla²)` con `ee = sd/√n` entre semillas.
* **Nada `falta` se implementa solo.** Una celda que no está implementada deja fila
  `bloqueado` con su motivo y el corredor sigue. Escribir el código es una decisión del
  usuario, no del corredor.

El ledger es append-only y es la única fuente de estado: no hay nada guardado en ningún
otro lado que haga falta para saber en qué celda seguir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import data as data_mod

__all__ = ["MATRIZ", "LEDGER", "dataset_id", "cargar_matriz", "leer_ledger",
           "celdas_en_orden", "veredicto_de", "umbral_de_ruido", "ejecutar_celda",
           "huella_esquema", "huella_valores", "comparar_datasets", "resolver_campana", "main"]

REPO = data_mod.REPO_ROOT
MATRIZ = REPO / "rio_search" / "experiments" / "matrix.yaml"
RESULTS = REPO / "rio_search" / "results"
LEDGER = RESULTS / "ledger.jsonl"

#: Celdas por encima de este tiempo estimado no corren salvo `--incluir-largas`.
#: El protocolo (§9) pide confirmar antes de arrancar una celda cara, no después.
LARGA_S = 600

#: Métricas que se copian al ledger además del objetivo.
METRICAS = ("rmse", "nse", "kge", "v_plus", "v_minus", "fa_wet")


# --------------------------------------------------------------------------
# Identidad del dato
# --------------------------------------------------------------------------

def dataset_id(snapshot: Path | None = None) -> tuple[str, dict]:
    """`d<delta>-<sha8>` del snapshot vigente, más el manifest que lo describe."""
    snapshot = snapshot or data_mod.DEFAULT_SNAPSHOT
    manifest = data_mod.read_manifest(snapshot)
    if not manifest:
        raise FileNotFoundError(
            f"no hay manifest para {snapshot.name}: no se puede fechar ningún resultado. "
            "Correr export_gold_dataset.py --refresh (celda B0.01)."
        )
    return f"d{manifest['delta_version']}-{manifest['file_sha256'][:8]}", manifest


def huella_esquema(manifest: dict) -> str:
    """Huella de las **columnas**, insensible a que se agreguen filas.

    Es la mitad de la identidad que decide si hay que descartar lo corrido. Gold
    publica una versión Delta nueva **todos los días** —la cadena diaria agrega un
    día de datos— así que el `DATASET_ID`, que incluye el sha256 del parquet,
    cambia a diario aunque no haya cambiado nada que invalide una conclusión.
    Comparando sólo el conjunto de columnas se separan los dos casos que el
    protocolo (§7) ya distinguía y el corredor no implementaba.
    """
    cols = sorted(str(c) for c in manifest.get("columns") or ())
    return hashlib.sha256("\n".join(cols).encode("utf-8")).hexdigest()[:8]


#: Días del final de la serie que se excluyen al comparar valores históricos. La cola
#: se reescribe sola —telemetría que llega tarde, MERGE que se regenera al mes
#: siguiente— y eso no es una corrección del pasado.
COLA_VOLATIL_D = 45


def huella_valores(snapshot: Path | None = None, cola_dias: int = COLA_VOLATIL_D) -> str | None:
    """Huella de los valores **históricos** del target, ignorando la cola reciente.

    Es la pieza que hace falta para no confundir «Gold agregó un día» con «Gold
    corrigió el pasado». Las dos cosas cambian el sha256 del parquet, pero sólo la
    segunda invalida lo ya corrido — y la segunda puede llegar sin cambiar ni una
    columna ni una fila: la Decisión 039 reescribió el 85,5 % de los caudales de
    2019-2026 dejando el esquema intacto.

    Se excluyen los últimos `cola_dias` porque esa franja se reescribe sola por
    diseño y marcarla como corrección sería un falso positivo diario.
    """
    import pandas as pd

    snapshot = snapshot or data_mod.DEFAULT_SNAPSHOT
    if not snapshot.exists():
        return None
    cols = ["fecha"] + [f"caudal_t_mas_{h}d" for h in data_mod.HORIZONS] + ["caudal_actual_m3s"]
    try:
        df = pd.read_parquet(snapshot, columns=cols)
    except (OSError, ValueError, KeyError):
        return None          # esquema distinto: eso ya lo detecta la comparación de columnas
    if df.empty:
        return None

    df["fecha"] = pd.to_datetime(df["fecha"])
    corte = df["fecha"].max() - pd.Timedelta(days=cola_dias)
    hist = df[df["fecha"] <= corte].sort_values("fecha")
    if hist.empty:
        return None
    # Redondeo a 3 decimales: protege de ruido de punto flotante entre exports sin
    # perder ninguna corrección real (la mediana de la Decisión 039 fue 105 m³/s).
    valores = hist.drop(columns=["fecha"]).round(3).to_numpy(dtype="float64")
    h = hashlib.sha256()
    h.update(str(hist["fecha"].iloc[0]).encode())
    h.update(str(hist["fecha"].iloc[-1]).encode())
    h.update(np.ascontiguousarray(np.nan_to_num(valores, nan=-9e18)).tobytes())
    return h.hexdigest()[:12]


def comparar_datasets(manifest: dict, previo: dict | None,
                      valores_ahora: str | None = None) -> dict:
    """Qué cambió entre dos snapshots, y si eso invalida lo ya corrido.

    Devuelve `modo`:

    - ``"igual"``           — nada cambió.
    - ``"filas_nuevas"``    — mismas columnas, mismos valores históricos, más filas:
      la cadena diaria agregó días al final. **No invalida nada.**
    - ``"esquema"``         — aparecieron o desaparecieron columnas. Invalida por
      cobertura, no por corrección del target.
    - ``"valores"``         — el pasado cambió: alguien corrigió el target. Es el
      caso de la Decisión 039 y el más peligroso, porque puede llegar **sin cambiar
      ni el esquema ni el número de filas**.
    - ``"filas_perdidas"``  — hay menos filas que antes: se rehízo historia.

    El orden de las comprobaciones importa: el esquema primero, porque si cambió no
    se puede comparar valores; los valores antes que las filas, porque una
    corrección del pasado invalida más que un día nuevo.
    """
    if previo is None:
        return {"modo": "sin_previo"}

    cols_a = set(str(c) for c in previo.get("columns") or ())
    cols_b = set(str(c) for c in manifest.get("columns") or ())
    filas_a = previo.get("rows") or 0
    filas_b = manifest.get("rows") or 0
    agregadas, quitadas = sorted(cols_b - cols_a), sorted(cols_a - cols_b)
    valores_antes = previo.get("valores_sha")

    detalle = {"columnas_agregadas": agregadas, "columnas_quitadas": quitadas,
               "filas_antes": filas_a, "filas_ahora": filas_b,
               "delta_antes": previo.get("delta_version"),
               "delta_ahora": manifest.get("delta_version"),
               "valores_antes": valores_antes, "valores_ahora": valores_ahora}

    if agregadas or quitadas:
        return {"modo": "esquema", **detalle}
    if valores_antes and valores_ahora and valores_antes != valores_ahora:
        return {"modo": "valores", **detalle}
    if filas_b < filas_a:
        return {"modo": "filas_perdidas", **detalle}
    if filas_b > filas_a:
        return {"modo": "filas_nuevas", **detalle}
    if valores_antes and valores_ahora is None:
        # No se pudo calcular la huella: no se puede afirmar que el pasado no cambió.
        return {"modo": "indeterminado", **detalle}
    return {"modo": "igual", **detalle}


# --------------------------------------------------------------------------
# Catálogo y ledger
# --------------------------------------------------------------------------

def cargar_matriz(path: Path | None = None) -> dict:
    import yaml
    return yaml.safe_load((path or MATRIZ).read_text(encoding="utf-8"))


def celdas_en_orden(matriz: dict) -> list[tuple[dict, dict]]:
    """Todas las celdas como (bloque, celda), en el orden del catálogo.

    El orden importa: cada bloque cierra fijando el ancla del siguiente (R10), así que
    recorrerlo salteado deja el ancla sin definir.
    """
    return [(b, c) for b in matriz["bloques"] for c in b["celdas"]]


def leer_ledger(path: Path | None = None) -> list[dict]:
    path = path or LEDGER
    if not path.exists():
        return []
    filas = []
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea:
            filas.append(json.loads(linea))
    return filas


def escribir_fila(fila: dict, path: Path | None = None) -> None:
    path = path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")


def ultima_fila(ledger: list[dict], celda_id: str, campana: str) -> dict | None:
    """La fila más reciente de esa celda dentro de la campaña. None si nunca corrió.

    Se busca por **campaña**, no por snapshot: un snapshot que sólo agregó filas al
    final pertenece a la misma campaña que el anterior, así que lo ya corrido sigue
    valiendo (ver `comparar_datasets`). Las filas viejas, escritas antes de que
    existiera el campo, caen de vuelta a `dataset` para no perderse.
    """
    candidatas = [f for f in ledger if f.get("celda") == celda_id
                  and f.get("campana", f.get("dataset")) == campana
                  and f.get("estado") != "historico"]
    return candidatas[-1] if candidatas else None


def resolver_campana(ledger: list[dict], ds_id: str, manifest: dict) -> tuple[str, dict]:
    """Bajo qué campaña se agrupa este snapshot, y qué cambió respecto de la anterior.

    Una campaña agrupa snapshots **equivalentes para las conclusiones**. Mientras el
    esquema no cambie y no se pierdan filas, agregar días al final no invalida nada
    y la campaña continúa. Si aparecen o desaparecen columnas, o si el snapshot
    encogió, arranca una campaña nueva y lo anterior queda histórico.
    """
    aperturas = [f for f in ledger if f.get("celda") == "APERTURA"]
    if not aperturas:
        return ds_id, {"modo": "sin_previo"}
    ultima = aperturas[-1]
    cambio = comparar_datasets(manifest, ultima.get("manifest") or {}, huella_valores())
    if cambio["modo"] in ("igual", "filas_nuevas"):
        return ultima.get("campana", ultima.get("dataset", ds_id)), cambio
    return ds_id, cambio


def resumen_manifest(manifest: dict) -> dict:
    """Lo mínimo del manifest que hace falta para comparar dos snapshots."""
    return {"delta_version": manifest.get("delta_version"),
            "rows": manifest.get("rows"),
            "columns": sorted(str(c) for c in manifest.get("columns") or ()),
            "esquema_sha": huella_esquema(manifest),
            "valores_sha": huella_valores(),
            "exported_at": manifest.get("exported_at")}


# --------------------------------------------------------------------------
# Lectura de resultados
# --------------------------------------------------------------------------

def tipo_de_celda(celda: dict) -> str:
    """Qué módulo corre la celda, que es lo que define cómo leer su JSON."""
    cmd = str(celda.get("cmd") or "")
    if not cmd or cmd.startswith("("):
        return "alias"
    for modulo, tipo in (("rio_search.train", "train"),
                         # ensemble imita el esquema de salida de train (models/
                         # <clave>/val/mean + seeds + baselines): se lee igual
                         ("rio_search.ensemble", "train"),
                         ("rio_search.search", "search"),
                         ("rio_search.walkforward", "walkforward"),
                         ("rio_search.sensitivity", "sensitivity"),
                         # dm produce un JSON de diagnóstico sin objetivo único,
                         # igual que un barrido: se lee como sensitivity
                         ("rio_search.dm", "sensitivity")):
        if modulo in cmd:
            return tipo
    return "guarda"          # pytest, audit, export_gold_dataset


def _bloque_val(datos: dict, tipo: str, celda: dict) -> dict | None:
    """El diccionario de métricas de VAL que corresponde a cada tipo de salida."""
    if tipo == "train":
        # Una celda de baseline (`lee: baselines:<clave>`) no mide el modelo
        # entrenado sino la vara que viaja en el mismo JSON.
        lee = str(celda.get("lee") or "")
        if lee.startswith("baselines:"):
            b = (datos.get("baselines") or {}).get(lee.split(":", 1)[1].strip()) or {}
            return (b.get("val") or {}).get("mean")
        modelos = datos.get("models") or {}
        if not modelos:
            return None
        if len(modelos) == 1:
            clave = next(iter(modelos))
        else:                                  # una corrida --compare
            cmd = str(celda.get("cmd") or "")
            clave = next((k for k in modelos if f"--loss {k}" in cmd), None)
            if clave is None:
                return None
        return (modelos[clave].get("val") or {}).get("mean")
    if tipo == "search":
        return (datos.get("final_multisemilla") or {}).get("val")
    return None                                 # walkforward y sensitivity: ver abajo


def extraer_metricas(datos: dict, tipo: str, celda: dict, objetivo: str) -> dict:
    """Métricas comparables de una corrida, más el skill contra persistencia.

    Devuelve siempre las mismas claves, con None donde el tipo de celda no las produce.
    Un barrido de sensibilidad y un walk-forward no tienen "un" número comparable con el
    ancla, y forzarlos a tenerlo sería inventar una comparación que el instrumento no hace.
    """
    fuera = {"objetivo": None, "objetivo_sd": None, "n_seeds": None,
             "skill_rmse_vs_persistencia": None, "val": None, "resumen": None}

    if tipo in ("walkforward", "sensitivity"):
        if tipo == "walkforward":
            fuera["resumen"] = {v: {k: r["test"].get(k) for k in (objetivo,) + METRICAS}
                                for v, r in (datos.get("resumen") or {}).items()}
        else:
            fuera["resumen"] = {"grid": datos.get("grid"), "modos": datos.get("modes"),
                                "dm": datos.get("pares"), "split": datos.get("split")}
        return fuera

    val = _bloque_val(datos, tipo, celda)
    if not val:
        return fuera

    fuera["val"] = {k: val.get(k) for k in (objetivo,) + METRICAS if val.get(k) is not None}
    fuera["objetivo"] = val.get(objetivo)
    fuera["objetivo_sd"] = val.get(f"{objetivo}_sd")
    fuera["n_seeds"] = len(datos.get("seeds") or []) or None

    persistencia = ((datos.get("baselines") or {}).get("persistencia") or {})
    base = (persistencia.get("val") or {}).get("mean") or persistencia
    rmse_base, rmse_celda = base.get("rmse"), val.get("rmse")
    if rmse_base and rmse_celda:
        fuera["skill_rmse_vs_persistencia"] = round(1.0 - rmse_celda / rmse_base, 4)
    return fuera


# --------------------------------------------------------------------------
# Veredicto
# --------------------------------------------------------------------------

def umbral_de_ruido(sd_a: float | None, n_a: int | None,
                    sd_b: float | None, n_b: int | None, sigmas: float = 2.0) -> float | None:
    """`sigmas · √(ee_a² + ee_b²)` con `ee = sd/√n`. None si falta algún desvío.

    Cubre el ruido de **inicialización**, no el del año: VAL es un solo año hidrológico y
    dos configuraciones que se separan limpiamente entre semillas pueden dar vuelta el
    orden en otro año. Por eso el cierre exige walk-forward (B11.01) y no este umbral.
    """
    if sd_a is None or sd_b is None or not n_a or not n_b:
        return None
    ee_a, ee_b = sd_a / math.sqrt(n_a), sd_b / math.sqrt(n_b)
    return sigmas * math.sqrt(ee_a ** 2 + ee_b ** 2)


def veredicto_de(m: dict, ancla: dict | None, sigmas: float = 2.0) -> tuple[str, dict]:
    """`gana` / `empata` / `pierde` / `descartado`, y el delta que lo sostiene.

    `descartado` gana a todo lo demás: una celda que no le gana a persistencia no compite,
    por más que su objetivo sea el mejor de la tabla (R6).
    """
    skill = m.get("skill_rmse_vs_persistencia")
    if skill is not None and skill <= 0:
        return "descartado", {"motivo": f"skill_rmse = {skill:.3f} ≤ 0: no supera persistencia"}

    if m.get("objetivo") is None:
        return "—", {}
    if not ancla or ancla.get("objetivo") is None:
        return "—", {"motivo": "sin ancla para este dataset"}

    delta = m["objetivo"] - ancla["objetivo"]
    umbral = umbral_de_ruido(m.get("objetivo_sd"), m.get("n_seeds"),
                             ancla.get("objetivo_sd"), ancla.get("n_seeds"), sigmas)
    detalle = {"objetivo": round(delta, 5), "umbral": round(umbral, 5) if umbral else None}
    if umbral is None:
        return "—", {**detalle, "motivo": "sin desvío entre semillas: no se puede decidir"}
    if delta < -umbral:
        return "gana", detalle
    if delta > umbral:
        return "pierde", detalle
    return "empata", detalle


# --------------------------------------------------------------------------
# Ejecución
# --------------------------------------------------------------------------

def _comando(celda: dict, tipo: str, bloque_id: str, salida: Path) -> list[str]:
    """El comando completo, con `--out` y con `--no-test` donde corresponde."""
    partes = shlex.split(str(celda["cmd"]))
    if partes and partes[0].endswith(".py"):
        argv = [sys.executable] + partes
    else:
        argv = [sys.executable] + partes

    if tipo in ("train", "search", "walkforward", "sensitivity"):
        argv += ["--out", str(salida)]
    # R3: TEST se calcula sólo en B11. En `train` es estructural — el bloque no se
    # escribe. `search` y `walkforward` no tienen el flag: ahí la regla la sostiene la
    # lectura (el corredor no mira TEST y el ledger guarda "no_leido").
    if tipo == "train" and bloque_id != "B11" and "--no-test" not in argv:
        argv.append("--no-test")
    return argv


def ejecutar_celda(bloque: dict, celda: dict, ds_id: str, *, objetivo: str,
                   ancla: dict | None, sigmas: float = 2.0, campana: str | None = None,
                   dry_run: bool = False, timeout: float | None = None) -> dict:
    """Corre una celda y devuelve su fila de ledger (sin escribirla).

    `dataset` es el snapshot exacto que la produjo (procedencia); `campana` es el
    grupo bajo el que se la busca después.
    """
    ahora = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    fila = {"celda": celda["id"], "nombre": celda.get("nombre"), "bloque": bloque["id"],
            "dataset": ds_id, "campana": campana or ds_id,
            "corrida_at": ahora, "prioridad": celda.get("prioridad")}

    estado_cat = celda.get("estado")
    if estado_cat != "implementado":
        return {**fila, "estado": "bloqueado", "veredicto": "—", "test": "no_leido",
                "motivo": {"falta": "hay que escribir código; requiere autorización (R7)",
                           "bloqueado_dato": celda.get("bloqueado_por", "el dato no existe"),
                           "requiere_autorizacion": "contradice una Decisión vigente"}
                          .get(estado_cat, estado_cat)}

    tipo = tipo_de_celda(celda)
    if tipo == "alias":
        return {**fila, "estado": "alias", "veredicto": "—", "test": "no_leido",
                "ref": str(celda.get("cmd") or "").strip("()= "),
                "motivo": "reusa la corrida de otra celda; no se ejecuta"}

    salida = RESULTS / (campana or ds_id) / f"{celda['id']}__{celda.get('slug', 'salida')}.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    argv = _comando(celda, tipo, bloque["id"], salida)
    fila["cmd"] = " ".join(argv[1:])
    fila["salida"] = str(salida.relative_to(REPO)) if tipo != "guarda" else None

    if dry_run:
        return {**fila, "estado": "dry_run", "veredicto": "—", "test": "no_leido"}

    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(argv, cwd=REPO, env=entorno, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {**fila, "estado": "error", "veredicto": "—", "test": "no_leido",
                "tiempo_s": round(time.perf_counter() - t0, 1),
                "motivo": f"timeout después de {timeout} s"}
    tiempo = round(time.perf_counter() - t0, 1)

    if proc.returncode != 0:
        cola = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        return {**fila, "estado": "error", "veredicto": "—", "test": "no_leido",
                "tiempo_s": tiempo, "returncode": proc.returncode,
                "motivo": "\n".join(cola)}

    fila["tiempo_s"] = tiempo
    fila["test"] = "no_leido"

    if tipo == "guarda":                       # tests, auditoría, refresco del snapshot
        return {**fila, "estado": "ok", "veredicto": "—"}

    if not salida.exists():
        return {**fila, "estado": "error", "veredicto": "—",
                "motivo": "la corrida terminó bien pero no dejó el JSON de salida"}

    datos = json.loads(salida.read_text(encoding="utf-8"))
    m = extraer_metricas(datos, tipo, celda, objetivo)
    v, detalle = veredicto_de(m, ancla, sigmas)
    return {**fila, "estado": "ok", "tipo": tipo, "veredicto": v,
            "val": m["val"], "objetivo": m["objetivo"], "objetivo_sd": m["objetivo_sd"],
            "n_seeds": m["n_seeds"],
            "skill_rmse_vs_persistencia": m["skill_rmse_vs_persistencia"],
            "resumen": m["resumen"], "delta_vs_ancla": detalle or None}


# --------------------------------------------------------------------------
# Informes
# --------------------------------------------------------------------------

def _f(v, nd=4):
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def fila_de_ancla(ledger: list[dict], matriz: dict, campana: str) -> dict | None:
    """La fila del ancla vigente, que es contra la que se calcula todo veredicto."""
    celda_ancla = matriz.get("ancla", {}).get("actualizada_en", "B0.06")
    f = ultima_fila(ledger, celda_ancla, campana)
    if not f or f.get("estado") != "ok":
        return None
    return {"objetivo": f.get("objetivo"), "objetivo_sd": f.get("objetivo_sd"),
            "n_seeds": f.get("n_seeds"), "celda": celda_ancla}


def informe_estado(matriz: dict, ledger: list[dict], campana: str,
                   ds_id: str | None = None, cambio: dict | None = None) -> None:
    """La fase F0 del protocolo: dónde está la búsqueda, sin correr nada."""
    celdas = celdas_en_orden(matriz)
    hechas = {c["id"]: ultima_fila(ledger, c["id"], campana) for _, c in celdas}
    ok = [i for i, f in hechas.items() if f and f["estado"] in ("ok", "alias")]
    bloq = [i for i, f in hechas.items() if f and f["estado"] == "bloqueado"]
    err = [i for i, f in hechas.items() if f and f["estado"] == "error"]
    pend = [i for i, f in hechas.items() if not f]

    otros = sorted({f.get("campana", f.get("dataset")) for f in ledger
                    if f.get("campana", f.get("dataset")) not in (campana, None)})
    ancla = fila_de_ancla(ledger, matriz, campana)

    print(f"\n  campaña vigente : {campana}")
    if ds_id and ds_id != campana:
        print(f"  snapshot de hoy : {ds_id}   (mismo esquema: la campaña sigue)")
    if cambio and cambio.get("modo") == "filas_nuevas":
        print(f"  ultimo cambio   : +{cambio['filas_ahora'] - cambio['filas_antes']} filas, "
              f"delta {cambio['delta_antes']} → {cambio['delta_ahora']}, esquema intacto")
    if otros:
        print(f"  campañas previas: {', '.join(otros)}   (--deriva las compara)")
    print(f"  celdas          : {len(ok)} ok · {len(bloq)} bloqueadas · "
          f"{len(err)} con error · {len(pend)} sin correr   (de {len(celdas)})")
    if ancla:
        print(f"  ancla ({ancla['celda']})   : objetivo = {_f(ancla['objetivo'])} "
              f"± {_f(ancla['objetivo_sd'])}  sobre {ancla['n_seeds']} semillas")
        u = umbral_de_ruido(ancla["objetivo_sd"], ancla["n_seeds"],
                            ancla["objetivo_sd"], ancla["n_seeds"])
        print(f"  umbral de ruido : ±{_f(u)}  (contra otra celda de igual dispersión)")
    else:
        print("  ancla           : SIN MEDIR — correr B0.06 antes de leer cualquier celda")

    p1_falta = [c["id"] for _, c in celdas
                if c.get("prioridad") == "P1" and not hechas.get(c["id"])]
    if p1_falta:
        print(f"  P1 sin cubrir   : {len(p1_falta)} → {', '.join(p1_falta[:8])}"
              f"{' …' if len(p1_falta) > 8 else ''}")

    siguiente = next((c for _, c in celdas if not hechas.get(c["id"])), None)
    print(f"  próxima celda   : {siguiente['id']} — {siguiente['nombre']}"
          if siguiente else "  próxima celda   : ninguna, el catálogo está cubierto")
    if err:
        print(f"  ATENCIÓN, con error: {', '.join(err)}")
    print()


def informe_bloque(bloque: dict, filas: list[dict], ancla: dict | None,
                   objetivo: str) -> None:
    corridas = [f for f in filas if f["estado"] == "ok" and f.get("objetivo") is not None]
    print(f"\n  BLOQUE {bloque['id']} — {bloque['nombre']}")
    if ancla:
        print(f"  ancla {ancla['celda']}: {objetivo} = {_f(ancla['objetivo'])} "
              f"± {_f(ancla['objetivo_sd'])}")
    print(f"  {'celda':9s}{'configuración':26s}{objetivo:>10s}{'Δ ancla':>10s}"
          f"{'RMSE':>8s}{'KGE':>7s}{'V+':>7s}{'V−':>7s}{'skill':>8s}  veredicto")
    for f in filas:
        val = f.get("val") or {}
        d = (f.get("delta_vs_ancla") or {}).get("objetivo")
        print(f"  {f['celda']:9s}{str(f.get('nombre'))[:25]:26s}"
              f"{_f(f.get('objetivo')):>10s}{_f(d, 4) if d is not None else '—':>10s}"
              f"{_f(val.get('rmse'), 0):>8s}{_f(val.get('kge'), 2):>7s}"
              f"{_f(val.get('v_plus'), 3):>7s}{_f(val.get('v_minus'), 3):>7s}"
              f"{_f(f.get('skill_rmse_vs_persistencia'), 3):>8s}  {f.get('veredicto')}")

    ganadoras = [f for f in filas if f.get("veredicto") == "gana"]
    bloqueadas = [f for f in filas if f["estado"] == "bloqueado"]
    umbrales = [(f.get("delta_vs_ancla") or {}).get("umbral") for f in corridas]
    umbrales = [u for u in umbrales if u is not None]
    if umbrales:
        # Uno por celda: depende de la dispersión de esa celda, no es una constante
        # del bloque. Una celda inestable necesita una diferencia mayor para contar.
        lo, hi = min(umbrales), max(umbrales)
        rango = f"±{_f(lo)}" if abs(hi - lo) < 1e-9 else f"±{_f(lo)} a ±{_f(hi)}"
        print(f"\n  umbral de ruido: {rango}   (uno por celda, según su dispersión)")

    # B0 y B11 no exploran un eje: no tienen ganador que mueva el ancla.
    if bloque.get("eje") and bloque["eje"] != "—":
        if ganadoras:
            mejor = min(ganadoras, key=lambda f: f["objetivo"])
            print(f"  ganador: {mejor['celda']} ({mejor['nombre']}) → pasa a ser el ancla; "
                  f"actualizar matrix.yaml → ancla")
        elif corridas:
            print(f"  ganador: ninguno — el ancla no se mueve, eje `{bloque['eje']}` "
                  f"queda saturado")
    if bloqueadas:
        print(f"  bloqueadas ({len(bloqueadas)}): "
              f"{', '.join(f['celda'] for f in bloqueadas)} — requieren autorización (R7)")
    print()


def informe_deriva(ledger: list[dict], campana: str) -> None:
    """Qué conclusiones se dieron vuelta al cambiar el dataset (protocolo §7)."""
    previos = [d for d in dict.fromkeys(f.get("campana", f.get("dataset")) for f in ledger)
               if d not in (campana, None)]
    if not previos:
        print("\n  no hay corridas de un dataset anterior: nada que comparar\n")
        return
    anterior = previos[-1]
    print(f"\n  DERIVA {anterior} → {campana}")
    print(f"  {'celda':9s}{'antes':>10s}{'ahora':>10s}   veredicto antes → ahora")
    cambios = 0
    comparadas = 0
    for celda_id in dict.fromkeys(f["celda"] for f in ledger):
        a = ultima_fila(ledger, celda_id, anterior)
        b = ultima_fila(ledger, celda_id, campana)
        if not a or not b or a.get("objetivo") is None or b.get("objetivo") is None:
            continue
        comparadas += 1
        giro = a.get("veredicto") != b.get("veredicto")
        cambios += giro
        print(f"  {celda_id:9s}{_f(a['objetivo']):>10s}{_f(b['objetivo']):>10s}"
              f"   {a.get('veredicto')} → {b.get('veredicto')}"
              f"{'   ⚠ cambió' if giro else ''}")
    print(f"\n  conclusiones que se dieron vuelta: {cambios} de {comparadas}")
    if cambios:
        print("  Una conclusión que se da vuelta con el dato nuevo no se resuelve acá: "
              "se reporta y se espera (protocolo §9).")
    print()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--estado", action="store_true", help="dónde está la búsqueda (F0)")
    g.add_argument("--bloque", help="correr un bloque, p. ej. B1")
    g.add_argument("--celda", help="correr una celda, p. ej. B1.03")
    g.add_argument("--todo", action="store_true", help="correr todo el catálogo en orden")
    g.add_argument("--deriva", action="store_true", help="comparar contra el dataset anterior")
    p.add_argument("--dry-run", action="store_true", help="mostrar qué correría, sin correr")
    p.add_argument("--rehacer", action="store_true",
                   help="re-correr celdas que ya tienen fila ok para este dataset")
    p.add_argument("--incluir-largas", action="store_true",
                   help=f"correr también las celdas de más de {LARGA_S} s estimados")
    p.add_argument("--timeout", type=float, default=None, help="segundos por celda")
    p.add_argument("--snapshot", default=None)
    p.add_argument("--matriz", default=None)
    args = p.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    matriz = cargar_matriz(Path(args.matriz) if args.matriz else None)
    objetivo = str(matriz.get("objetivo", "val/gral")).split("/")[-1]
    sigmas = float(matriz.get("umbral_sigmas", 2.0))
    ds_id, manifest = dataset_id(Path(args.snapshot) if args.snapshot else None)
    ledger = leer_ledger()
    campana, cambio = resolver_campana(ledger, ds_id, manifest)

    if args.estado:
        informe_estado(matriz, ledger, campana, ds_id, cambio)
        return 0
    if args.deriva:
        informe_deriva(ledger, campana)
        return 0

    ahora = lambda: datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    # Cambio de snapshot. Lo que decide si hay que descartar NO es que la versión Delta
    # haya subido —sube todos los días, porque la cadena diaria agrega un día— sino si
    # cambió el esquema o se perdieron filas. Es la distinción que el protocolo §7 ya
    # hacía y que el corredor no implementaba: agregar días al final no invalida nada.
    if cambio["modo"] == "filas_nuevas":
        print(f"  snapshot nuevo ({cambio['delta_antes']} → {cambio['delta_ahora']}, "
              f"+{cambio['filas_ahora'] - cambio['filas_antes']} filas) con el mismo esquema: "
              f"sigue la campaña {campana}. Lo ya corrido vale.")
        escribir_fila({"celda": "CONTINUA", "dataset": ds_id, "campana": campana,
                       "estado": "info", "corrida_at": ahora(), "cambio": cambio,
                       "manifest": resumen_manifest(manifest),
                       "veredicto": "—", "test": "no_leido"})
        ledger = leer_ledger()
    elif cambio["modo"] in ("esquema", "valores", "filas_perdidas",
                            "indeterminado", "sin_previo"):
        if cambio["modo"] == "esquema":
            ag, qu = cambio["columnas_agregadas"], cambio["columnas_quitadas"]
            print(f"  CAMBIO DE ESQUEMA ({cambio['delta_antes']} → {cambio['delta_ahora']}): "
                  f"{len(ag)} columna(s) nueva(s), {len(qu)} quitada(s). Campaña nueva.")
            for c in (ag[:6] + (['…'] if len(ag) > 6 else [])):
                print(f"      + {c}")
            for c in (qu[:6] + (['…'] if len(qu) > 6 else [])):
                print(f"      − {c}")
        elif cambio["modo"] == "valores":
            print(f"  EL PASADO CAMBIÓ ({cambio['delta_antes']} → {cambio['delta_ahora']}): "
                  f"mismo esquema y mismas filas, pero los valores históricos del target no "
                  f"coinciden ({cambio['valores_antes']} → {cambio['valores_ahora']}). "
                  f"Es una corrección del dato. Campaña nueva.")
        elif cambio["modo"] == "indeterminado":
            print("  No se pudo verificar si el pasado cambió (no hay huella de valores "
                  "comparable). Se abre campaña nueva por precaución.")
        elif cambio["modo"] == "filas_perdidas":
            print(f"  EL SNAPSHOT ENCOGIÓ ({cambio['filas_antes']} → {cambio['filas_ahora']} "
                  f"filas): se rehízo historia. Campaña nueva.")
        previas = {f.get("campana", f.get("dataset")) for f in ledger} - {campana, None}
        for vieja in sorted(previas):
            escribir_fila({"celda": "CIERRE", "campana": vieja, "dataset": vieja,
                           "estado": "historico", "corrida_at": ahora(),
                           "motivo": f"reemplazada por {campana} ({cambio['modo']})",
                           "veredicto": "—", "test": "no_leido"})
        escribir_fila({"celda": "APERTURA", "dataset": ds_id, "campana": campana,
                       "estado": "info", "corrida_at": ahora(), "cambio": cambio,
                       "manifest": resumen_manifest(manifest),
                       "veredicto": "—", "test": "no_leido"})
        if previas:
            print(f"  {len(previas)} campaña(s) anterior(es) marcada(s) como histórica(s); "
                  f"sus filas quedan para --deriva.")
        ledger = leer_ledger()

    celdas = celdas_en_orden(matriz)
    if args.celda:
        celdas = [(b, c) for b, c in celdas if c["id"] == args.celda]
        if not celdas:
            p.error(f"no existe la celda {args.celda} en el catálogo")
    elif args.bloque:
        celdas = [(b, c) for b, c in celdas if b["id"] == args.bloque]
        if not celdas:
            p.error(f"no existe el bloque {args.bloque} en el catálogo")

    print(f"\n  catálogo {MATRIZ.name} · campaña {campana} · snapshot {ds_id} · delta "
          f"{manifest['delta_version']} de {manifest.get('exported_at')}")
    print(f"  objetivo: val/{objetivo} · umbral {sigmas}σ · "
          f"{len(celdas)} celda(s) en el alcance\n")

    por_bloque: dict[str, list[dict]] = {}
    for bloque, celda in celdas:
        previa = ultima_fila(ledger, celda["id"], campana)
        if previa and not args.rehacer and previa["estado"] in ("ok", "alias", "bloqueado"):
            por_bloque.setdefault(bloque["id"], []).append(previa)
            continue

        estimado = celda.get("tiempo_est_s") or 0
        if estimado > LARGA_S and not args.incluir_largas and not args.dry_run:
            print(f"  {celda['id']:9s} omitida: {estimado} s estimados. "
                  f"Correr con --incluir-largas o --celda {celda['id']}.")
            continue

        # El ancla se relee en cada celda: si un bloque anterior la movió, el veredicto
        # de esta celda tiene que medirse contra la nueva.
        ancla = fila_de_ancla(ledger, matriz, campana)
        etiqueta = f"  {celda['id']:9s} {str(celda.get('nombre'))[:44]:45s}"
        if celda.get("estado") != "implementado":
            estado_txt = {"falta": "bloqueada: falta implementarla",
                          "bloqueado_dato": "bloqueada: falta el dato",
                          "requiere_autorizacion": "bloqueada: requiere autorización"}
            print(etiqueta + estado_txt.get(celda["estado"], "bloqueada"), flush=True)
        elif tipo_de_celda(celda) == "alias":
            print(etiqueta + f"alias de {str(celda['cmd']).strip('()= ')}", flush=True)
        else:
            print(etiqueta + ("(dry-run)" if args.dry_run else "corriendo ..."), flush=True)

        fila = ejecutar_celda(bloque, celda, ds_id, objetivo=objetivo, ancla=ancla,
                              sigmas=sigmas, campana=campana, dry_run=args.dry_run,
                              timeout=args.timeout)
        if not args.dry_run:
            escribir_fila(fila)
            ledger.append(fila)
        por_bloque.setdefault(bloque["id"], []).append(fila)

        if fila["estado"] == "error":
            print(f"    ERROR: {str(fila.get('motivo'))[:400]}")
            # R1/R2: una guarda en rojo es alto total, no una advertencia. Seguir
            # entrenando sobre un snapshot no verificado o con la auditoría de fuga
            # fallando produce números que se ven bien y no valen nada.
            if bloque["id"] == "B0" and tipo_de_celda(celda) == "guarda":
                print(f"\n  ALTO: falló una guarda de B0 ({celda['id']}). No se corre "
                      f"nada más sobre este snapshot hasta resolverlo (protocolo R1/R2).\n")
                return 2
        elif fila["estado"] == "ok" and fila.get("objetivo") is not None:
            print(f"    {objetivo} = {_f(fila['objetivo'])} ± {_f(fila.get('objetivo_sd'))}"
                  f"   → {fila['veredicto']}   ({fila.get('tiempo_s')} s)")
        elif fila["estado"] == "ok":
            print(f"    ok ({fila.get('tiempo_s')} s)")

    if not args.dry_run:
        ancla = fila_de_ancla(ledger, matriz, campana)
        for bloque_id, filas in por_bloque.items():
            bloque = next(b for b in matriz["bloques"] if b["id"] == bloque_id)
            informe_bloque(bloque, filas, ancla, objetivo)

    errores = [f for fs in por_bloque.values() for f in fs if f["estado"] == "error"]
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
