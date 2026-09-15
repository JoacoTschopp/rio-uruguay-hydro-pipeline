"""Tests del corredor del catálogo y del catálogo mismo.

Dos cosas distintas se verifican acá y conviene no confundirlas:

1. **El catálogo es coherente** — ids únicos, comandos que parsean, celdas
   implementadas que apuntan a un módulo que existe. Un catálogo roto no se nota
   hasta que una corrida larga muere a mitad de camino.
2. **El corredor sostiene las reglas del protocolo por código y no por disciplina** —
   que `--no-test` se agregue fuera de B11, que el veredicto salga del umbral de ruido
   y no de comparar dos números, y que una celda que no supera persistencia quede
   descartada aunque su objetivo sea el mejor de la tabla.
"""

from __future__ import annotations

import json
import shlex
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import runner as R


# --------------------------------------------------------------------------
# El catálogo
# --------------------------------------------------------------------------

def test_matriz_carga_y_tiene_lo_minimo():
    m = R.cargar_matriz()
    assert m["objetivo"].startswith("val/")
    assert m["umbral_sigmas"] > 0
    for clave in ("model", "loss", "groups", "seeds", "gate_rain"):
        assert clave in m["ancla"], f"al ancla le falta {clave}"
    assert m["bloques"], "el catálogo no tiene bloques"


def test_ids_de_celda_unicos_y_ordenados_por_bloque():
    celdas = R.celdas_en_orden(R.cargar_matriz())
    ids = [c["id"] for _, c in celdas]
    assert len(ids) == len(set(ids)), "hay ids repetidos"
    for bloque, celda in celdas:
        assert celda["id"].startswith(bloque["id"] + "."), \
            f"{celda['id']} no pertenece al bloque {bloque['id']}"


def test_toda_celda_declara_estado_y_prioridad():
    validos = {"implementado", "falta", "bloqueado_dato", "requiere_autorizacion"}
    for _, c in R.celdas_en_orden(R.cargar_matriz()):
        assert c.get("estado") in validos, f"{c['id']}: estado {c.get('estado')!r}"
        assert c.get("prioridad") in {"P1", "P2", "P3"}, f"{c['id']}: sin prioridad"
        assert c.get("nombre"), f"{c['id']}: sin nombre"


def test_celdas_implementadas_tienen_comando_parseable():
    """Un `cmd` que no parsea rompe recién al ejecutarse, y puede ser media hora después."""
    for _, c in R.celdas_en_orden(R.cargar_matriz()):
        if c["estado"] != "implementado":
            continue
        assert c.get("cmd"), f"{c['id']}: implementada pero sin cmd"
        partes = shlex.split(str(c["cmd"]))
        assert partes, f"{c['id']}: cmd vacío"
        if R.tipo_de_celda(c) != "alias":
            assert c.get("slug"), f"{c['id']}: sin slug, el archivo de salida no tiene nombre"


def test_celdas_que_faltan_dicen_como_implementarlas():
    """Sin eso, la celda bloqueada no se puede convertir en un pedido de autorización."""
    for _, c in R.celdas_en_orden(R.cargar_matriz()):
        if c["estado"] == "falta":
            assert c.get("implementar"), f"{c['id']}: falta sin bloque `implementar`"
        if c["estado"] == "bloqueado_dato":
            assert c.get("bloqueado_por"), f"{c['id']}: sin decir qué lo bloquea"


def test_tipo_de_celda():
    t = R.tipo_de_celda
    assert t({"cmd": "-m rio_search.train --loss gral"}) == "train"
    assert t({"cmd": "-m rio_search.search --trials 60"}) == "search"
    assert t({"cmd": "-m rio_search.walkforward --n-folds 5"}) == "walkforward"
    assert t({"cmd": "-m rio_search.sensitivity --seeds 3"}) == "sensitivity"
    assert t({"cmd": "-m pytest rio_search/tests -q"}) == "guarda"
    assert t({"cmd": "(= B0.06)"}) == "alias"
    assert t({}) == "alias"


# --------------------------------------------------------------------------
# R3: TEST se calcula sólo en B11
# --------------------------------------------------------------------------

def test_no_test_se_agrega_fuera_de_b11():
    celda = {"id": "B1.03", "slug": "mse_log", "cmd": "-m rio_search.train --loss mse_log"}
    argv = R._comando(celda, "train", "B1", Path("x.json"))
    assert "--no-test" in argv
    assert "--out" in argv


def test_no_test_no_se_agrega_dentro_de_b11():
    """B11 es el único bloque que puede mirar TEST; agregarle el flag lo dejaría ciego."""
    celda = {"id": "B11.02", "slug": "test_unico", "cmd": "-m rio_search.train --loss gral"}
    argv = R._comando(celda, "train", "B11", Path("x.json"))
    assert "--no-test" not in argv


def test_no_test_no_se_agrega_a_lo_que_no_lo_acepta():
    """walkforward y sensitivity no tienen el flag: pasárselo mataría la corrida."""
    for tipo, cmd in (("walkforward", "-m rio_search.walkforward --n-folds 5"),
                      ("sensitivity", "-m rio_search.sensitivity --seeds 3"),
                      ("search", "-m rio_search.search --trials 10")):
        argv = R._comando({"id": "X.01", "slug": "x", "cmd": cmd}, tipo, "B9", Path("x.json"))
        assert "--no-test" not in argv, f"{tipo} no acepta --no-test"


def test_guarda_no_recibe_out():
    """pytest y la auditoría no escriben JSON; un --out las haría fallar."""
    celda = {"id": "B0.02", "slug": "tests", "cmd": "-m pytest rio_search/tests -q"}
    argv = R._comando(celda, "guarda", "B0", Path("x.json"))
    assert "--out" not in argv


# --------------------------------------------------------------------------
# Umbral de ruido y veredicto
# --------------------------------------------------------------------------

def test_umbral_de_ruido():
    # sd = 0,01 con 4 semillas ⇒ ee = 0,005 por lado; combinado ×√2, ×2 sigmas
    u = R.umbral_de_ruido(0.01, 4, 0.01, 4, sigmas=2.0)
    assert abs(u - 2 * (2 * 0.005 ** 2) ** 0.5) < 1e-12
    assert R.umbral_de_ruido(None, 5, 0.01, 5) is None
    assert R.umbral_de_ruido(0.01, 0, 0.01, 5) is None


def _m(objetivo, sd=0.01, n=5, skill=0.2):
    return {"objetivo": objetivo, "objetivo_sd": sd, "n_seeds": n,
            "skill_rmse_vs_persistencia": skill}


def test_veredicto_gana_pierde_empata():
    ancla = _m(0.500)
    assert R.veredicto_de(_m(0.400), ancla)[0] == "gana"     # muy por debajo
    assert R.veredicto_de(_m(0.600), ancla)[0] == "pierde"
    assert R.veredicto_de(_m(0.502), ancla)[0] == "empata"   # dentro del umbral


def test_una_mejora_menor_al_ruido_no_es_una_victoria():
    """Es la regla R5, y es la que evita leer ruido de inicialización como resultado."""
    ancla = _m(0.5000, sd=0.0096, n=5)
    u = R.umbral_de_ruido(0.0096, 5, 0.0096, 5)
    apenas = _m(0.5000 - u * 0.9, sd=0.0096, n=5)
    assert R.veredicto_de(apenas, ancla)[0] == "empata"
    claro = _m(0.5000 - u * 1.5, sd=0.0096, n=5)
    assert R.veredicto_de(claro, ancla)[0] == "gana"


def test_descartado_gana_a_todo():
    """Sin skill contra persistencia no compite, aunque su objetivo sea el mejor (R6)."""
    ancla = _m(0.500)
    v, detalle = R.veredicto_de(_m(0.100, skill=-0.05), ancla)
    assert v == "descartado"
    assert "persistencia" in detalle["motivo"]


def test_sin_ancla_no_hay_veredicto():
    v, detalle = R.veredicto_de(_m(0.400), None)
    assert v == "—" and "ancla" in detalle["motivo"]


def test_sin_desvio_no_se_decide():
    """Un solo seed no da desvío; inventar un veredicto ahí sería leer ruido."""
    v, detalle = R.veredicto_de(_m(0.400, sd=None, n=1), _m(0.500))
    assert v == "—" and "desvío" in detalle["motivo"]


# --------------------------------------------------------------------------
# Lectura de resultados
# --------------------------------------------------------------------------

def _json_train(gral=0.42, sd=0.01, rmse=1000.0, rmse_persistencia=1200.0):
    mean = {"gral": gral, "gral_sd": sd, "rmse": rmse, "nse": 0.3, "kge": 0.5,
            "v_plus": 0.4, "v_minus": 0.6, "fa_wet": 0.3}
    return {"seeds": [1, 2, 3, 4, 5],
            "models": {"gral": {"val": {"mean": mean}}},
            "baselines": {"persistencia": {"val": {"mean": {"rmse": rmse_persistencia}}}}}


def test_extraer_metricas_de_train():
    m = R.extraer_metricas(_json_train(), "train", {"cmd": "-m rio_search.train"}, "gral")
    assert m["objetivo"] == 0.42 and m["objetivo_sd"] == 0.01 and m["n_seeds"] == 5
    # el ledger guarda el skill redondeado a 4 decimales
    assert abs(m["skill_rmse_vs_persistencia"] - (1 - 1000 / 1200)) < 1e-4
    assert m["val"]["kge"] == 0.5


def test_extraer_metricas_elige_la_perdida_del_comando_en_un_compare():
    datos = _json_train()
    datos["models"]["mse_log"] = {"val": {"mean": {"gral": 0.99, "gral_sd": 0.01,
                                                   "rmse": 2000.0}}}
    m = R.extraer_metricas(datos, "train", {"cmd": "-m rio_search.train --loss mse_log"},
                           "gral")
    assert m["objetivo"] == 0.99


def test_walkforward_y_sensitivity_no_producen_un_objetivo_comparable():
    """Forzarlos a tener uno sería inventar una comparación que el instrumento no hace."""
    wf = {"resumen": {"expandible": {"test": {"gral": 0.6, "rmse": 1900.0}}}}
    m = R.extraer_metricas(wf, "walkforward", {}, "gral")
    assert m["objetivo"] is None and m["resumen"]["expandible"]["gral"] == 0.6
    assert R.veredicto_de(m, _m(0.5))[0] == "—"

    sw = {"grid": [0.6, 0.85], "split": "val"}
    assert R.extraer_metricas(sw, "sensitivity", {}, "gral")["resumen"]["grid"] == [0.6, 0.85]


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------

def test_ledger_es_append_only_y_devuelve_la_ultima():
    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    R.escribir_fila({"celda": "B1.01", "dataset": "d1-aa", "estado": "ok",
                     "objetivo": 0.5}, tmp)
    R.escribir_fila({"celda": "B1.01", "dataset": "d1-aa", "estado": "ok",
                     "objetivo": 0.4}, tmp)
    filas = R.leer_ledger(tmp)
    assert len(filas) == 2, "una re-corrida agrega fila, no edita la anterior"
    assert R.ultima_fila(filas, "B1.01", "d1-aa")["objetivo"] == 0.4
    assert R.ultima_fila(filas, "B1.01", "d2-bb") is None, "no cruza datasets"
    assert R.ultima_fila(filas, "B9.99", "d1-aa") is None


def test_las_filas_historicas_no_cuentan_como_corridas():
    tmp = Path(tempfile.mkdtemp()) / "ledger.jsonl"
    R.escribir_fila({"celda": "B1.01", "dataset": "d1-aa", "estado": "historico"}, tmp)
    assert R.ultima_fila(R.leer_ledger(tmp), "B1.01", "d1-aa") is None


def test_ledger_inexistente_es_una_busqueda_de_cero():
    assert R.leer_ledger(Path(tempfile.mkdtemp()) / "no_existe.jsonl") == []


def test_fila_de_ancla_exige_estado_ok():
    matriz = {"ancla": {"actualizada_en": "B0.06"}}
    ledger = [{"celda": "B0.06", "dataset": "d1-aa", "estado": "error"}]
    assert R.fila_de_ancla(ledger, matriz, "d1-aa") is None
    ledger.append({"celda": "B0.06", "dataset": "d1-aa", "estado": "ok",
                   "objetivo": 0.5, "objetivo_sd": 0.01, "n_seeds": 5})
    assert R.fila_de_ancla(ledger, matriz, "d1-aa")["objetivo"] == 0.5


# --------------------------------------------------------------------------
# Celdas que no se ejecutan
# --------------------------------------------------------------------------

def test_celda_que_falta_no_se_ejecuta_y_deja_su_motivo():
    """R7: el corredor nunca implementa una celda por iniciativa propia."""
    fila = R.ejecutar_celda({"id": "B1"}, {"id": "B1.07", "nombre": "huber",
                                           "estado": "falta"}, "d1-aa",
                            objetivo="gral", ancla=None)
    assert fila["estado"] == "bloqueado" and "autorización" in fila["motivo"]
    assert fila["test"] == "no_leido"


def test_celda_bloqueada_por_dato_dice_que_la_bloquea():
    fila = R.ejecutar_celda({"id": "B2"}, {"id": "B2.19", "nombre": "forecast",
                                           "estado": "bloqueado_dato",
                                           "bloqueado_por": "Fase 4 del roadmap"},
                            "d1-aa", objetivo="gral", ancla=None)
    assert fila["estado"] == "bloqueado" and "Fase 4" in fila["motivo"]


def test_celda_alias_no_corre_nada():
    fila = R.ejecutar_celda({"id": "B1"}, {"id": "B1.05", "nombre": "gral",
                                           "estado": "implementado", "cmd": "(= B0.06)"},
                            "d1-aa", objetivo="gral", ancla=None)
    assert fila["estado"] == "alias" and fila["ref"] == "B0.06"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests del corredor OK")
