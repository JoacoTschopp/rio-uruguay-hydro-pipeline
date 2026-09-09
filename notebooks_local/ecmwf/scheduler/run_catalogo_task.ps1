# Revalidacion diaria del catalogo de descargas (Decision 046).
# Recorre discos + lista los volumenes de Databricks y reporta discrepancias.
# Solo lee: nunca borra ni sube nada.
#
# Se usa `cmd /c "... >> log 2>&1"` y NO la redireccion nativa de PowerShell: con
# $ErrorActionPreference="Stop", cualquier linea que el proceso hijo escriba en stderr
# (progreso, warnings del CLI) aborta la tarea aunque el proceso termine bien.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$Python   = "$RepoRoot\.venv\Scripts\python.exe"
$Script   = "$RepoRoot\notebooks_local\catalogo.py"
$Log      = "$RepoRoot\notebooks_local\catalogo_task.log"

"=== Revalidacion iniciada $(Get-Date -Format 'MM/dd/yyyy HH:mm:ss') ===" | Out-File -FilePath $Log -Append -Encoding utf8

cmd /c "`"$Python`" `"$Script`" revalidar >> `"$Log`" 2>&1"
exit 0
