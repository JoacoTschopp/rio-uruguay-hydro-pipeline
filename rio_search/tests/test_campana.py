"""Tests de la identidad de campaña: cuándo un snapshot nuevo invalida lo corrido.

La regla que se verifica acá es la que el protocolo (§7) siempre tuvo escrita y el
corredor no implementaba: **subir la versión Delta no es motivo para descartar**. La
cadena diaria de Gold publica una versión nueva todos los días porque agrega un día de
datos, y eso no invalida ninguna conclusión. Lo que sí la invalida es que cambie el
conjunto de columnas o que se pierdan filas.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rio_search import runner as R


def _man(delta, rows, cols, valores=None):
    return {"delta_version": delta, "rows": rows, "columns": list(cols),
            "valores_sha": valores, "file_sha256": "%064x" % delta,
            "exported_at": "2026-09-15T00:00:00"}


COLS = ["fecha", "caudal_actual_m3s", "caudal_t_mas_1d"]


# --------------------------------------------------------------------------
# comparar_datasets
# --------------------------------------------------------------------------

def test_un_dia_mas_no_invalida_nada():
    """El caso de todos los días: la cadena diaria agrega una fila y sube el delta."""
    c = R.comparar_datasets(_man(299, 9754, COLS), _man(297, 9753, COLS))
    assert c["modo"] == "filas_nuevas"
    assert c["filas_antes"] == 9753 and c["filas_ahora"] == 9754


def test_columna_nueva_si_invalida():
    """Atributos nuevos: el catálogo puede querer usarlos, hay que rehacer."""
    c = R.comparar_datasets(_man(299, 9754, COLS + ["ecmwf_cf_tp_mm_d1"]), _man(297, 9753, COLS))
    assert c["modo"] == "esquema"
    assert c["columnas_agregadas"] == ["ecmwf_cf_tp_mm_d1"]
    assert c["columnas_quitadas"] == []


def test_columna_que_desaparece_tambien_invalida():
    c = R.comparar_datasets(_man(299, 9754, COLS[:-1]), _man(297, 9753, COLS))
    assert c["modo"] == "esquema" and c["columnas_quitadas"] == ["caudal_t_mas_1d"]


def test_snapshot_que_encoge_es_cambio_de_fondo():
    """Menos filas = se rehízo historia. No hay forma de saber qué se movió."""
    assert R.comparar_datasets(_man(299, 9000, COLS), _man(297, 9753, COLS))["modo"] == "filas_perdidas"


def test_una_correccion_del_pasado_invalida_aunque_no_cambie_nada_mas():
    """EL CASO PELIGROSO. La Decisión 039 reescribió el 85,5 % de los caudales de
    2019-2026 **sin tocar el esquema ni el número de filas**. Una regla que sólo
    mire columnas y filas lo deja pasar, y todas las conclusiones quedan calculadas
    contra un target que ya cambió."""
    c = R.comparar_datasets(_man(303, 9754, COLS), _man(299, 9754, COLS, valores="aaa"),
                            valores_ahora="bbb")
    assert c["modo"] == "valores", "una corrección del target no puede pasar como 'igual'"
    assert c["valores_antes"] == "aaa" and c["valores_ahora"] == "bbb"


def test_un_dia_nuevo_con_el_pasado_intacto_sigue_sin_invalidar():
    """El contrapeso: la huella de valores no puede convertir el append diario en
    un falso positivo."""
    c = R.comparar_datasets(_man(299, 9754, COLS), _man(297, 9753, COLS, valores="aaa"),
                            valores_ahora="aaa")
    assert c["modo"] == "filas_nuevas"


def test_correccion_del_pasado_gana_sobre_filas_nuevas():
    """Si en la misma corrida se agregó un día Y se corrigió el pasado, manda la
    corrección: es lo que más invalida."""
    c = R.comparar_datasets(_man(303, 9755, COLS), _man(299, 9754, COLS, valores="aaa"),
                            valores_ahora="bbb")
    assert c["modo"] == "valores"


def test_sin_huella_comparable_no_se_afirma_que_el_pasado_no_cambio():
    """Prudencia: si no se pudo calcular la huella, no se puede continuar la campaña
    como si nada."""
    c = R.comparar_datasets(_man(303, 9754, COLS), _man(299, 9754, COLS, valores="aaa"),
                            valores_ahora=None)
    assert c["modo"] == "indeterminado"


def test_correccion_del_pasado_abre_campana():
    prev = _man(299, 9754, COLS, valores="aaa")
    ledger = _ledger_con_apertura("d299-aaaa", prev)
    # se fuerza la huella nueva sin tocar el parquet real
    orig = R.huella_valores
    R.huella_valores = lambda *a, **k: "bbb"
    try:
        campana, cambio = R.resolver_campana(ledger, "d303-bbbb", _man(303, 9754, COLS))
    finally:
        R.huella_valores = orig
    assert campana == "d303-bbbb" and cambio["modo"] == "valores"


def test_huella_de_valores_del_snapshot_real_es_estable():
    """Sobre el parquet de verdad: dos llamadas seguidas dan lo mismo."""
    a = R.huella_valores()
    if a is None:
        return                      # sin snapshot local, nada que verificar
    assert a == R.huella_valores() and len(a) == 12


def test_mismo_snapshot():
    assert R.comparar_datasets(_man(297, 9753, COLS, valores="a"),
                               _man(297, 9753, COLS, valores="a"), "a")["modo"] == "igual"


def test_el_orden_de_las_columnas_no_importa():
    """El manifest puede reordenar columnas sin que eso sea un cambio de esquema."""
    c = R.comparar_datasets(_man(299, 9753, list(reversed(COLS)), valores="a"),
                            _man(297, 9753, COLS, valores="a"), "a")
    assert c["modo"] == "igual"


def test_huella_de_esquema_ignora_filas_y_orden():
    a = R.huella_esquema(_man(297, 9753, COLS))
    assert a == R.huella_esquema(_man(999, 12345, list(reversed(COLS))))
    assert a != R.huella_esquema(_man(297, 9753, COLS + ["nueva"]))


# --------------------------------------------------------------------------
# resolver_campana
# --------------------------------------------------------------------------

def _ledger_con_apertura(campana, manifest):
    return [{"celda": "APERTURA", "dataset": campana, "campana": campana,
             "estado": "info", "manifest": R.resumen_manifest(manifest)}]


def test_dia_nuevo_continua_la_campana():
    """Lo que motivó todo el arreglo: el replay no se reinicia por un día más."""
    prev = _man(297, 9753, COLS)
    ledger = _ledger_con_apertura("d297-aaaa", prev)
    campana, cambio = R.resolver_campana(ledger, "d299-bbbb", _man(299, 9754, COLS))
    assert campana == "d297-aaaa", "un día más no puede abrir campaña nueva"
    assert cambio["modo"] == "filas_nuevas"


def test_columna_nueva_abre_campana():
    prev = _man(297, 9753, COLS)
    ledger = _ledger_con_apertura("d297-aaaa", prev)
    campana, cambio = R.resolver_campana(ledger, "d299-bbbb", _man(299, 9754, COLS + ["x"]))
    assert campana == "d299-bbbb" and cambio["modo"] == "esquema"


def test_sin_apertura_previa_la_campana_es_el_snapshot():
    campana, cambio = R.resolver_campana([], "d297-aaaa", _man(297, 9753, COLS))
    assert campana == "d297-aaaa" and cambio["modo"] == "sin_previo"


def test_las_celdas_se_encuentran_a_traves_del_cambio_de_snapshot():
    """El punto de todo: una celda corrida ayer sigue encontrándose hoy."""
    prev = _man(297, 9753, COLS)
    ledger = _ledger_con_apertura("d297-aaaa", prev)
    ledger.append({"celda": "B1.03", "dataset": "d297-aaaa", "campana": "d297-aaaa",
                   "estado": "ok", "objetivo": 0.47})
    campana, _ = R.resolver_campana(ledger, "d299-bbbb", _man(299, 9754, COLS))
    assert R.ultima_fila(ledger, "B1.03", campana)["objetivo"] == 0.47


def test_las_filas_viejas_sin_campana_siguen_encontrandose():
    """Compatibilidad: el ledger anterior no tenía el campo `campana`."""
    ledger = [{"celda": "B1.03", "dataset": "d278-vieja", "estado": "ok", "objetivo": 0.477}]
    assert R.ultima_fila(ledger, "B1.03", "d278-vieja")["objetivo"] == 0.477


def test_una_campana_no_ve_las_celdas_de_otra():
    ledger = [{"celda": "B1.03", "dataset": "d1", "campana": "d1", "estado": "ok", "objetivo": 0.4}]
    assert R.ultima_fila(ledger, "B1.03", "d2") is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print()
    print(f"{len(fns)} tests de campaña OK")
