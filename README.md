# Automation Cobros - Fase 1

Base de automatizacion para el proyecto de COSTOS/Cobros.

## Alcance actual

- Consulta `dbo.F_COMPRAS(proveedor, fecha_inicial, fecha_final)` en SQL Server.
- Genera archivo `Compras` en Excel con formato y hoja de pendientes EDI.
- Permite que el auditor edite el Excel manualmente.
- Recalcula los campos de auditoria:
  - `cto_aud`
  - `iva_aud`
  - `ieps_aud`
  - `imp_aud`
  - `debio_pagar_ne`
  - `dif_det_ne`
  - `debio_pagar_inv`
  - `tot_pagado_inv`
  - `dif_det_inv`
- Genera el archivo `Validacion de Condiciones` con hojas:
  - `Resumen`
  - `Consolidado`
  - `Detalle PAGOS`

## Ejecucion

```powershell
python main.py
```

Tambien se puede ejecutar por consola:

```powershell
python main.py extract --vendor 885 --start 2020-01-01 --end 2025-01-01 --output outputs\Compras_885.xlsx
python main.py recalc --input outputs\Compras_885.xlsx --output outputs\Compras_885_Recalculado.xlsx
python main.py validate --input outputs\Compras_885_Recalculado.xlsx --output outputs\Validacion_885.xlsx
```

## CPA Vision - fase inicial

La automatizacion web se inicia con Playwright. Primero instala el navegador:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Abrir CPA Vision, iniciar sesion manualmente y capturar descargas CSV:

```powershell
python main.py cpa-session --download-dir outputs\cpa_vision --browser-channel msedge
```

El comando guarda la sesion en `logs\cpavision_state.json`. En la siguiente ejecucion
intentara reutilizarla.

Listar los CSV descargados:

```powershell
python main.py cpa-csvs --download-dir outputs\cpa_vision
```

Consolidar el ZIP descargado de CPA Vision en un solo Excel:

```powershell
python main.py cpa-consolidate --input "outputs\cpa_vision\archivo.zip" --output "outputs\cpa_vision\Consolidado_CPA.xlsx"
```

Tambien se puede pasar una carpeta para consolidar todos los ZIP que contenga:

```powershell
python main.py cpa-consolidate --input "outputs\cpa_vision" --output "outputs\cpa_vision\Consolidado_CPA.xlsx"
```

Iniciar sesion automaticamente y dejar el navegador en la pantalla
`Descarga masiva de archivos` con la seleccion base:

```powershell
$env:CPA_VISION_USER = "usuario@empresa.com"
$env:CPA_VISION_PASSWORD = "password"
python main.py cpa-downloads-page --download-dir outputs\cpa_vision --browser-channel msedge
```

La seleccion base deja `EMITIDOS` vacio y marca solo `RECIBIDOS`,
`Vigentes`, `Ingreso`, `11810 - TIENDAS SORIANA`, anos `2020` a `2024` y
`Hoja de cálculo con detalle de conceptos y Tasas (.csv)`.
Tambien marca `Generar acumulado`.

Para solicitar la descarga, esperar la solicitud y descargar el ZIP:

```powershell
$env:CPA_VISION_USER = "usuario@empresa.com"
$env:CPA_VISION_PASSWORD = "password"
python main.py cpa-request-download --rfc "RFC_DEL_PROVEEDOR" --download-dir outputs\cpa_vision --browser-channel msedge
```

Este flujo deja `EMITIDOS` vacio, marca solo recibidos con `Vigentes`,
`Ingreso`, anos `2020` a `2024`, captura el RFC en la seccion `RECIBIDOS`,
selecciona `Hoja de cálculo con detalle de conceptos y Tasas (.csv)`,
marca `Generar acumulado`,
envia la solicitud, selecciona `Conciliacion` y `Unica vez`, abre
`Solicitudes`, refresca cada 20 segundos y descarga el ZIP cuando el link
este disponible.

Opciones utiles:

```powershell
python main.py cpa-request-download --rfc "RFC_DEL_PROVEEDOR" --start-year 2020 --end-year 2024 --poll-seconds 20 --max-wait-minutes 30
```

Para solo abrir la pagina sin marcar opciones:

```powershell
python main.py cpa-downloads-page --download-dir outputs\cpa_vision --skip-config
```

Si no se configura `CPA_VISION_PASSWORD`, el comando la pide por consola.

## Configuracion

La conexion esta en `config.py` y usa estos valores por defecto:

```text
DRIVER={ODBC Driver 18 for SQL Server}
SERVER=ATL20AF2222SQ19
DATABASE=SORIANA_PROJECTS
Trusted_Connection=yes
TrustServerCertificate=yes
```

Se puede cambiar sin editar codigo usando variables de entorno:

```powershell
$env:COBROS_DB_SERVER = "ATL20AF2222SQ19"
$env:COBROS_DB_NAME = "SORIANA_PROJECTS"
```

Variables opcionales para CPA Vision:

```powershell
$env:CPA_VISION_URL = "https://cpavision.mx/"
$env:CPA_VISION_DOWNLOAD_DIR = "outputs\cpa_vision"
$env:CPA_VISION_STATE_PATH = "logs\cpavision_state.json"
$env:CPA_VISION_BROWSER_CHANNEL = "msedge"
$env:CPA_VISION_USER = "usuario@empresa.com"
$env:CPA_VISION_PASSWORD = "password"
$env:CPA_VISION_RFC = "RFC_DEL_PROVEEDOR"
```

## Flujo recomendado para el auditor

1. Abrir la app con `python main.py`.
2. Capturar proveedor y rango de fechas.
3. Ejecutar `Generar Compras preliminar`.
4. Abrir el Excel generado y completar manualmente los campos EDI pendientes.
5. Guardar el archivo.
6. Ejecutar `Recalcular Compras editado`.
7. Ejecutar `Generar Validacion`.

## Regla de salida para Validacion

Si la columna `concepto` viene clasificada, el archivo de validacion toma solo los folios con `concepto = dif costos`.
Si `concepto` esta vacio, usa como criterio preliminar `dif_det_ne > 1`.

La regla exacta que separa `dif costos`, `sin diferencia`, `sobrepago` y casos cruzados de 2023 debe cerrarse con ejemplos adicionales antes de considerar terminada la fase de negocio.

## Generar EXE

Cuando se quiera distribuir:

```powershell
.\build_exe.ps1
```

El ejecutable quedara en `dist\AutomationCobros.exe`.
