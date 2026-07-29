# correr_grandes_pendientes.ps1
# Corre los 2 urgentes GRANDES que faltan (Arca y Pepsico), uno tras otro.
# El pipeline detecta solo que son grandes (COUNT en SQL) y los procesa año por año.
# 3M y Nestlé ya quedaron en la corrida anterior, no se repiten.
#
# Uso:  powershell -ExecutionPolicy Bypass -File "scripts\correr_grandes_pendientes.ps1"

$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'

$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$py      = Join-Path $raiz '.venv\Scripts\python.exe'
$parquet = 'outputs\cpa_vision\parquet'
$outdir  = 'outputs'
$logdir  = 'outputs\logs'
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

$proveedores = @(
    @{ vendor = '391250'; start = '2020-01-01'; end = '2025-12-31'; nombre = 'ARCA CONTINENTAL' },
    @{ vendor = '76034';  start = '2020-01-01'; end = '2025-12-31'; nombre = 'PEPSICO MEXICO' }
)

$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$resumen = Join-Path $logdir "grandes_$stamp.resumen.txt"
function Anota($t) { $t | Tee-Object -FilePath $resumen -Append }

Anota "==================================================================="
Anota "  Grandes pendientes (por año)  -  inicio $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Anota "==================================================================="

foreach ($p in $proveedores) {
    $log = Join-Path $logdir "$($p.vendor)_$stamp.log"
    $t0  = Get-Date
    Anota ""
    Anota ">>> $($p.nombre) [$($p.vendor)]  $($p.start)..$($p.end)"
    Anota "    inicio $($t0.ToString('yyyy-MM-dd HH:mm:ss'))  ->  log: $log"

    & $py -u main.py cpa-salida --vendor $p.vendor --start $p.start --end $p.end `
        --parquet $parquet --output-dir $outdir *> $log
    $code = $LASTEXITCODE

    $dur    = (Get-Date) - $t0
    $estado = if ($code -eq 0) { 'OK' } else { "FALLO (exit $code)" }
    Anota "    $estado  -  duracion $($dur.ToString('hh\:mm\:ss'))"
}

Anota ""
Anota "  Fin  -  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  ·  resumen: $resumen"
