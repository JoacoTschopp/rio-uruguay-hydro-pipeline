# Registra las 2 tareas programadas de Windows para el backfill historico de ANA:
#   - ANA_Backfill_Download: corre run_backfill_task.ps1 (tandas de --max-windows 10) cada 4 horas.
#   - ANA_Backfill_Sync: corre sync_task.ps1 (sube JSON al Volume de Databricks) 2x/dia (08:00 y 20:00).
#
# MultipleInstances=IgnoreNew en ambas: si la tarea anterior todavia esta corriendo cuando
# toca el proximo disparo, Windows lo salta en vez de arrancar una segunda instancia en
# paralelo (complementa el lock de un solo proceso en lock.py, que cubre ademas el caso de
# que el dashboard Gradio dispare un backfill manual mientras la tarea programada corre).
#
# Correr una sola vez, a mano (no lo ejecuta el agente):
#   powershell -ExecutionPolicy Bypass -File register_tasks.ps1
# Para desregistrar:
#   Unregister-ScheduledTask -TaskName "ANA_Backfill_Download" -Confirm:$false
#   Unregister-ScheduledTask -TaskName "ANA_Backfill_Sync" -Confirm:$false

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)

# --- Descarga: cada 4 horas, indefinidamente ---
$DownloadAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\run_backfill_task.ps1`""
$DownloadTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 4) -RepetitionDuration ([TimeSpan]::MaxValue)

Register-ScheduledTask -TaskName "ANA_Backfill_Download" `
    -Action $DownloadAction -Trigger $DownloadTrigger -Settings $Settings `
    -Description "Backfill historico ANA (nivel + lluvia) en tandas de 10 ventanas, resumible via historic_backfill_state.json." `
    -Force

# --- Sync: 08:00 y 20:00 ---
$SyncAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\sync_task.ps1`""
$SyncTrigger1 = New-ScheduledTaskTrigger -Daily -At "08:00"
$SyncTrigger2 = New-ScheduledTaskTrigger -Daily -At "20:00"

Register-ScheduledTask -TaskName "ANA_Backfill_Sync" `
    -Action $SyncAction -Trigger @($SyncTrigger1, $SyncTrigger2) -Settings $Settings `
    -Description "Sube los JSON del backfill historico ANA al Volume de Databricks, 2 veces al dia." `
    -Force

Write-Host "Tareas registradas: ANA_Backfill_Download (cada 4hs), ANA_Backfill_Sync (08:00 y 20:00)."
Write-Host "Revisar/administrar desde el Programador de tareas de Windows (taskschd.msc)."
