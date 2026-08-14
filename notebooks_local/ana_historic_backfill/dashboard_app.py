"""Dashboard local (Gradio) para monitorear y controlar el backfill historico de ANA.

Corre 100% local, no consume computo de Databricks. Lee el estado que ya escribe
run_backfill_local.py (historic_backfill_state.json, logs/backfill.log, backfill.lock) y
ofrece botones para arrancar/parar una corrida y disparar un sync manual al Volume de
Databricks. Pensado para correr junto con las tareas programadas de Windows (ver
scheduler/register_tasks.ps1) - el lock de un solo proceso (lock.py) evita que un click
de "Iniciar" en la UI pise una corrida que la tarea programada ya dispar processo.

Uso:
    python dashboard_app.py
    (abre http://127.0.0.1:7860)
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import gradio as gr

import lock
import sync_to_databricks

LOCAL_DIR = Path(__file__).parent
STATE_FILE = LOCAL_DIR / "historic_backfill_state.json"
LOG_FILE = LOCAL_DIR / "logs" / "backfill.log"
LAST_SYNC_FILE = LOCAL_DIR / "last_sync.json"
PYTHON = sys.executable

DEFAULT_PROFILE = "joaquintschopp@gmail.com"


def _read_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_last_sync() -> dict | None:
    if not LAST_SYNC_FILE.exists():
        return None
    try:
        return json.loads(LAST_SYNC_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _tail_log(n_lines: int = 60) -> str:
    if not LOG_FILE.exists():
        return "(sin logs todavia)"
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n_lines:]) or "(log vacio)"


def render_status() -> str:
    state = _read_state()
    running_info = lock.is_locked()
    last_sync = _read_last_sync()

    parts = []
    if running_info:
        started = datetime.fromtimestamp(running_info["started_at"]).strftime("%Y-%m-%d %H:%M:%S")
        parts.append(f"**Estado: corriendo** (pid={running_info['pid']}, desde {started})")
    else:
        parts.append("**Estado: detenido**")

    if state:
        n_active = len(state.get("active_stations", []))
        n_exhausted = len(state.get("exhausted_stations", {}))
        next_window = state.get("next_window_end", "?")
        parts.append(f"- Estaciones activas: **{n_active}**")
        parts.append(f"- Estaciones agotadas: **{n_exhausted}**")
        parts.append(f"- Proxima ventana (yendo hacia atras): **{next_window}**")
    else:
        parts.append("- Sin `historic_backfill_state.json` todavia.")

    n_local_files = len(list((LOCAL_DIR / "output_json").glob("ANA_HIST_*.json"))) if (LOCAL_DIR / "output_json").exists() else 0
    parts.append(f"- Archivos JSON locales listos para subir: **{n_local_files}**")

    if last_sync:
        finished = datetime.fromtimestamp(last_sync["finished_at"]).strftime("%Y-%m-%d %H:%M:%S")
        parts.append(
            f"- Ultimo sync: {finished} — subidos={last_sync['uploaded']}, "
            f"ya estaban={last_sync['skipped']}, fallidos={last_sync['failed']}"
        )
    else:
        parts.append("- Sin sync todavia.")

    return "\n".join(parts)


def refresh():
    return render_status(), _tail_log()


def start_backfill(max_windows: int):
    if lock.is_locked():
        gr.Warning("Ya hay un backfill corriendo (via tarea programada o esta UI). No se inicia otro.")
        return refresh()
    subprocess.Popen(
        [PYTHON, str(LOCAL_DIR / "run_backfill_local.py"), "--max-windows", str(int(max_windows))],
        cwd=str(LOCAL_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    gr.Info(f"Backfill iniciado en background (hasta {int(max_windows)} ventanas).")
    return refresh()


def stop_backfill():
    stopped = lock.stop_running()
    if stopped:
        gr.Info("Proceso detenido. El estado de la ultima ventana completa queda guardado (resumible).")
    else:
        gr.Warning("No habia ningun backfill corriendo.")
    return refresh()


def sync_now(profile: str, sync_state: bool):
    log_lines: list[str] = []
    try:
        summary = sync_to_databricks.sync(profile.strip(), sync_state=sync_state, log=log_lines.append)
    except Exception as exc:  # noqa: BLE001 - se muestra en la UI, no hace falta mas contexto
        gr.Warning(f"Sync fallo: {exc}")
        return refresh()
    gr.Info(f"Sync terminado: {summary['uploaded']} subidos, {summary['failed']} fallidos, {summary['skipped']} ya estaban.")
    return refresh()


with gr.Blocks(title="ANA Backfill - Dashboard") as demo:
    gr.Markdown("# Backfill historico ANA (nivel + lluvia)")
    gr.Markdown(
        "Corre 100% local. Databricks solo recibe los JSON ya descargados via sync "
        "(no corre el download). Ver `docs/decisions.md` Decision 015/016."
    )

    status_md = gr.Markdown(render_status())

    with gr.Row():
        max_windows_input = gr.Number(value=20, label="Ventanas por tanda (--max-windows)", precision=0)
        start_btn = gr.Button("Iniciar backfill", variant="primary")
        stop_btn = gr.Button("Detener", variant="stop")

    with gr.Row():
        profile_input = gr.Textbox(value=DEFAULT_PROFILE, label="Perfil Databricks CLI")
        sync_state_checkbox = gr.Checkbox(value=False, label="Tambien subir historic_backfill_state.json (backup)")
        sync_btn = gr.Button("Sincronizar ahora")

    log_box = gr.Textbox(value=_tail_log(), label="Log (ultimas 60 lineas)", lines=20, max_lines=20, interactive=False)

    start_btn.click(start_backfill, inputs=[max_windows_input], outputs=[status_md, log_box])
    stop_btn.click(stop_backfill, outputs=[status_md, log_box])
    sync_btn.click(sync_now, inputs=[profile_input, sync_state_checkbox], outputs=[status_md, log_box])

    timer = gr.Timer(5)
    timer.tick(refresh, outputs=[status_md, log_box])


if __name__ == "__main__":
    demo.launch()
