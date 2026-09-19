<#
.SYNOPSIS
    Compila los manuscritos a PDF con latexmk (MiKTeX).

.DESCRIPTION
    1. Regenera manuscritos/comun/referencias.bib desde research/catalog/ (salvo -SinBib).
    2. Agrega manuscritos/comun/ a BIBINPUTS con ruta de Windows.
    3. Corre latexmk -pdf -outdir=build en el directorio de cada documento.

    Correr desde PowerShell, no desde Git Bash: MSYS reescribe BIBINPUTS a /c/... y el bibtex de
    MiKTeX no encuentra el .bib (Decision 049 de la rama feature/rio-search).

    latexmk necesita perl. Si no hay uno en el PATH se usa el que trae Git for Windows.

.EXAMPLE
    .\manuscritos\herramientas\compilar.ps1
    .\manuscritos\herramientas\compilar.ps1 -Documento tesis
    .\manuscritos\herramientas\compilar.ps1 -Documento plan-de-tesis -SinBib
    .\manuscritos\herramientas\compilar.ps1 -Documento anexo-relevamiento
    .\manuscritos\herramientas\compilar.ps1 -Limpiar
#>
param(
    [ValidateSet('plan-de-tesis', 'tesis', 'anexo-relevamiento', 'todos')]
    [string]$Documento = 'todos',
    [switch]$SinBib,
    [switch]$Limpiar
)

# 'Continue' y no 'Stop': en PowerShell 5.1 latexmk escribe avisos en stderr y con 'Stop' se cortaria
# la compilacion. Los fallos se detectan por $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
$manuscritos = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$raiz = (Resolve-Path (Join-Path $manuscritos '..')).Path
$comun = Join-Path $manuscritos 'comun'

$documentos = if ($Documento -eq 'todos') { @('plan-de-tesis', 'tesis', 'anexo-relevamiento') }
              else { @($Documento) }

if ($Limpiar) {
    foreach ($doc in $documentos) {
        $build = Join-Path (Join-Path $manuscritos $doc) 'build'
        if (Test-Path $build) { Remove-Item -Recurse -Force $build; "  borrado $build" }
    }
    return
}

if (-not $SinBib) {
    Push-Location $raiz
    try {
        uv run --no-project --with pyyaml python manuscritos/herramientas/exportar_bib.py
        if ($LASTEXITCODE -ne 0) { throw 'exportar_bib.py fallo' }
    } finally { Pop-Location }
}

if (-not (Get-Command perl -ErrorAction SilentlyContinue)) {
    $perlGit = 'C:\Program Files\Git\usr\bin'
    if (-not (Test-Path (Join-Path $perlGit 'perl.exe'))) {
        throw 'latexmk necesita perl y no se encontro ni en el PATH ni en Git for Windows'
    }
    # Al final del PATH: no tapa ningun ejecutable de Windows con los de MSYS.
    $env:PATH = "$env:PATH;$perlGit"
}

$env:BIBINPUTS = "$comun;$env:BIBINPUTS"

$fallidos = @()
foreach ($doc in $documentos) {
    $dir = Join-Path $manuscritos $doc
    Write-Host "== $doc" -ForegroundColor Cyan
    Push-Location $dir
    try {
        latexmk -pdf -silent -interaction=nonstopmode -halt-on-error -outdir=build main.tex | Out-Host
        if ($LASTEXITCODE -ne 0) { $fallidos += $doc; continue }
        $log = Get-Content (Join-Path $dir 'build\main.log') -Raw
        $avisos = @()
        if ($log -match 'Citation .* undefined') { $avisos += 'citas sin definir' }
        if ($log -match 'Reference .* undefined') { $avisos += 'referencias sin definir' }
        $pdf = Get-Item (Join-Path $dir 'build\main.pdf')
        $estado = if ($avisos) { "con avisos: $($avisos -join ', ')" } else { 'ok' }
        Write-Host "   $($pdf.FullName) ($([math]::Round($pdf.Length / 1KB)) KB) $estado"
    } finally { Pop-Location }
}

if ($fallidos) { throw "No compilaron: $($fallidos -join ', '). Ver build/main.log" }
