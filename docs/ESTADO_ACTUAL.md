# Estado actual del proyecto

> **Última actualización:** 2026-08-15
> Actualizar este archivo al cerrar cada sesión de trabajo.

---

> ✅ **CERRADO (2026-08-15): el objetivo de cobertura <90 % de Mónica está descargado.**
> **397 de 398** pares proveedor-año. El único que falta es imposible por CPA Vision
> (ver *El caso IGU880227Q96* abajo). Ya no hay lotes de descarga pendientes.

> ✅ **CERRADO (2026-08-11): renombre Cobros → Costos completo.** La carpeta raíz ya es
> `Automation-Costos` y el checklist de validación de [BITACORA.md](BITACORA.md) pasó entero
> (CLI con sus 17 subcomandos, imports, `py_compile`, parquet con 350 RFC, renombres como `R`
> en git). Los artefactos `build/` y `dist/` se regeneraron con el nombre nuevo.
>
> El `.venv` heredado de la ruta vieja (con `pip.exe` y `pyinstaller.exe` rotos) **ya se
> recreó** el 2026-08-11 y quedó verificado. ⚠️ Al recrearlo, hacerlo siempre desde una
> terminal **sin el entorno activado**, o Windows bloquea `python.exe` y el entorno queda a
> medias — ver la entrada del 2026-08-11 en [BITACORA.md](BITACORA.md).

# 🎯 Dónde vamos ahora mismo

**La descarga terminó.** El objetivo de cobertura <90 % de Mónica (correo 2026-08-10,
[reunión 009](reuniones/009-2026-08-10-enfoque-cobertura-90-monica.md)) quedó cubierto.
El criterio nunca fue "todo el historial por prioridad": solo **proveedor+año con
`% poblado EDI` < 90 %**. El siguiente paso ya no es bajar datos, es **explotarlos**
(ver *Siguiente paso inmediato*).

## 📊 Corte al 2026-08-15 (medido contra el parquet, no contra CSV)

| Concepto | Valor |
|---|---:|
| Objetivo <90 % (`_objetivo_edi_menor_90.csv`) | **398** pares prov-año / **227** RFC |
| Ya en el acervo | **397** ✅ |
| **Faltan** | **1** — IGU880227Q96 2023, sin CFDI (ver abajo) |
| 🌎 Extranjeros sin RFC (imposible por CPA) | **17** proveedores |

Último lote (2026-08-15, `descarga_monica_pendientes.xlsx`, 24 proveedores / 44 pares):
**23 OK, 0 errores, 1 sin valores**, 19,596 filas nuevas en 1h 12m (3m 0s por proveedor).

### Las dos carpetas del acervo

| | RFC | Pares RFC-año | Conceptos | CFDI | Parquet |
|---|---:|---:|---:|---:|---:|
| `cpa_vision` (todo lo descargado) | **475** | 1,208 | 87,760,780 | 10,116,257 | 1.9 GB |
| `cpa_vision_complemento` (solo <90 %) | **227** | 397 | 7,122,851 | 613,748 | 140 MB |

Cada una lleva su propio `Inventario_CPA_Vision.xlsx`, y **ambas se actualizan solas al
cerrar cada lote** de descarga (`inventario_cpa` + `complemento_cpa`, procesos independientes
enganchados en `cpa_vision.py`). El complemento se llena **por copia** desde el general,
filtrando por `_objetivo_edi_menor_90.csv`: no se descarga dos veces.

> ⚠️ Por eso el lote **debe** correr con el `--download-dir` del acervo (es el default de
> `config`). Si se le pasa `outputs/cpa_vision`, los ZIP y el Parquet quedan dentro del repo
> y el acervo y su inventario quedan incompletos.

**Tiempos acumulados** (29 archivos `cpa_batch_metrics_*.csv`, 530 intentos): 212.6 h de
reloj, media **7m 52s** por proveedor, **407** proveedores únicos OK, 8,984,523 filas.

### El caso IGU880227Q96 — reportar a Mónica

**INDUSTRIAS GUACAMAYA SA DE CV (44586), año 2023.** CPA Vision procesa la solicitud y
devuelve estatus **"Sin valores"**: no existe ni un CFDI de ese RFC recibido por Soriana en
2023. **No es un fallo técnico y no se arregla reintentando** — se verificó dos veces
(2026-08-14 y 2026-08-15). Va en la misma canasta que los 17 extranjeros sin RFC: un
proveedor-año del objetivo que CPA Vision no puede cubrir porque no hay comprobantes.

Desde el 2026-08-15 el lote **detecta ese estatus y salta al siguiente proveedor** en vez de
gastar los 2 intentos y los `max_wait_minutes` completos (`SolicitudSinValores`). Aparece en
el resumen como *"Sin valores (saltados)"*, aparte de los errores.

> ⚠️ **`downloaded_after_recovery` es una descarga BUENA** (tropezó y el reintento la
> completó). Hasta el 2026-08-15 los dos resúmenes la contaban como error — por eso
> `METRICAS_TOTALES.txt` reportaba 76.5 % de éxito. Corregido con `_ESTATUS_OK`.

## 📈 Indicador de beneficio por año (pedido de Mónica)

`scripts/beneficio_cpa.py` (cobertura antes/después por proveedor-año) y
`scripts/actualizar_plan_beneficio.py`, que vuelca el "después" sobre el archivo de Mónica
respetando su estructura → **`Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx`** con
`edi_despues`, `pct_despues`, `mejora_pp`, `renglones_ganados`. Corrida 2026-08-11:
**1,781 de 4,202** filas prov-año con beneficio calculado (312 proveedores); el resto queda
en blanco porque esos proveedores todavía no se descargan.

## Los 6 urgentes (histórico — cerrados el 2026-07-27)

| Proveedor | Nombre | Renglones | Compras + Validación |
|---|---|---:|---|
| **741** | SELECTA DEL CAMPO | 58,558 | ✅ **entregado** (2020–2025) |
| **73692** | EMPACADORA CELAYA | 1,244,498 | ✅ **entregado** |
| **5462** | MARCAS NESTLÉ | ~1.3M | ✅ **entregado** |
| **80622** | 3M MEXICO (solo 2025) | 25 mil | ✅ **entregado** |
| **391250** | DISTRIBUIDORA ARCA CONTINENTAL | 11.5M | ✅ **Validación** · 157,433 folios · $170.6M |
| **76034** | COMERCIALIZADORA PEPSICO | 10.1M | ✅ **Validación** · 123,742 folios · $160.6M |

> ✅ **LOS 6 URGENTES CERRADOS (2026-07-27).** Arca y Pepsico se entregaron con **solo la
> Validación** (camino ligero `generar_validacion_grande`; sin los Compras gigantes). Clave
> del éxito: filtrar la CPA por **factura** además de código de barra (Pepsico bajó de 9 GB
> a 2.7 GB por trimestre) — verificado que **no cambia ningún resultado**. Cada gigante en
> su **proceso propio**. El Detalle se parte en varias hojas (Arca 4.29M, Pepsico 1.92M).

### Generar los Compras de los gigantes (pendiente, 2026-07-28)

La Validación de Arca/Pepsico ya está. Faltan sus **archivos de Compras** (referencia). Se
generan aparte, por trimestre, con el subcomando `cpa-compras-grande` — **resumible** (salta
los trimestres cuyo archivo ya existe, sin re-consultar SQL). No escribe Validación, así que
no acumula en RAM: pico ~5.5 GB por trimestre. Un trimestre tarda ~5 min (16 trimestres ≈ 1.5 h).

**Arca** (ya tiene 2020-2021; esto genera 2022-2025):
```bash
.venv/Scripts/python.exe main.py cpa-compras-grande --vendor 391250 \
    --start 2020-01-01 --end 2025-12-31 \
    --parquet outputs/cpa_vision/parquet --output-dir outputs
```

**Pepsico** (no tiene ninguno; si un trimestre no cupiera, agregar `--por-mes`):
```bash
.venv/Scripts/python.exe main.py cpa-compras-grande --vendor 76034 \
    --start 2020-01-01 --end 2025-12-31 \
    --parquet outputs/cpa_vision/parquet --output-dir outputs
```

- **Si se corta a media ejecución** (memoria, energía, lo que sea): **volver a correr el
  mismo comando** — continúa desde donde quedó (salta lo ya escrito).
- Los totales por folio del Compras son **por trimestre** (los ~0.3% de folios que cruzan
  trimestre difieren del global; el número exacto de auditoría vive en la **Validación**).
- Decisión de Óscar (2026-07-27/28): **Validación primero** (ya entregada); los Compras
  gigantes son referencia y se generan cuando haya máquina/tiempo, sin prisa.
- Arca ya tiene sus **24 Compras** (Óscar corrió `cpa-compras-grande` el 2026-07-28; funcionó).

## 📂 Dónde van los archivos (2026-07-29)

El share `X:/Soriana` se llenó por **duplicación**: los entregables estaban en `outputs/` del
proyecto **y** en la carpeta de auditores donde Óscar los pega para el equipo. **Decisión:**

- **Entregables** (Compras/Validación/soportes) → **directo a la carpeta de auditores**, con:
  ```
  --output-dir "X:/Soriana/00 - AUDITORIA 2020 - 2024/Proceso Validación de condiciones (Oscar Pineda)"
  ```
- **El proyecto `outputs/` solo guarda datos de trabajo**: `outputs/cpa_vision/` (ZIPs +
  Parquet, materia prima de los cruces) y `outputs/logs/`. **No borrar `cpa_vision`.**
- Se borraron del proyecto las 6 carpetas de proveedor (ya estaban en la carpeta de
  auditores) → liberó ~12.6 GB.
- Las **descargas** de CPA Vision siguen yendo a `outputs/cpa_vision` (`--download-dir`).

## 📥 Cómo se descarga hoy (modo Mónica)

El maestro es **`descarga_monica_pendientes.xlsx`** (lo genera `scripts/gen_lote_monica.py`:
una fila por proveedor, `FECHAS` = los años sueltos <90 %, ordenado por prioridad,
excluyendo lo que ya está en parquet). Se pagina con `--start-index`:

**No se le pasan rutas**: `--download-dir` y `--parquet-dir` traen `default=None` y caen en
`config`, que ya apunta al acervo. Escribirlas a mano es la forma de equivocarse.

```powershell
.\.venv\Scripts\python.exe main.py cpa-batch-vendors --input descarga_monica_pendientes.xlsx --start-index 0 --batch-size 50 --user '<USUARIO_CPA>' --password '<PASSWORD_CPA>' --browser-channel msedge
```

> ⚠️ **La terminal del proyecto es PowerShell.** Va todo en **una sola línea**: `\` no
> continúa línea en PowerShell (el carácter es el backtick `` ` ``). Comillas **simples** en
> la contraseña: las dobles interpolan `$`.

> ⚠️ **No regenerar el maestro a media paginación**: `gen_lote_monica.py` reordena y
> reindexa el archivo, y `--start-index` dejaría de apuntar a donde iba.

**Si un lote se corta a media corrida** (reinicio, corte de energía): los ZIP y el Parquet ya
descargados **sí** quedan en el acervo, pero el inventario y el complemento **no**, porque su
enganche corre al *cerrar* el lote. Se ponen al día sin re-descargar nada:

```powershell
.\.venv\Scripts\python.exe scripts/complemento_cpa.py
```

Para saber dónde retomar, el `cpa_batch_metrics_*.csv` del lote trae la columna `excel_row`:
el `--start-index` es esa fila **menos 2**.

> El criterio anterior (59 prioritarios del master, col X) quedó **superado** por el enfoque
> <90 %. Los lotes `descarga_prioritarios_lote*.xlsx` se borraron el 2026-08-10.

**Arca y Pepsico (2026-07-27):** procesar un año/trimestre completo con los Compras agotaba
la RAM (11.5M compras + 2.9M CPA; además acumulaba en RAM las filas con diferencia). Se
midió que marcan hasta **42 % de folios con diferencia** (hallazgos reales donde el CFDI <
sistema). **Decisión de Óscar: Validación primero** (el entregable), Compras después.

Corren con `scripts/correr_validaciones_grandes.py` →
`pipeline_streaming.generar_validacion_grande`: **una pasada por trimestre**, solo renglones
**auditables** (con nota de entrada; ver LOGICA_NEGOCIO §5.1), vuelca a disco (no acumula),
y escribe la Validación con **motor rápido** (`write_validation_rapida`, xlsxwriter, aguanta
millones). Pico de RAM ~5 GB. **NO** escribe el Compras. Verificado idéntico al camino
normal en Selecta. Los ~8 Compras de Arca (2020-2021) del intento anterior quedan en disco.

**Pendiente cuando estén los resultados:** decidir con Mónica/Luis si el ~42 % de
diferencias es real o si el umbral de 1 peso marca ruido (pendiente viejo del §5). Y si se
quieren los Compras por trimestre de Arca/Pepsico.

## Dos caminos según el tamaño (2026-07-27)

`generar_salida_proveedor` hace un `COUNT` barato y elige:
- **≤ 2.5M renglones:** camino normal, todo en memoria (rápido). Ej. Selecta, Celaya, Nestlé.
  → un `Compras_<base>.xlsx` (o por año si es grande) + Validación.
- **> 2.5M:** **procesamiento por trimestre** ([pipeline_streaming.py](../automation_costos/pipeline_streaming.py)),
  para no agotar la RAM (un año no cabe: 1.6M compras + 2.9M CPA). Ej. Arca (11.5M), Pepsico
  (10.1M). → un `Compras_<base>_<año>-T<n>.xlsx` **por trimestre** (~24) + **una** Validación
  consolidada. Da resultados **idénticos** al camino normal (verificado con Selecta y Nestlé).
  Ver [RENDIMIENTO_EXPORTADOR.md](RENDIMIENTO_EXPORTADOR.md) §6c.

## El comando que produce el entregable

```bash
.venv/Scripts/python.exe main.py cpa-salida \
    --vendor 73692 --start 2020-01-01 --end 2025-12-31 \
    --parquet outputs/cpa_vision/parquet --output-dir outputs
```

> ⚠️ **Siempre con `.venv/Scripts/python.exe`**, nunca con el Python global: el del venv es
> el que tiene xlsxwriter, duckdb y customtkinter.

Encadena en memoria: SQL → cruce CPA Vision → recálculo → **Validación** → **Compras** →
copia de **soportes**. También está como botón *"Generar salida completa (1 clic)"* en la
ETAPA 2 de la GUI.

### Estructura de salida (estandarizada 2026-07-24)

Cada proveedor es un paquete autocontenido:

```
outputs/
  <numero>_<nombre>/                       ej. 741_SELECTA DEL CAMPO SA DE CV/
    Compras_<numero>_<nombre>.xlsx         (proveedor chico: 1 archivo, hojas por año)
    Validacion_<numero>_<nombre>.xlsx      SIEMPRE 1 solo archivo (el entregable real)
    cpa vision soportes/
      <request_id>_..._1.zip               los ZIP de CPA Vision que respaldan la salida
```

**Compras chico vs. grande** (umbral `UMBRAL_PARTIR_POR_ANIO` = 1,000,000 filas):
- **Chico:** un solo `Compras_<base>.xlsx` con una hoja por año (`Compras 2020`, …).
- **Grande** (Arca, Pepsico): **un archivo por año**, cada uno con su `Pendientes_EDI`:
  ```
    Compras_<base>_2020.xlsx
    Compras_<base>_2021.xlsx
    ...
    Compras_<base>_2025.xlsx
  ```
  Se corta en límites de año, así una nota de entrada no queda partida y **no cambia
  ningún cálculo**. La Validación sigue siendo **un solo archivo**.

El pipeline crea la carpeta y copia los ZIP solo, tomando **el request que alimentó el
cruce** (para Pepsico/Nestlé, que tienen dos descargas, copia solo la completa). La copia
es idempotente y no-fatal: si falta el ZIP, avisa pero no tumba el entregable.

---

## Etapa A — Pipeline SQL Server → Excel

**Estado: funcionando.** `fetch_compras()` → `dbo.F_COMPRAS(proveedor, fecha_ini, fecha_fin)`
en `ATL20AF2222SQ19` con Trusted_Connection. **Toda la lógica de joins vive en SQL Server.**

`F_COMPRAS` está en **dos bases partidas por año** y `fetch_compras` las une sola:

| Base | Periodo que se le pide |
|---|---|
| `SORIANA_PROJECTS` | 2020–2024 |
| `SORIANA_2025_PROJECTS` | 2025 |

> ⚠️ `SORIANA_2025_PROJECTS` **también contiene 2022-2024, pero incompletos** (Óscar,
> 2026-07-24). De esa base se toma **solo 2025**; todo lo anterior sale de
> `SORIANA_PROJECTS`. **No ampliar el rango de `FUENTES_COMPRAS`**: además de duplicar
> renglones, metería datos parciales. Ver LOGICA_NEGOCIO.md R25.

**Pendiente funcional:** cerrar con negocio la regla que separa
`dif costos` / `sin diferencia` / `sobrepago` / `faltante` (ver LOGICA_NEGOCIO.md §5).

## Etapa B — Extracción masiva de CFDI desde CPA Vision

**Estado: TERMINADA. 475 RFC descargados; el objetivo <90 % quedó en 397/398.** Playwright +
msedge contra `cpavision.mx`.

- Dataset en `<acervo>/cpa_vision/parquet`, particionado Hive `rfc=/year=/request_id=`,
  consultable con DuckDB. **Es la fuente de verdad del avance** (los CSV mienten).
- Tiempos medidos: media 7m 52s por proveedor sobre 530 intentos (ver el corte arriba).

### Problemas abiertos de la Etapa B

**1. Duplicación de 2025.** `CPM110719SG3` (Pepsico) y `MNE0409226K9` (Nestlé) tienen dos
`request_id` cada uno (2020-2025 + solo 2025), con **2,331,088 filas duplicadas**.
`cargar_cpa` ya deduplica en DuckDB quedándose con el request más completo, así que el
cruce no se ve afectado — pero **conviene deduplicar el vendor master** antes de seguir.

**2. Basura recuperable** en `outputs/cpa_vision/parquet_test/`.

## El puente A ↔ B

**✅ Implementado.** `cruce_cpa.py` llena el bloque EDI del Compras con los CFDI del
Parquet. Llave: serie+folio de factura y código de barras. **Solo rellena celdas vacías**,
nunca pisa un dato que Compras ya traía. Ver [CRUCE_IMPLEMENTACION.md](CRUCE_IMPLEMENTACION.md).

---

## 🔴 Lo que hay que revisar con negocio

**El umbral de la Validación es demasiado bajo para proveedores grandes.**
Celaya produjo un Consolidado de **26,326 folios** y un Detalle de **322,294 filas**
(archivo de 41 MB). Pero la **mediana de la diferencia es de $6.86** y el primer cuartil
es de **$2.48**: la enorme mayoría son centavos de redondeo, no cobros reales.

- Suma total de diferencias: **$6,292,572.70** sobre $292M pagados.
- Umbral actual: `config.VALIDATION_DIFFERENCE_THRESHOLD` = 1 peso.

**Decisión pendiente de Óscar / Mónica:** subir el umbral para proveedores grandes, o
dejarlo y que el auditor filtre. No se cambió nada por cuenta propia.

## Siguiente paso inmediato

- [x] ~~Descargar el objetivo <90 %~~ — **cerrado el 2026-08-15**, 397/398
- [ ] **Re-correr `actualizar_plan_beneficio.py`** ahora que el objetivo está completo, para
      que el archivo ACTUALIZADO de Mónica refleje el beneficio real de los 23 proveedores
      nuevos. Es el pendiente más inmediato
- [ ] Reportar a Mónica **IGU880227Q96 / 44586 año 2023**: sin CFDI en CPA Vision, no se
      puede cubrir (junto con los 17 extranjeros)
- [ ] Fase 3: copiar el parquet a la carpeta de Data Services
      `...\Proceso Validación de condiciones (Oscar Pineda)\cpa_vision`
- [ ] Confirmar con Mónica el caso **2020 de Selecta** (CFDIs bajados que no cruzan por
      barcode+factura: 8.5 % → 8.7 %)
- [ ] Reportar a Mónica los **17 extranjeros sin RFC** (`reporte_monica_extranjeros.xlsx`)
- [ ] Decidir el umbral de la Validación (arriba)
- [ ] Resolver **C13** (tasas literales) y **C14** (nivel factura vs. renglón)

## Fuera de alcance por ahora

- **Integración dentro de Audit Tools** (hueco C6). Aplazado por decisión de Óscar el
  2026-07-22. No retomar hasta nueva indicación.
