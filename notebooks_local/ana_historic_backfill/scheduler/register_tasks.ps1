# Registra las 2 tareas programadas de Windows para el backfill historico de ANA:
#   - ANA_Backfill_Download: corre run_backfill_task.ps1 (corrida CONTINUA, sin tope de
#     ventanas) y se redispara cada 1 hora solo para retomar si la corrida anterior se corto.
#   - ANA_Backfill_Sync: corre sync_task.ps1 (sube JSON al Volume de Databricks) cada 6 horas.
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

# ExecutionTimeLimit de 6h: backstop contra una corrida colgada (p. ej. ANA caida y todos
# los requests en timeout+retry sin avanzar). No es un problema para la corrida continua:
# run_backfill_local.py checkpointea el estado despues de CADA ventana, asi que si Windows
# mata la corrida al llegar a las 6h se pierde a lo sumo la ventana en curso y el proximo
# disparo horario retoma desde historic_backfill_state.json.
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)

# --- Descarga: corrida continua. El trigger se redispara cada 1 hora (por 10 anios,
# efectivamente indefinido; [TimeSpan]::MaxValue fue probado y rechazado por
# Register-ScheduledTask porque el XML de Task Scheduler tiene un limite de duracion menor
# al maximo de .NET). IgnoreNew hace que mientras la corrida sigue viva los disparos
# horarios sean no-op: solo sirven para retomar del state.json si la corrida anterior se
# corto (kill por el ExecutionTimeLimit de 6h, reinicio de PC o crash) ---
$DownloadAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\run_backfill_task.ps1`""
$DownloadTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "ANA_Backfill_Download" `
    -Action $DownloadAction -Trigger $DownloadTrigger -Settings $Settings `
    -Description "Backfill historico ANA (nivel + lluvia), corrida continua resumible via historic_backfill_state.json (redisparo horario para retomar si se corta)." `
    -Force

# --- Sync: cada 6 horas. Mas frecuente que antes (era 08:00 y 20:00) para subir menos MB
# por vez: sync() solo sube los JSON que aun no esten en el Volume, asi que cuanto mas
# seguido corre, menos se acumula entre corridas ---
$SyncAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\sync_task.ps1`""
$SyncTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 6) -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "ANA_Backfill_Sync" `
    -Action $SyncAction -Trigger $SyncTrigger -Settings $Settings `
    -Description "Sube los JSON del backfill historico ANA al Volume de Databricks, cada 6 horas." `
    -Force

Write-Host "Tareas registradas: ANA_Backfill_Download (corrida continua, redisparo 1h), ANA_Backfill_Sync (cada 6hs)."
Write-Host "Revisar/administrar desde el Programador de tareas de Windows (taskschd.msc)."
