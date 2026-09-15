"""Sube los Parquet del backfill de MERGE/SAMeT (ya recortados a la cuenca, ver
download_cptec_obs.py) al Volume de Databricks que lee ETL_Bronze_CPTEC_Obs.ipynb, y el
catalogo grid_subcuenca.json que siembra DDL_CPTEC_Obs.ipynb. No dispara ningun job.

Dos modos de subida:
  * por archivo (default): sube solo los Parquet que todavia no estan en el Volume, en
    paralelo (`databricks fs cp`), igual que gefs_reforecast/sync_to_databricks.py. Sirve para
    sincronizaciones chicas (dias nuevos, re-descargas puntuales).
  * --bundle: empaqueta TODOS los Parquet pendientes en uno o mas ZIP (<= 1,5 GB c/u), sube
    los ZIP a `staging/` del Volume y deja que ETL_Bronze_CPTEC_Obs.ipynb los descomprima en
    `{source}/daily/` antes de leer (un `databricks fs cp` por archivo tarda ~1-2 s de
    overhead; con ~20.000 archivos de la carga inicial eso son horas, contra minutos con el ZIP).

Requiere `databricks` CLI autenticado (perfil pasado por --profile).

Uso:
    python sync_to_databricks.py --profile joaquintschopp@gmail.com --catalogo
    python sync_to_databricks.py --profile joaquintschopp@gmail.com --source all --bundle
    python sync_to_databricks.py --profile joaquintschopp@gmail.com --source merge
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

LOCAL_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = LOCAL_DIR / "output_parquet"
CATALOGO_FILE = LOCAL_DIR / "grid_subcuenca.json"
STAGING_DIR = LOCAL_DIR / "staging_zip"

VOLUME_ROOT = "dbfs:/Volumes/weather/raw/cptec_volume"
SOURCES = ("merge", "samet")
MAX_ZIP_BYTES = 1_500_000_000


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def list_remote_files(profile: str, remote_dir: str) -> set[str]:
    result = _run(["databricks", "-p", profile, "fs", "ls", remote_dir, "--output", "json"], timeout=900)
    if result.returncode != 0:
        if any(s in result.stderr for s in ("does not exist", "RESOURCE_DOES_NOT_EXIST", "no such directory", "No such file")):
            return set()
        raise RuntimeError(f"No se pudo listar {remote_dir}: {result.stderr}")
    entries = json.loads(result.stdout) if result.stdout.strip() else []
    return {e["name"] for e in entries}


def upload_file(profile: str, local: Path, remote: str, timeout: int = 3600) -> tuple[bool, str]:
    try:
        result = _run(["databricks", "-p", profile, "fs", "cp", str(local), remote, "--overwrite"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if result.returncode != 0:
        return False, result.stderr.strip()[:300]
    return True, ""


def sync_catalogo(profile: str, log=print) -> None:
    if not CATALOGO_FILE.exists():
        raise RuntimeError(f"No existe {CATALOGO_FILE}; corre build_grid_subcuenca.py primero")
    remote = f"{VOLUME_ROOT}/catalogo/{CATALOGO_FILE.name}"
    ok, err = upload_file(profile, CATALOGO_FILE, remote)
    log(f"catalogo -> {remote}: {'OK' if ok else 'FALLO ' + err}")
    if not ok:
        raise RuntimeError(err)


def pending_files(profile: str, source: str, force: bool, log=print) -> list[Path]:
    local_dir = OUTPUT_DIR / source
    if not local_dir.exists():
        log(f"[{source}] no existe {local_dir}, nada que subir")
        return []
    local_files = sorted(local_dir.glob(f"{source.upper()}_*.parquet"))
    if force:
        return local_files
    remote_dir = f"{VOLUME_ROOT}/{source}/daily"
    log(f"[{source}] listando {remote_dir}...")
    remote = list_remote_files(profile, remote_dir)
    pending = [f for f in local_files if f.name not in remote]
    log(f"[{source}] {len(local_files)} locales, {len(pending)} pendientes")
    return pending


def sync_per_file(profile: str, source: str, files: list[Path], max_workers: int, log=print) -> dict:
    summary = {"uploaded": 0, "failed": 0, "errors": []}
    remote_dir = f"{VOLUME_ROOT}/{source}/daily"
    log_lock = threading.Lock()

    def one(f: Path):
        ok, err = upload_file(profile, f, f"{remote_dir}/{f.name}", timeout=600)
        return f.name, ok, err

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(one, f) for f in files]
        for i, fut in enumerate(as_completed(futures), 1):
            name, ok, err = fut.result()
            with log_lock:
                if ok:
                    summary["uploaded"] += 1
                    if i % 50 == 0 or i == len(files):
                        log(f"  [{source}] {i}/{len(files)} subidos")
                else:
                    summary["failed"] += 1
                    summary["errors"].append(f"{name}: {err}")
                    log(f"  [{source}] FALLO {name}: {err}")
    return summary


def sync_bundle(profile: str, source: str, files: list[Path], log=print) -> dict:
    """Empaqueta en ZIP (sin compresion: el Parquet ya viene comprimido con zstd) y sube a
    staging/. ETL_Bronze_CPTEC_Obs.ipynb descomprime y borra el ZIP."""
    STAGING_DIR.mkdir(exist_ok=True)
    summary = {"zips": 0, "files": 0, "failed": 0, "errors": []}
    batch, batch_bytes, part = [], 0, 1

    def flush():
        nonlocal batch, batch_bytes, part
        if not batch:
            return
        zip_path = STAGING_DIR / f"{source}_daily_part{part:03d}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
            for f in batch:
                zf.write(f, arcname=f.name)
        remote = f"{VOLUME_ROOT}/staging/{zip_path.name}"
        log(f"  [{source}] subiendo {zip_path.name} ({zip_path.stat().st_size / 1e6:.0f} MB, {len(batch)} archivos)...")
        ok, err = upload_file(profile, zip_path, remote, timeout=3600)
        if ok:
            summary["zips"] += 1
            summary["files"] += len(batch)
            zip_path.unlink(missing_ok=True)
        else:
            summary["failed"] += 1
            summary["errors"].append(f"{zip_path.name}: {err}")
            log(f"  [{source}] FALLO {zip_path.name}: {err}")
        batch, batch_bytes, part = [], 0, part + 1

    for f in files:
        size = f.stat().st_size
        if batch and batch_bytes + size > MAX_ZIP_BYTES:
            flush()
        batch.append(f)
        batch_bytes += size
    flush()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--source", choices=list(SOURCES) + ["all"], default=None, help="Que Parquet subir (omitir para subir solo el catalogo)")
    parser.add_argument("--catalogo", action="store_true", help="Subir grid_subcuenca.json a catalogo/")
    parser.add_argument("--bundle", action="store_true", help="Subir en ZIP a staging/ (carga inicial masiva)")
    parser.add_argument("--force", action="store_true", help="Subir todo aunque ya exista en el Volume")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    if args.catalogo:
        sync_catalogo(args.profile)

    if args.source:
        sources = list(SOURCES) if args.source == "all" else [args.source]
        for source in sources:
            files = pending_files(args.profile, source, args.force)
            if not files:
                continue
            if args.bundle:
                print(json.dumps({source: sync_bundle(args.profile, source, files)}, ensure_ascii=False))
            else:
                print(json.dumps({source: sync_per_file(args.profile, source, files, args.workers)}, ensure_ascii=False))
        print("\nListo. El proximo run de ETL_Bronze_CPTEC_Obs descomprime staging/ (si aplica) y mergea los Parquet.")


if __name__ == "__main__":
    main()
