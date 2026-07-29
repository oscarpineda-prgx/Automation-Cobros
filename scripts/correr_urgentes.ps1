# correr_urgentes.ps1
# Corre varios proveedores por el pipeline cpa-salida, uno tras otro.
# Cada proveedor es independiente: si uno falla, se registra y SIGUE con el siguiente.
# Pensado para dejarlo corriendo toda la noche.
#
# Uso:  powershell -ExecutionPolicy Bypass -File "scripts\correr_urgentes.ps1"

$ErrorActionPreference = 'Continue'
$env:PYTHONIOENCODING = 'utf-8'   # logs sin caracteres raros

# Raiz del proyecto = carpeta que contiene a 'scripts'
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$py      = Join-Path $raiz '.venv\Scripts\python.exe'
$parquet = 'outputs\cpa_vision\parquet'
$outdir  = 'outputs'
$logdir  = 'outputs\logs'
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

# --- Proveedores a correr (ordenados de menor a mayor). 80622 = 3M es solo 2025. ---
$proveedores = @(
    @{ vendor = '80622';  start = '2025-01-01'; end = '2025-12-31'; nombre = '3M MEXICO (solo 2025)' },
    @{ vendor = '5462';   start = '2020-01-01'; end = '2025-12-31'; nombre = 'MARCAS NESTLE' },
    @{ vendor = '391250'; start = '2020-01-01'; end = '2025-12-31'; nombre = 'ARCA CONTINENTAL' },
    @{ vendor = '76034';  start = '2020-01-01'; end = '2025-12-31'; nombre = 'PEPSICO MEXICO' }
)

$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$resumen = Join-Path $logdir "urgentes_$stamp.resumen.txt"

function Anota($texto) { $texto | Tee-Object -FilePath $resumen -Append }

Anota "==================================================================="
Anota "  Lote de proveedores  -  inicio $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
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
Anota "==================================================================="
Anota "  Lote terminado  -  fin $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Anota "  Resumen: $resumen"
Anota "==================================================================="
