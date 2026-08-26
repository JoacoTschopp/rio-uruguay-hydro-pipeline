"""Backfill historico local de MERGE (precipitacion) y SAMeT (temperatura) de CPTEC/INPE,
recortados al bounding box de la cuenca -- ver docs/data_sources.md §9.6/§9.7 y Decision 033.

Descarga cada archivo diario en memoria (GRIB2 ~0,4 MB para MERGE; 3 NetCDF ~1,8 MB para
SAMeT), lo decodifica, recorta al bounding box de las 3 sub-cuencas y escribe UN Parquet por
producto y dia en output_parquet/{merge,samet}/. Nunca se guarda el archivo crudo en disco.
Ningun archivo se sube a Databricks desde aca: sync_to_databricks.py sube los Parquet.

Resumible via cptec_obs_backfill_state.json (source -> fecha -> status/last_modified/rows).
Usa el lock compartido de ana_historic_backfill para no correr en paralelo con otro backfill
local. Descarga en paralelo con procesos (cada proceso tiene su propia sesion HTTP y su
propio ecCodes -- ecCodes no es seguro entre threads).

Uso:
    python download_cptec_obs.py --source all                      # todo el archivo disponible
    python download_cptec_obs.py --source merge --from-date 2020-01-01 --to-date 2020-12-31
    python download_cptec_obs.py --source samet --refresh-days 14  # re-baja los ultimos 14 dias
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

LOCAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = LOCAL_DIR.parents[1]
STATE_FILE = LOCAL_DIR / "cptec_obs_backfill_state.json"
OUTPUT_DIR = LOCAL_DIR / "output_parquet"

sys.path.insert(0, str(LOCAL_DIR))
from common_cptec import SOURCES, download_area, first_date, new_session, process_day  # noqa: E402

ANA_BACKFILL_DIR = REPO_ROOT / "notebooks_local" / "ana_historic_backfill"
sys.path.insert(0, str(ANA_BACKFILL_DIR))
import lock  # noqa: E402  (notebooks_local/ana_historic_backfill/lock.py, reusado)

SAVE_STATE_EVERY = 100

_SESSION = None


def _worker(source: str, d_iso: str, area: dict, out_dir: str) -> tuple[str, str, dict]:
    """Corre en un proceso hijo: descarga + decodifica + recorta + escribe el Parquet de un dia."""
    global _SESSION
    if _SESSION is None:
        _SESSION = new_session()
    d = date.fromisoformat(d_iso)
    try:
        return source, d_iso, process_day(source, d, area, Path(out_dir), _SESSION)
    except Exception as exc:  # noqa: BLE001 -- se registra en el estado y sigue con el resto
        return source, d_iso, {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {s: {} for s in SOURCES}


def save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


def pending_days(state: dict, source: str, from_date: date, to_date: date, force: bool, refresh_days: int) -> list[date]:
    days = []
    refresh_floor = date.today() - timedelta(days=refresh_days) if refresh_days > 0 else None
    d = from_date
    while d <= to_date:
        entry = state.get(source, {}).get(d.isoformat(), {})
        done = entry.get("status") in ("done", "partial", "not_found")
        # Los `not_found` del pasado lejano no se reintentan (el archivo no existe); los recientes
        # si, porque el dia puede haberse publicado despues de la corrida anterior.
        recent = refresh_floor is not None and d >= refresh_floor
        if force or not done or recent:
            days.append(d)
        d += timedelta(days=1)
    return days


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=list(SOURCES) + ["all"], default="all")
    parser.add_argument("--from-date", type=date.fromisoformat, default=None, help="Default: primer dia real del archivo de cada producto")
    parser.add_argument("--to-date", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-days-per-run", type=int, default=0, help="0 = sin tope")
    parser.add_argument("--refresh-days", type=int, default=0, help="Re-descarga los ultimos N dias aunque esten done (regeneracion de CPTEC)")
    parser.add_argument("--force", action="store_true", help="Reprocesa dias ya marcados como done")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sources = list(SOURCES) if args.source == "all" else [args.source]

    if not lock.acquire("cptec_obs_backfill"):
        info = lock.read_lock()
        print(f"Ya hay un backfill corriendo (pid={info.get('pid') if info else '?'}); salgo.")
        return

    try:
        state = load_state()
        for s in sources:
            state.setdefault(s, {})

        work: list[tuple[str, date]] = []
        for s in sources:
            start = args.from_date or first_date(s)
            days = pending_days(state, s, start, args.to_date, args.force, args.refresh_days)
            print(f"[{s}] rango {start} .. {args.to_date}: {len(days)} dias pendientes")
            work.extend((s, d) for d in days)

        if args.max_days_per_run > 0:
            work = work[: args.max_days_per_run]
        if args.dry_run or not work:
            print(f"{len(work)} dias a procesar (dry-run={args.dry_run}); nada que hacer." if not work or args.dry_run else "")
            for s, d in work[:20]:
                print(f"  {s} {d}")
            return

        areas = {s: download_area(s) for s in sources}
        for s in sources:
            print(f"[{s}] area de recorte: {areas[s]}")
            (OUTPUT_DIR / s).mkdir(parents=True, exist_ok=True)

        t0 = time.time()
        done = failed = 0
        since_save = 0
        print(f"Procesando {len(work)} dias con {args.workers} procesos...")
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(_worker, s, d.isoformat(), areas[s], str(OUTPUT_DIR / s)) for s, d in work]
            for i, fut in enumerate(as_completed(futures), 1):
                s, d_iso, result = fut.result()
                state[s][d_iso] = result
                if result.get("status") == "failed":
                    failed += 1
                    print(f"  [{s} {d_iso}] FALLO: {result.get('error')}")
                else:
                    done += 1
                since_save += 1
                if since_save >= SAVE_STATE_EVERY:
                    save_state(state)
                    since_save = 0
                    elapsed = time.time() - t0
                    rate = i / elapsed if elapsed > 0 else 0
                    eta = (len(work) - i) / rate / 60 if rate > 0 else float("inf")
                    print(f"  {i}/{len(work)} ({done} ok, {failed} fallos) {rate:.1f} dias/s, ETA {eta:.0f} min")
        save_state(state)

        print(f"\nListo: {done} ok, {failed} fallos en {(time.time() - t0) / 60:.1f} min.")
        for s in sources:
            n_done = sum(1 for v in state[s].values() if v.get("status") in ("done", "partial"))
            n_nf = sum(1 for v in state[s].values() if v.get("status") == "not_found")
            n_fail = sum(1 for v in state[s].values() if v.get("status") == "failed")
            print(f"  [{s}] estado acumulado: {n_done} con datos, {n_nf} inexistentes en origen, {n_fail} fallidos")
    finally:
        lock.release()


if __name__ == "__main__":
    main()
