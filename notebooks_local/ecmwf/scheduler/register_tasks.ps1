# Registra la tarea programada de Windows para el backfill historico local de TIGGE (cf+pf),
# mismo patron que notebooks_local/ana_historic_backfill/scheduler/register_tasks.ps1.
#
# TIGGE_Backfill_Download: corre run_backfill_task.ps1 (corrida CONTINUA: cf completo, despues
# pf completo, sync periodico interno) y se redispara cada 1 hora solo para retomar si la
# corrida anterior se corto (ExecutionTimeLimit de 6h, reinicio de PC, etc).
#
# No hace falta una tarea de sync separada (a diferencia de ANA): run_tigge_backfill.py ya
# sincroniza cada --sync-every-calls llamadas dentro de la misma corrida.
#
# MultipleInstances=IgnoreNew: si la corrida anterior todavia esta viva cuando toca el
# proximo disparo horario, Windows lo saltea en vez de arrancar una segunda instancia en
# paralelo (complementa tigge_lock.py, que cubre ademas el caso de un lanzamiento manual
# mientras la tarea programada corre).
#
# Correr una sola vez, a mano (no lo ejecuta el agente):
#   powershell -ExecutionPolicy Bypass -File register_tasks.ps1
# Para desregistrar:
#   Unregister-ScheduledTask -TaskName "TIGGE_Backfill_Download" -Confirm:$false

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot

# ExecutionTimeLimit de 6h: backstop contra una corrida colgada. No es un problema para la
# corrida continua: cada lote aterrizado queda marcado por la presencia de su JSON en disco,
# asi que si Windows mata la corrida a las 6h se pierde a lo sumo el lote en curso (se vuelve
# a pedir en el proximo disparo, sin corromper nada -- la escritura a disco solo pasa despues
# de que cdsapi.retrieve() devuelve con exito).
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)

$DownloadAction = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptDir\run_backfill_task.ps1`""
$DownloadTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName "TIGGE_Backfill_Download" `
    -Action $DownloadAction -Trigger $DownloadTrigger -Settings $Settings `
    -Description "Backfill historico local de TIGGE cf+pf, corrida continua resumible (redisparo horario para retomar si se corta)." `
    -Force

Write-Host "Tarea registrada: TIGGE_Backfill_Download (corrida continua, redisparo 1h)."
Write-Host "Revisar/administrar desde el Programador de tareas de Windows (taskschd.msc)."
