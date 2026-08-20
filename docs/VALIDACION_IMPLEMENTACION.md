# Implementación de la Validación de Condiciones

> **Cómo se construye el entregable**, hoja por hoja y filtro por filtro.
> Documento hermano de [CRUCE_IMPLEMENTACION.md](CRUCE_IMPLEMENTACION.md): allí está cómo se
> **llena** el Compras; aquí, cómo de ese Compras sale la **Validación**, que es el
> entregable real que ve el cliente.
>
> Las **reglas de negocio** (por qué, no cómo) viven en
> [LOGICA_NEGOCIO.md](LOGICA_NEGOCIO.md). Este archivo describe el código.
>
> **Creado:** 2026-08-18 · Código: [`validation_exporter.py`](../automation_costos/validation_exporter.py)

---

## 1. Dónde encaja en el pipeline

`pipeline.generar_salida_proveedor()` encadena todo en memoria, sin archivos intermedios:

```
SQL Server  ──►  recorte de años  ──►  cruce CPA  ──►  recálculo  ──┐
(F_COMPRAS)      (--anios)           (cruce_cpa)     (calculations) │
                                                                    ▼
                          soportes ZIP  ◄──  Compras  ◄──  VALIDACIÓN
                          (si hubo cruce)   (referencia)   (el entregable)
```

**La Validación se escribe ANTES que el Compras**, a propósito ([pipeline.py](../automation_costos/pipeline.py)):
es el entregable real y es chica, así que sale aunque el Compras gigante falle. Además
trabaja sobre el DataFrame **antes** de que el exportador de Compras le aplique valores de
fórmula en sitio.

## 2. Las cuatro hojas

| Hoja | Contenido | Nivel |
|---|---|---|
| **Resumen** | Una celda: la suma de diferencias + "Observaciones Auditor" | Proveedor |
| **Consolidado** | Un renglón **por folio** con lo pagado, lo que debió pagarse y la diferencia | Folio |
| **Ajustes** | Devoluciones MR8M/KG-14 que anularon diferencias. *Solo si las hay* | Devolución |
| **Detalle PAGOS** | Un renglón **por artículo** de los folios que entraron al Consolidado | Renglón |

Los dos niveles (folio y renglón) son la regla de negocio de
[LOGICA_NEGOCIO §4](LOGICA_NEGOCIO.md); aquí solo se materializan.

Todas llevan el mismo encabezado: logo de Soriana, razón social, `<número> - <nombre>` del
proveedor y **`Validacion de Condiciones - Periodo <años>`** (ver §6).

## 3. Qué folios entran — el filtro que define el entregable

`build_consolidado()` no lleva todos los folios: solo los que **califican**. La regla tiene
dos caminos y los elige `_has_audit_concepts()`:

| Caso | Condición | Qué entra |
|---|---|---|
| **Con clasificación del auditor** | la columna `concepto` trae alguno de `dif costos`, `sin diferencia`, `sobrepago`, `faltante` | los folios con **al menos un renglón** `dif costos` |
| **Sin clasificación** | `concepto` viene vacío | los folios cuya `dif_det_ne` supere el **umbral** |

El umbral es `config.VALIDATION_DIFFERENCE_THRESHOLD` = **1 peso**.

> ⚠️ **Ese umbral sigue pendiente de decidir con negocio.** En Celaya produjo 26,326 folios
> con mediana de diferencia de **$6.86** y primer cuartil de **$2.48**: la mayoría son
> centavos de redondeo. Ver [ESTADO_ACTUAL.md](ESTADO_ACTUAL.md).

**Por qué es un prefiltro vectorizado y no un bucle:** `_folios_que_califican()` devuelve una
máscara y descarta **antes** de agrupar. Recorrer los ~100k folios de un proveedor grande uno
por uno en Python para tirar el 99 % era el paso lento de la Validación.

### Renglones sin nota de entrada

No son auditables y quedan fuera desde el pipeline, no aquí
([LOGICA_NEGOCIO §5.1](LOGICA_NEGOCIO.md)). El folio se arma con
`make_folio_series(strnbr, rcvnbr)` = prefijo + tienda(4) + nota(8).

## 4. Los ajustes de pagos (MR8M / KG-14)

`aplicar_ajustes_a_consolidado()` cruza las devoluciones del proveedor y las descuenta. Es
lo que evita reclamar algo que el proveedor **ya devolvió**.

- **MR8M** → liga por **proveedor + factura**.
- **KG-14** → liga por **nota de entrada + tienda** (el folio exacto).
- **Compensada** (`ChkNbr` con valor): se **consume** contra la diferencia disponible, sin
  dejarla bajo cero. Una factura con varios folios reparte en cascada, sin descontar de más.
- **No compensada** (`ChkNbr` vacío): **no** resta; marca la bandera y suma el pendiente.

Los folios que la devolución deja en ~0 **desaparecen** del Consolidado y quedan en la hoja
"Ajustes". El Consolidado pasa entonces de 15 a 21 columnas (`CONSOLIDADO_COLUMNS_AJUSTES`).

Es **no-op y no-fatal**: si el proveedor no tiene devoluciones, o si la BD no responde, la
Validación se genera igual con las 15 columnas de siempre.

> El corte de la consulta de devoluciones es **31-mar-2026**. Estuvo en 31-dic-2025 y se
> perdían todas las devoluciones de 2026 — ver el bug del 2026-08-13 en
> [BITACORA.md](BITACORA.md) y [LOGICA_NEGOCIO §11](LOGICA_NEGOCIO.md).

## 5. Tres motores para el mismo contenido

El tamaño del proveedor decide el camino. **El contenido es el mismo**; cambia cómo se
escribe.

| Función | Motor | Cuándo | Títulos |
|---|---|---|---|
| `write_validation_from_dataframe` | openpyxl | camino normal | ✅ las 4 hojas |
| `write_validation_rapida` | xlsxwriter | proveedores grandes, detalle en memoria | ❌ sin títulos |
| `write_validation_streaming` | xlsxwriter | gigantes: detalle por chunks (trimestres) | ✅ las 4 hojas |

- **openpyxl** materializa el libro completo en memoria: cómodo, con formato fino, pero se
  ahoga con millones de renglones.
- **xlsxwriter con `constant_memory`** escribe fila por fila y no acumula. Exige escribir
  **en orden de filas**, y de ahí que el título (filas 2-4) se pinte antes que los datos.
- **`write_validation_streaming`** nunca materializa el detalle: recibe un iterable de
  chunks, transforma cada uno con `build_detalle_rapido()` y lo escribe de inmediato. Es el
  camino con el que salieron Arca (11.5 M) y Pepsico (10.1 M), con pico de RAM ~5 GB.

> `build_detalle_rapido()` es la versión vectorizada de `build_detalle()`. Mismo resultado,
> sin el bucle por renglón.

Solo se copian al Compras las **32 columnas** de `_COLUMNAS_FUENTE`, no las 95 del
entregable: eso es lo que hace viable a los proveedores de más de un millón de renglones.

## 6. El periodo en el título (2026-08-18)

La tercera línea del título dice qué periodo se auditó:

```
Validacion de Condiciones - Periodo 2020-2025
Validacion de Condiciones - Periodo 2020, 2022, 2025
```

Guion si los años son **consecutivos**; con huecos se **listan todos**. Lo produce
`utils.formatear_periodo()`.

**El periodo se deriva de los renglones que quedaron** (`rcvdt`), no del rango pedido a SQL.
Un "2020-2025" en un entregable al que le falta 2022 se leería como que ese año se revisó y
no tuvo diferencias, cuando ni se miró. Ver [LOGICA_NEGOCIO §13.2](LOGICA_NEGOCIO.md).

Quien llama puede pasar el periodo explícito (`periodo=`); si no, se deriva del DataFrame.
En el camino gigante el explícito **manda**, porque ahí el `df` es solo el primer trozo.

## 7. Efectos colaterales al terminar

Cada proveedor terminado dispara dos cosas, ambas **no-fatales**:

1. `actualizar_reporte_consolidado()` → refresca `Reporte_Diferencias_Consolidado.xlsx` en la
   raíz de entregables (el archivo de control de Héctor) y anota en
   `Historico_Diferencias.parquet`.
2. `copiar_soportes_cpa()` → copia los ZIP de CPA Vision a `cpa vision soportes/`,
   **solo si hubo cruce**. Sin cruce no se copian: el entregable no se apoya en ningún CFDI y
   los ZIP sugerirían lo contrario.

## 8. Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Construcción de las hojas | [`validation_exporter.py`](../automation_costos/validation_exporter.py) |
| Devoluciones MR8M/KG-14 | [`ajustes_pagos.py`](../automation_costos/ajustes_pagos.py) |
| Encadenado del pipeline | [`pipeline.py`](../automation_costos/pipeline.py) |
| Camino de gigantes | [`pipeline_streaming.py`](../automation_costos/pipeline_streaming.py) |
| Regla del costo auditado | [`calculations.py`](../automation_costos/calculations.py) |
| Relectura del Compras editado | [`recalculate.py`](../automation_costos/recalculate.py) |
| **Guía para el auditor** | `Guia_Validacion_Condiciones.docx` (la genera `scripts/generar_guia_validacion.py`) |

## 9. El flujo del auditor (por qué existe `validate`)

El auditor **corrige el Compras a mano** y regenera la Validación:

```bash
.venv/Scripts/python.exe main.py validate --input "Compras_<...>.xlsx"
```

`recalculate.read_compras_workbook()` relee el Excel editado, `calculations` recalcula y se
escribe la Validación otra vez. Ese subcomando **sí** actualiza el reporte consolidado; el
botón "Validar" de la GUI **no**, a propósito: escribe un archivo suelto fuera del árbol de
entregables.
