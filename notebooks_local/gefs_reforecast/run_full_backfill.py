"""Orquestador del backfill historico completo de GEFS Reforecast v12: paraleliza
`download_gefs_backfill.py` por dia (varios workers -- **procesos**, no threads, ver nota abajo --
S3 publico sin cuenta/cola que proteger, a diferencia de TIGGE/ECDS, ver el docstring de
`download_file` en common_gefs.py) y sincroniza + borra localmente en lotes, para no acumular
cientos de GB de JSON en disco antes de subir nada (la maquina tiene ~437 GB libres; un dia
completo de 5 miembros pesa ~164 MiB recortado, no hay margen para acumular meses enteros sin
sincronizar).

**Por que procesos y no threads (confirmado empiricamente, no asumido):** `cfgrib`/`eccodes` no
es thread-safe -- correr `xr.open_dataset(..., engine="cfgrib")` desde varios threads del mismo
proceso al mismo tiempo corrompe el estado interno de la libreria C de eccodes
(`ECCODES ERROR: grib_handle_create: Cannot create handle, no definitions found`, con threads
concurrentes pisandose el filesystem en memoria que usa eccodes para sus tablas de definiciones).
Cada worker de `ProcessPoolExecutor` tiene su propio proceso (su propio estado de eccodes), asi
que evita el problema por completo, a costa de un poco de overhead de arranque de proceso --
despreciable frente al tiempo de descarga por dia.

Pensado para correr desatendido durante horas/dias: si se corta (Ctrl-C, reinicio, corte de luz),
es resumible -- el estado por dia vive en gefs_backfill_state.json y el sync es idempotente
(sólo sube lo que todavia no esta en el Volume). Volver a correr el mismo comando retoma donde
quedo.

Uso:
    python run_full_backfill.py --from-date 2000-01-01 --to-date 2006-09-30 --workers 8 \
        --sync-every-days 30 --profile joaquintschopp@gmail.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common_gefs import (  # noqa: E402
    EARLIEST_GEFS_DATE,
    LATEST_GEFS_DATE,
    compute_download_area,
    flatten_member_day,
    list_members,
    write_json,
)
import sync_to_databricks  # noqa: E402

LOCAL_DIR = Path(__file__).parent
REPO_ROOT = LOCAL_DIR.parents[1]
GEOJSON_PATH = REPO_ROOT / "SIG" / "subcuencas_modelo.geojson"

STATE_FILE = LOCAL_DIR / "gefs_backfill_state.json"
OUTPUT_JSON_DIR = LOCAL_DIR / "output_json"
TMP_DIR_BASE = LOCAL_DIR / "tmp_grib"

ANA_BACKFILL_DIR = REPO_ROOT / "notebooks_local" / "ana_historic_backfill"
sys.path.insert(0, str(ANA_BACKFILL_DIR))
import lock  # noqa: E402

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"days": {}}


def save_state(state: dict) -> None:
    # Solo se llama desde el loop principal (as_completed corre serial en el proceso padre),
    # nunca desde los workers de ProcessPoolExecutor -- no hace falta lock.
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def process_one_day(run_date: date, area: dict) -> tuple[str, dict]:
    """Corre en un worker thread. Sesion HTTP propia por thread (requests.Session no es
    thread-safe para compartir entre threads en paralelo)."""
    session = requests.Session()
    tmp_dir = TMP_DIR_BASE / f"worker_{run_date.isoformat()}"
    try:
        members = list_members(session, run_date)
        if not members:
            return run_date.isoformat(), {"status": "not_found", "members": [], "records": 0}

        all_records: list[dict] = []
        for member in members:
            records = flatten_member_day(session, run_date, member, area, tmp_dir)
            if records is None:
                continue
            all_records.extend(records)

        if not all_records:
            return run_date.isoformat(), {"status": "empty", "members": members, "records": 0}

        out_file = OUTPUT_JSON_DIR / f"GEFS_{run_date:%Y_%m_%d}_t00.json"
        write_json(all_records, out_file)
        return run_date.isoformat(), {"status": "done", "members": members, "records": len(all_records)}
    except Exception as exc:
        return run_date.isoformat(), {"status": "failed", "error": str(exc)}
    finally:
        try:
            if tmp_dir.exists():
                for p in tmp_dir.iterdir():
                    p.unlink(missing_ok=True)
                tmp_dir.rmdir()
        except OSError:
            pass


def _unlink_with_retry(path: Path, attempts: int = 5, delay_seconds: float = 2.0) -> bool:
    """Windows a veces mantiene un lock transitorio sobre un archivo recien escrito/leido
    (antivirus, indexado) que tira `PermissionError: [WinError 32]` en el primer intento de
    borrarlo -- confirmado empiricamente en esta corrida. Reintenta antes de darse por vencido;
    si sigue fallando, se deja el archivo local (no es fatal, sync_to_databricks.py es
    idempotente y lo va a saltear la proxima vez)."""
    for attempt in range(attempts):
        try:
            path.unlink()
            return True
        except PermissionError:
            if attempt == attempts - 1:
                return False
            time.sleep(delay_seconds)
    return False


def sync_and_clean(profile: str) -> None:
    """Sube todo lo pendiente y borra localmente los JSON ya confirmados en el Volume --
    mantiene el disco local acotado durante una corrida de meses."""
    print("--- Sincronizando lote a Databricks ---")
    summary = sync_to_databricks.sync(profile)
    print(f"Sync: {summary['uploaded']} subidos, {summary['skipped']} ya estaban, {summary['failed']} fallidos")
    if summary["failed"] > 0:
        print("Hay archivos que fallaron al subir -- se conservan localmente, no se borran.")

    remote_files = sync_to_databricks.list_remote_files(profile, sync_to_databricks.VOLUME_JSON_DIR)
    deleted = 0
    locked = 0
    for f in OUTPUT_JSON_DIR.glob("GEFS_*.json"):
        if f.name in remote_files:
            if _unlink_with_retry(f):
                deleted += 1
            else:
                locked += 1
    msg = f"Borrados {deleted} JSON locales ya confirmados en el Volume."
    if locked:
        msg += f" {locked} no se pudieron borrar (lock de Windows persistente) -- quedan para el proximo lote."
    print(msg + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-date", type=date.fromisoformat, default=EARLIEST_GEFS_DATE)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--workers", type=int, default=8, help="Dias procesados en paralelo")
    parser.add_argument("--sync-every-days", type=int, default=30, help="Sincroniza y limpia cada N dias completados")
    parser.add_argument("--profile", required=True, help="Perfil de databricks CLI para sync_to_databricks.py")
    parser.add_argument("--force", action="store_true", help="Reprocesa dias ya marcados como done")
    args = parser.parse_args()

    if args.from_date < EARLIEST_GEFS_DATE or args.to_date > LATEST_GEFS_DATE:
        print(f"Rango fuera de la cobertura real de GEFS v12 ({EARLIEST_GEFS_DATE} .. {LATEST_GEFS_DATE})")
        return

    if not lock.acquire("gefs_backfill"):
        info = lock.read_lock()
        print(f"Ya hay un backfill corriendo (pid={info.get('pid') if info else '?'}); salgo.")
        return

    try:
        OUTPUT_JSON_DIR.mkdir(exist_ok=True)
        TMP_DIR_BASE.mkdir(exist_ok=True)
        area = compute_download_area(GEOJSON_PATH)
        print(f"Area de descarga: {area}")

        state = load_state()
        all_dates = []
        d = args.from_date
        while d <= args.to_date:
            if args.force or state["days"].get(d.isoformat(), {}).get("status") != "done":
                all_dates.append(d)
            d += timedelta(days=1)

        total_target = (args.to_date - args.from_date).days + 1
        print(f"Rango objetivo: {args.from_date} .. {args.to_date} ({total_target} dias totales, {len(all_dates)} pendientes)")
        print(f"workers={args.workers}, sync-every-days={args.sync_every_days}")

        from concurrent.futures import ProcessPoolExecutor, as_completed

        completed_since_sync = 0
        start_time = time.time()
        n_done_total = 0

        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_one_day, d, area): d for d in all_dates}
            for future in as_completed(futures):
                run_date = futures[future]
                try:
                    day_key, result = future.result()
                except Exception as exc:
                    day_key, result = run_date.isoformat(), {"status": "failed", "error": str(exc)}

                state["days"][day_key] = result
                save_state(state)
                n_done_total += 1
                elapsed_min = (time.time() - start_time) / 60
                rate = n_done_total / elapsed_min if elapsed_min > 0 else 0
                print(f"[{n_done_total}/{len(all_dates)}] {day_key}: {result.get('status')} "
                      f"({len(result.get('members', []))} miembros, {result.get('records', 0)} registros) "
                      f"-- {elapsed_min:.1f} min transcurridos, {rate:.1f} dias/min")

                if result.get("status") == "done":
                    completed_since_sync += 1
                if completed_since_sync >= args.sync_every_days:
                    try:
                        sync_and_clean(args.profile)
                    except Exception as exc:
                        # Un sync fallido (timeout, red caida, etc.) no debe tirar abajo una
                        # corrida de horas/dias -- los JSON quedan localmente y se reintentan
                        # en el proximo lote o al terminar (ver Decision 030).
                        print(f"ERROR en sync_and_clean, se continua sin subir este lote: {exc}")
                    completed_since_sync = 0

        if completed_since_sync > 0:
            try:
                sync_and_clean(args.profile)
            except Exception as exc:
                print(f"ERROR en el sync final, correr sync_to_databricks.py a mano para el resto: {exc}")

        done = sum(1 for v in state["days"].values() if v.get("status") == "done")
        failed = sum(1 for v in state["days"].values() if v.get("status") == "failed")
        print(f"\nTerminado. {done} dias completos en el estado acumulado, {failed} fallidos en esta corrida.")
        if failed:
            print("Volver a correr el mismo comando reintenta los dias fallidos automaticamente (no estan marcados done).")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
