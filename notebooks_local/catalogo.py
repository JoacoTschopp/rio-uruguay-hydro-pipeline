# -*- coding: utf-8 -*-
"""Catalogo unico de dias descargados: donde esta cada archivo y si llego al volumen.

Por que existe (Decision 046). Hasta ahora la pregunta "ya baje este dia?" se contestaba
haciendo stat() sobre el directorio de archivo. Eso trajo tres problemas concretos:

1. Con el archivo en un disco externo por USB, un backfill que pregunta dia por dia hace
   miles de lecturas contra el disco lento.
2. La presencia del archivo en disco NO implica que haya llegado a Databricks. El 2026-09-05
   aparecieron 29 dias de febrero 2022 que estaban en W: pero nunca en el volumen: el sync
   solo escanea el directorio local, asi que no los veia, y already_landed() los daba por
   buenos. Eran un hueco permanente que nadie iba a corregir.
3. GEFS ya usaba otro mecanismo (gefs_backfill_state.json) y ECMWF usaba presencia de
   archivo, asi que no habia forma de mirar el estado completo de una sola vez.

El catalogo unifica las cuatro fuentes y cruza las tres ubicaciones posibles (disco local,
archivo externo, volumen de Databricks). La tarea diaria lo revalida entero, asi que la
deriva entre el indice y la realidad queda acotada a 24 h.

Uso:
    python catalogo.py escanear            # recorre discos, actualiza el indice
    python catalogo.py volumen             # lista los volumenes y marca que llego
    python catalogo.py reporte             # resumen + discrepancias
    python catalogo.py revalidar           # escanear + volumen + reporte (lo que corre a diario)
"""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "catalogo.db"
PROFILE = "joaquintschopp@gmail.com"

ECMWF = BASE / "ecmwf" / "local_data" / "ecmwf_volume"

# Cada fuente declara: donde escribe el descargador, donde se archiva cuando el disco aprieta,
# cual es su volumen en Databricks, y desde/hasta que fechas tiene sentido esperar dato.
FUENTES: dict[str, dict] = {
    "ecmwf_cf": {
        "prefijo": "ECMWF_CF",
        "dir_local": ECMWF / "cf_tigge" / "json",
        "dirs_archivo": [],
        "volumen": "dbfs:/Volumes/weather/raw/ecmwf_volume/cf_tigge/json",
        "desde": date(2006, 10, 1),
    },
    "ecmwf_pf": {
        "prefijo": "ECMWF_PF",
        "dir_local": ECMWF / "pf_tigge" / "json",
        "dirs_archivo": [
            Path(r"D:\rio_uruguay\pf_tigge_json"),
            Path(r"W:\Instaladores\swap\tschopp\pf_tigge_json"),
        ],
        "volumen": "dbfs:/Volumes/weather/raw/ecmwf_volume/pf_tigge/json",
        "desde": date(2006, 10, 1),
    },
    "ecmwf_fc": {
        "prefijo": "ECMWF_FC",
        "dir_local": ECMWF / "fc_opendata" / "json",
        "dirs_archivo": [],
        "volumen": "dbfs:/Volumes/weather/raw/ecmwf_volume/fc_opendata/json",
        "desde": date(2026, 7, 27),
    },
    "gefs_reforecast": {
        "prefijo": "GEFS",
        "dir_local": BASE / "gefs_reforecast" / "output_json",
        "dirs_archivo": [],
        "volumen": "dbfs:/Volumes/weather/raw/gefs_volume/json",
        "desde": date(2000, 1, 1),
    },
}

RE_NOMBRE = re.compile(r"^(?P<pref>[A-Z_]+?)_(?P<y>\d{4})_(?P<m>\d{2})_(?P<d>\d{2})_t(?P<hh>\d{2})\.json$")

DDL = """
CREATE TABLE IF NOT EXISTS archivos (
    fuente        TEXT NOT NULL,
    fecha         TEXT NOT NULL,
    run_time      TEXT NOT NULL,
    nombre        TEXT NOT NULL,
    ubicacion     TEXT,            -- directorio donde esta, '' si solo esta en el volumen
    bytes         INTEGER,
    mtime         REAL,
    en_volumen    INTEGER DEFAULT 0,
    bytes_volumen INTEGER,
    verificado_en TEXT,
    PRIMARY KEY (fuente, fecha, run_time)
);
CREATE INDEX IF NOT EXISTS ix_fuente_fecha ON archivos(fuente, fecha);
CREATE TABLE IF NOT EXISTS corridas (
    momento TEXT, accion TEXT, detalle TEXT
);
"""


def conectar() -> sqlite3.Connection:
    cx = sqlite3.connect(DB_PATH)
    cx.executescript(DDL)
    return cx


def _parse(nombre: str):
    m = RE_NOMBRE.match(nombre)
    if not m:
        return None
    return f"{m['y']}-{m['m']}-{m['d']}", m["hh"]


def escanear(cx: sqlite3.Connection) -> dict:
    """Recorre disco local y directorios de archivo. El orden importa: se recorre primero el
    archivo y despues el local, para que si un dia esta en los dos (pasa durante una migracion)
    gane la copia local, que es la que el sync mira."""
    ahora = datetime.now(timezone.utc).isoformat()
    resumen = {}
    for fuente, cfg in FUENTES.items():
        vistos = 0
        for d in list(cfg["dirs_archivo"])[::-1] + [cfg["dir_local"]]:
            if not d.exists():
                continue
            for f in d.iterdir():
                if not f.name.startswith(cfg["prefijo"]) or not f.name.endswith(".json"):
                    continue
                p = _parse(f.name)
                if not p:
                    continue
                fecha, hh = p
                try:
                    st = f.stat()
                except OSError:
                    continue
                cx.execute(
                    """INSERT INTO archivos (fuente,fecha,run_time,nombre,ubicacion,bytes,mtime,verificado_en)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(fuente,fecha,run_time) DO UPDATE SET
                         nombre=excluded.nombre, ubicacion=excluded.ubicacion,
                         bytes=excluded.bytes, mtime=excluded.mtime,
                         verificado_en=excluded.verificado_en""",
                    (fuente, fecha, hh, f.name, str(d), st.st_size, st.st_mtime, ahora),
                )
                vistos += 1
        # un dia que el indice daba en disco y ya no esta en ningun lado queda con ubicacion
        # vacia, no se borra: si esta en el volumen sigue siendo un dia cubierto.
        cx.execute(
            "UPDATE archivos SET ubicacion='' WHERE fuente=? AND verificado_en<>? AND ubicacion<>''",
            (fuente, ahora),
        )
        resumen[fuente] = vistos
    cx.commit()
    cx.execute("INSERT INTO corridas VALUES (?,?,?)", (ahora, "escanear", json.dumps(resumen)))
    cx.commit()
    return resumen


def _listar_volumen(vol: str) -> dict:
    """Devuelve {nombre: bytes} del volumen. Usa --output json para no parsear columnas."""
    out = subprocess.run(
        ["databricks", "fs", "ls", vol, "--profile", PROFILE, "--output", "json"],
        capture_output=True, text=True, timeout=900,
    )
    if out.returncode != 0:
        raise RuntimeError(f"no se pudo listar {vol}: {out.stderr.strip()[:200]}")
    return {x["name"]: x.get("file_size") for x in json.loads(out.stdout or "[]")}


def reconciliar_volumen(cx: sqlite3.Connection) -> dict:
    ahora = datetime.now(timezone.utc).isoformat()
    resumen = {}
    for fuente, cfg in FUENTES.items():
        try:
            enel = _listar_volumen(cfg["volumen"])
        except Exception as e:
            resumen[fuente] = f"ERROR: {str(e)[:120]}"
            continue
        cx.execute("UPDATE archivos SET en_volumen=0 WHERE fuente=?", (fuente,))
        for nombre, tam in enel.items():
            p = _parse(nombre)
            if not p:
                continue
            fecha, hh = p
            cx.execute(
                """INSERT INTO archivos (fuente,fecha,run_time,nombre,ubicacion,en_volumen,bytes_volumen,verificado_en)
                   VALUES (?,?,?,?,'',1,?,?)
                   ON CONFLICT(fuente,fecha,run_time) DO UPDATE SET
                     en_volumen=1, bytes_volumen=excluded.bytes_volumen, verificado_en=excluded.verificado_en""",
                (fuente, fecha, hh, nombre, tam, ahora),
            )
        resumen[fuente] = len(enel)
    cx.commit()
    cx.execute("INSERT INTO corridas VALUES (?,?,?)", (ahora, "volumen", json.dumps(resumen)))
    cx.commit()
    return resumen


def dias_cubiertos(cx: sqlite3.Connection, fuente: str) -> set:
    """Dias que existen en algun lado (disco o volumen). Es lo que consulta el backfill en
    vez de golpear el disco externo dia por dia."""
    return {
        date.fromisoformat(r[0])
        for r in cx.execute(
            "SELECT fecha FROM archivos WHERE fuente=? AND (en_volumen=1 OR ubicacion<>'')", (fuente,)
        )
    }


def reporte(cx: sqlite3.Connection) -> None:
    print(f"{'fuente':<18}{'dias':>7}{'en disco':>10}{'en volumen':>12}{'SOLO disco':>12}{'solo volumen':>14}{'GB disco':>10}")
    print("  " + "-" * 84)
    problemas = []
    for fuente, cfg in FUENTES.items():
        f = cx.execute(
            """SELECT count(*),
                      sum(ubicacion<>''), sum(en_volumen=1),
                      sum(ubicacion<>'' AND en_volumen=0),
                      sum(ubicacion='' AND en_volumen=1),
                      coalesce(sum(CASE WHEN ubicacion<>'' THEN bytes END),0)
               FROM archivos WHERE fuente=?""", (fuente,)
        ).fetchone()
        total, disco, vol, solo_disco, solo_vol, nbytes = [x or 0 for x in f]
        print(f"{fuente:<18}{total:>7}{disco:>10}{vol:>12}{solo_disco:>12}{solo_vol:>14}{nbytes/1e9:>10.1f}")
        # Distinguir pendiente de huerfano es el punto de todo esto: un dia en el directorio
        # LOCAL que no esta en el volumen lo sube el proximo sync y no hay nada que hacer; uno
        # en un directorio de ARCHIVO no lo va a subir nadie nunca, porque sync_to_databricks.py
        # solo escanea el local. Mezclarlos haria que la tarea diaria avise siempre y se ignore.
        huerfanos = cx.execute(
            "SELECT count(*) FROM archivos WHERE fuente=? AND en_volumen=0 AND ubicacion<>'' AND ubicacion<>?",
            (fuente, str(cfg["dir_local"])),
        ).fetchone()[0]
        if huerfanos:
            problemas.append(("HUERFANOS " + fuente, huerfanos))
        # huecos de calendario
        cub = dias_cubiertos(cx, fuente)
        if cub:
            d0, d1 = cfg["desde"], max(cub)
            faltan = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)
                      if d0 + timedelta(days=i) not in cub]
            if faltan:
                problemas.append((f"{fuente} (huecos de calendario)", len(faltan)))

    print()
    if problemas:
        print("DISCREPANCIAS:")
        for que, n in problemas:
            if "huecos" in que:
                print(f"  - {que}: {n} dias sin dato entre el inicio y el ultimo dia cubierto")
            else:
                print(f"  - {que}: {n} dias ARCHIVADOS que no estan en el volumen. "
                      f"El sync solo escanea el directorio local, asi que nadie los va a subir: "
                      f"hay que copiarlos a mano con 'databricks fs cp'.")
    else:
        print("Sin discrepancias.")
    ult = cx.execute("SELECT momento,accion FROM corridas ORDER BY momento DESC LIMIT 1").fetchone()
    if ult:
        print(f"\nultima revalidacion: {ult[0]} ({ult[1]})")


def main() -> int:
    accion = sys.argv[1] if len(sys.argv) > 1 else "reporte"
    cx = conectar()
    if accion in ("escanear", "revalidar"):
        print("escaneando discos...", flush=True)
        print("  ", escanear(cx))
    if accion in ("volumen", "revalidar"):
        print("listando volumenes...", flush=True)
        print("  ", reconciliar_volumen(cx))
    print()
    reporte(cx)
    cx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
