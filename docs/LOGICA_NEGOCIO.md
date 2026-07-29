# Lógica de negocio — Auditoría de Costos Soriana 2020–2024

> Fuente de verdad de reglas, criterios y definiciones de columnas.
> Toda regla que se acuerde en una reunión o en el chat se escribe aquí, con su fecha.
>
> **Última actualización:** 2026-07-22 10:53:41

---

## 1. El negocio en una frase

Soriana paga a proveedores contra **notas de entrada**. El costo que Soriana pagó (SAP) no
siempre coincide con el que el proveedor facturó (EDI/CFDI). La auditoría busca esas
**diferencias de costo para reclamarlas**.

## 2. El folio — llave de agrupación

`utils.make_folio()`:

```
folio = "11004" (prefijo configurable) + tienda a 4 dígitos + nota de entrada a 8 dígitos
      = 17 caracteres
```

Representa **una entrega física en una tienda**.

`concaten` es lo mismo **sin prefijo y sin ceros de relleno**; es la llave que se usa
dentro de las fórmulas de Excel.

## 3. Regla central del costo auditado

En `calculations.recalculate_dataframe()`:

```
cto_aud = ctonto_edi   si hay EDI y ctonto_edi < ctouni
        = ctouni       en cualquier otro caso
```

**Si el proveedor facturó un costo MENOR al de sistema, el correcto es el del proveedor.**
Es una regla conservadora: **solo corrige a la baja**, nunca al alza.

Las tasas (`iva_aud`, `ieps_aud`) salen del EDI si existe; si no, caen a las tasas SAP
de la tabla `T007S`.

```
imp_aud = cto_aud × can_rec × (1 + iva_aud) × (1 + ieps_aud)
```

## 4. Los dos niveles de agregación

Fuente frecuente de confusión. Son **dos cortes distintos del mismo dato**:

| Nivel | Llave | Debió pagar | Pagado | Columna de diferencia |
|---|---|---|---|---|
| Nota de entrada | `folio` | suma de `imp_aud` | **máx** de `paynetamt` | `dif_det_ne` |
| Factura | `vndnbr\|strnbr\|invnbr` | suma de `imp_aud` | **máx** de `paynetamt` | `dif_det_inv` |

```
diferencia = pagado − debió_pagar
```

**Diferencia positiva = se pagó de más = hay algo que cobrar.**

El "pagado" usa `max` y no `sum` porque el monto viene **repetido en cada renglón** del
folio. Es correcto cuando hay un solo pago por folio; **subestimaría si hubiera pagos
parciales múltiples** (riesgo conocido, no resuelto).

## 5. Filtro del entregable final

En `validation_exporter.build_consolidado()`:

- Si el auditor ya clasificó la columna `concepto` → toma solo `dif costos`.
- Si `concepto` está vacía → usa el criterio preliminar `dif_det_ne > 1`.

> ⚠️ **PENDIENTE FUNCIONAL ABIERTO.** La regla exacta que separa
> `dif costos` / `sin diferencia` / `sobrepago` / `faltante` **sigue sin cerrarse con
> negocio**. Es el principal pendiente de la Etapa A.

### 5.1 Renglones sin nota de entrada NO son auditables (2026-07-27)

La diferencia se calcula **por nota de entrada** (folio = tienda + `rcvnbr`). Un renglón
**sin nota de entrada (`rcvnbr` nulo)** no tiene folio: no se puede validar a ese nivel y
hoy caía en un folio degenerado (todos juntos) que **nunca supera el umbral**, así que
nunca entra al entregable.

Por eso, para el cálculo de la Validación de proveedores grandes se **excluyen** esos
renglones (`fetch_compras(..., filtro_filas="rcvnbr IS NOT NULL")`). **Verificado que no
cambia ni un resultado**: Selecta con y sin ellos da la misma Validación (188 folios, 1,119
detalle). En Arca/Pepsico son ~30 % de los renglones, y quitarlos es lo que hace que el
cálculo quepa en memoria. **No es un cambio de criterio de auditoría, es quitar lo que de
todos modos no producía hallazgo.**

## 6. Columnas clave

| Columna | Origen | Significado |
|---|---|---|
| `folio` | calculada | Llave de entrega física (ver §2) |
| `concaten` | calculada | Igual a `folio` sin prefijo ni padding; usada en Excel |
| `ctouni` | SAP | Costo unitario de sistema |
| `ctonto_edi` | EDI/CFDI | Costo unitario facturado por el proveedor |
| `cto_aud` | calculada | Costo auditado (ver §3) |
| `can_rec` | SAP | Cantidad recibida |
| `iva_aud` / `ieps_aud` | EDI o T007S | Tasas aplicadas al cálculo auditado |
| `imp_aud` | calculada | Importe auditado con impuestos |
| `paynetamt` | SAP | Importe neto pagado (repetido por renglón) |
| `dif_det_ne` | calculada | Diferencia a nivel nota de entrada |
| `dif_det_inv` | calculada | Diferencia a nivel factura |
| `concepto` | manual | Clasificación del auditor |
| `uuid` | CFDI | Folio fiscal del CFDI |
| `totfactura` | CFDI | Total de la factura |

## 7. El puente entre las dos etapas (no implementado)

La hoja **`Pendientes_EDI`** del Excel de la Etapa A lista los renglones **sin datos EDI**
(`uuid`, `ctonto_edi`, `totfactura`…). Eso es exactamente lo que la Etapa B (CPA Vision)
viene a llenar con los CFDI descargados.

**Ese enlace todavía no está implementado**: no existe código que cruce el Parquet de
CPA Vision contra el Excel de Compras.

## 8. Riesgos conocidos de implementación (verificados 2026-07-21, sin arreglar)

1. **VLOOKUP con límite duro.** La fórmula de `dpagar` fija el rango
   `impaud!$A$3:$B$4779` → máximo **4,777 folios únicos**, y
   `_write_impaud_helper_sheet` trunca la tabla auxiliar **en silencio**. Medido sobre
   `Compras_885`: 4,775 `concaten` únicos. **Margen de 2 folios.** Con un proveedor más
   grande, los sobrantes dan `#N/A` sin aviso. Debería calcularse dinámicamente.

2. **IVA clavado en `=0.16` dentro de Excel.** La fórmula de Excel usa esa tasa plana,
   pero Python usa las tasas reales `(1+iva_aud)*(1+ieps_aud)`. **En productos con IEPS o
   IVA distinto de 16% (frontera, tasa 0, exentos) el Excel y Python no coinciden.**

3. **El recálculo depende de abrir el archivo en Excel.** pandas lee con
   `data_only=True` y openpyxl escribe fórmulas **sin valor cacheado**. Si se corre
   `recalc` sobre un archivo que nunca pasó por Excel, esas 10 columnas se leen vacías.

## 9. Reglas acordadas en reuniones

<!-- Cada acuerdo que salga de una reunión se agrega aquí con fecha y enlace a la nota -->

### De la reunión 001 (2026-04-23) — [nota completa](reuniones/001-2026-04-23-proceso-compras-audit-tools.md)

**R1 — Se toma la mejor condición.** Se compara el costo facturado por el proveedor contra
el del sistema del cliente y se toma **el mejor costo y el impuesto correcto**.

**R2 — Impuesto en cero del cliente → gana la tasa del proveedor.**
> "Si el sistema del cliente trae el impuesto en cero y la factura del proveedor trae una
> tasa, se deja el impuesto del proveedor." (Mónica)

**R3 — El cruce EDI falla por código de barras.** La causa principal de campos EDI vacíos
es que el código de barras del proveedor no coincide con el registrado por el cliente.
También falla cuando simplemente falta la factura.

**R4 — Tres orígenes posibles de una diferencia:** faltante de mercancía · diferencial de
costo · impuestos. El **IEPS en vinos llega al 53%**.

**R5 — El entregable al proveedor tiene 3 pestañas:** total de la diferencia · consolidado
a nivel factura · detalle por artículo. Con **menos campos** que el archivo de compras: solo
lo necesario para que el proveedor valide. El "debió pagar" del consolidado **debe cuadrar
con la suma del detalle**.

**R6 — Dos fuentes para rellenar huecos EDI:** listas de precios que llegan por correo, y
el portal **CPA Vision / CFDI Visión**.

**Origen de la lógica de cálculo:** los campos `costo OUT`, `IVA OUT`, `IEPS OUT` fueron
generados **por el equipo de Data Services**, no por Audit Tools (que solo filtra). Por eso
la lógica vive en SQL Server y no en Python. **El criterio exacto sigue pendiente de
confirmar con Mónica** (ver §10).

### De la reunión 002 (2026-04-29) — [nota completa](reuniones/002-2026-04-29-paso-a-paso-cpa-vision.md)

**R7 — Son 4 las columnas de auditoría que se actualizan:**
**Costo Auditoría · IVA Auditoría · IEPS Auditoría · Impuesto**.

**R8 — Los campos `EDI` son el insumo; las 4 de auditoría son el resultado.** Los campos que
terminan en `EDI` se extraen de CPA Vision / factura electrónica; a partir de ellos se
calculan las 4 columnas de auditoría comparando mejor costo e impuesto correcto.

**R9 — 🔑 LLAVE DEL CRUCE CPA Vision ↔ Compras:**
> **número de proveedor + número de factura + código de barra**

Las tasas del archivo de CPA Vision corresponden a **`IVA EDI`** e **`IEPS EDI`** en el
archivo de compras. **Esta es la especificación del puente Etapa A ↔ Etapa B (§7), que
sigue sin implementarse.**

**R10 — Hoja `Pendientes_EDI`:** segunda hoja con la misma información, donde se completan
los datos faltantes manualmente o vía CPA Vision.

**R11 — Tercera fuente:** cuando el dato no está en CPA Vision, los auditores lo buscan en
**listas de precios de P-Mail (correo)** y actualizan **manualmente el costo auditoría**.

**R12 — Validar que el pago coincida con la recepción y la factura**, por problemas
históricos de **pagos de facturas cruzadas** en Soriana. (Relacionado con C5.)

**R13 — Flujo ideal del auditor:** (1) ver las compras con el mayor % posible de información
ya poblada → (2) corroborar las diferencias preliminares → (3) generar el archivo de salida
con un botón, en el formato exacto que se envía al proveedor, sin acomodar campos a mano.

**Formato de CPA Vision:** entrega **un CSV comprimido por mes**, no un consolidado.
Columnas: código de barra · valor unitario · tasa de impuesto · cantidad facturada · total factura.

### De la reunión 003 (capacitación con Luis Martínez) — [nota completa](reuniones/003-2026-XX-XX-capacitacion-cpa-vision-luis.md)

#### 🔴 Procedimiento de descarga CORRECTO (corrige lo dicho en la reunión 002)

1. **Emitidos: NO marcar nada**
2. **Recibidos → Vigentes → Ingreso**
3. **Tienda Soriana** (no "todas")
4. Rango de fechas
5. Tipo: **"hoja de cálculo con detalle de conceptos y tasas"**
   — **NO** "detalle de conceptos" a secas: esa **no trae el porcentaje de impuesto**
6. Archivo a subir: **RFC en la primera celda, SIN encabezado**

> La reunión 002 decía "marcar todos los emitidos y todos los recibidos". **Es incorrecto.**
> Luis lo reiteró tres veces.

#### 🔴 Limitación: las tasas especiales NO bajan
La hoja de CPA Vision **solo trae proveedores con tasa 16% u 8%**. **NO trae vinos/licores**
(53%, 30%, 26.5%) — justo el caso de mayor impacto económico (R4). Ver C9.

**R14 — Criterio del mejor costo (confirmado por Luis).** Se compara **`costo UNI`** (sistema)
contra **`costo neto EDI`** (CPA Vision). **Si `costo neto EDI` está vacío, se toma `costo UNI`
por defecto**, porque no hay con qué comparar.

**R15 — Unidades y factor de empaque.** Si compras trae el costo por caja y CPA Vision también,
no hay diferencia. **El problema es cuando las unidades no coinciden** (caja / pieza / kilo).
La corrección es **dividir por el factor de empaque** (ejemplo real: $297 / 3 = $99).

**R16 — Descuento de catálogo. ⚠️ CONCEPTO NUEVO.** Antes de calcular el costo auditoría hay
que **confirmar si el proveedor maneja descuento de catálogo** (columna dedicada). Se aplica
**después del pago de facturas**. **No está implementado.** Ver C10.

**R17 — Definición de `costo OUT`:** es **la comparación entre `costo UNI` y `costo neto EDI`**.
`costo mío` / `costo neto mío` son columnas de **control**, para verificar que la fórmula da
lo esperado.

**R18 — ✅ REGLA DEL IMPUESTO (cierra C2).** La fuente de verdad es **la factura**, no el sistema:
- Proveedor **sí factura** el impuesto → **actualizar/incluir en el sistema**
- Proveedor **no lo factura** → **dejar en cero**
- **Si en la factura no aparece el porcentaje → no debe registrarse el impuesto**

Caso validado: compras dice 0%, CPA Vision y la factura dicen 16% → **se actualiza compras a 16%**.
Conceptos guía: **`IEPS T007`** e **`IVA T0007007`**.

**Validar una factura puntual:** Tienda Soriana → "buscar XML" → **UUID** (más directo que RFC)
+ fecha de emisión → devuelve el **PDF**, con costo unitario, cantidad recibida, código de
barras y subtotal.

### De la reunión 004 (2026-06-09) — [nota completa](reuniones/004-2026-06-09-mapeo-columnas-cruce.md)

> 🔑 **El mapeo campo por campo está en su propio documento:**
> [MAPEO_CRUCE_CPA_COMPRAS.md](MAPEO_CRUCE_CPA_COMPRAS.md)

**R19 — Factor de empaque:** es **la cantidad de unidades dentro de una caja o paquete**
(caja de 4 yogures → factor 4). **No viene de CPA Vision; se toma del archivo de compras.**

**R20 — Costo bruto EDI = `costo neto × factor empaque`.** No viene de CPA Vision, se deriva.

**R21 — Importe por artículo EDI = `costo neto × factor empaque × (1 + IVA)`.**
Debe coincidir con `importe total` / `importe concepto` de CPA Vision.

**R22 — 🔴 Los importes de impuesto se calculan A NIVEL FACTURA, no por artículo:**
```
IMP IVA EDI  = total factura ÷ (1 + tasa) × tasa
IMP IEPS EDI = total factura ÷ (1 + tasa) × tasa
```
Luis fue explícito en que es **a nivel de factura completa**. En CPA Vision **solo viene el
porcentaje, no el importe** — por eso hay que derivarlo.

**R23 — El valor unitario puede venir por caja.** Cuando es así, **dividir entre la cantidad**
para obtener el unitario real ($282 ÷ 24 = $11.75).

**R24 — Se puede avanzar con campos vacíos.** Acuerdo explícito: **el análisis principal se
basa en `costo neto EDI` contra el costo del sistema**; lo que no se logre llenar se deja vacío.

**Cambio de estrategia:** **descargar todo primero a SQL, cruzar después** — revierte la
"opción 2" de la reunión 002.

### R25 — Qué base de compras manda para cada año (Óscar, 2026-07-24)

`F_COMPRAS` existe en dos bases del mismo servidor (`ATL20AF2222SQ19`) y **las dos
devuelven años solapados**, pero no valen lo mismo:

| Base | Qué se le pide | Por qué |
|---|---|---|
| `SORIANA_PROJECTS` | **2020–2024** | Fuente de verdad de todo lo anterior a 2025 |
| `SORIANA_2025_PROJECTS` | **solo 2025** | Sus años previos **están incompletos** |

`SORIANA_2025_PROJECTS` también devuelve renglones de 2022, 2023 y 2024 —verificado con
Selecta, con los mismos conteos que la otra base— **pero esa información no es confiable:
a veces está incompleta.** De esa base se toma **únicamente 2025**; el resto del periodo
sale siempre de `SORIANA_PROJECTS`.

Implementado en `FUENTES_COMPRAS` ([database.py](../automation_cobros/database.py)), que
recorta el periodo pedido contra el rango de cada fuente. **No ampliar esos rangos:** no
solo duplicaría renglones, metería datos parciales en la auditoría.

---

## 10. Contradicciones y huecos por resolver

Lista viva. Cada punto debe cerrarse con Mónica o Luis.

| # | Tema | Estado |
|---|---|---|
| C1 | **¿El criterio de `costo OUT` que está en el código es el original de Data Services?** El código hace `si hay EDI y ctonto_edi < ctouni → ctonto_edi` (§3). **Luis confirmó la mitad** en la reunión 003 (R14): si el EDI está vacío se toma `costo UNI`. **Sigue sin confirmarse** que con ambos valores presentes gane siempre el menor. | 🟡 Parcial |
| C2 | **Regla completa del IEPS/IVA.** | ✅ **CERRADO** por R18 (reunión 003). La fuente de verdad es la factura: si el proveedor factura el impuesto se actualiza el sistema; si no lo factura, cero; si la factura no muestra porcentaje, no se registra. |
| C3 | **IVA clavado en `0.16` en la fórmula de Excel** (§8.2) contra un IEPS real de hasta 53% (R4). El Excel entregado al proveedor puede traer números mal en productos con IEPS. | 🔴 Abierto — riesgo alto |
| C4 | **Clasificación de la diferencia.** R4 da tres orígenes (faltante / costo / impuestos); el código usa cuatro etiquetas (`dif costos` / `sin diferencia` / `sobrepago` / `faltante`). **No empatan** y la regla nunca se cerró (§5). | 🔴 Abierto |
| C5 | **`paynetamt` usa `max` y no `sum`** (§4). Correcto con un pago por folio, subestima con pagos parciales. **Agravado por R12**: Mónica reportó problemas históricos de **pagos de facturas cruzadas** en Soriana, así que el supuesto de un solo pago por folio es frágil. | 🔴 Abierto — riesgo alto |
| C6 | **¿El proyecto se integra dentro de Audit Tools?** La vicepresidencia y Antonio lo pidieron (reunión 002). Óscar lo ve complicado por ser Access. Quedó pendiente hablar con **Armando**. Hoy el proyecto es una herramienta Python independiente. | ⚪ **Aplazado por decisión de Óscar (2026-07-22).** Fuera de alcance por ahora; no retomar hasta que él lo indique. |
| C7 | **El puente Etapa A ↔ Etapa B no está implementado**, aunque la llave del cruce está perfectamente especificada desde 2026-04-29 (R9). | 🔴 Abierto — es el pendiente central |
| C8 | **Cuenta compartida de CPA Vision.** | ⚪ **Cerrado — no accionable.** Óscar confirmó el 2026-07-22 que la descarga ya está bien. |
| C9 | **Vinos y licores no bajan por CPA Vision.** La hoja solo trae tasas de 16% y 8%; las especiales (53%, 30%, 26.5%) no. | 🟡 **No es tema de descarga** (esa ya está bien), sino de **cobertura de datos**: para esos proveedores el cruce simplemente no encontrará EDI. Tenerlo presente al interpretar resultados. |
| C10 | **Descuento de catálogo no implementado.** Luis lo revisa **antes** de calcular el costo auditoría (R16); se aplica después del pago de facturas. **No aparece en el código ni en ninguna otra reunión.** Falta saber de qué columna sale y cómo afecta el cálculo. | 🔴 Abierto |
| C11 | **Factor de empaque en el cruce.** Cuando las unidades no coinciden (caja/pieza/kilo) hay que dividir por el factor de empaque (R15). **Falta confirmar si el cruce automatizado lo aplicará** y con qué criterio se detecta la discrepancia. | 🔴 Abierto |
| C12 | **¿CPA Vision acepta varios RFC por solicitud?** | ⚪ **Cerrado — no accionable.** Óscar confirmó el 2026-07-22 que la descarga ya está bien; el scraper va de uno en uno y así se queda. |

| C13 | **Las fórmulas de impuesto se escribieron con `1.16` y `1.08` literales** (R22). El divisor debe ser **la tasa real del renglón**. Mismo vicio que C3 en el exportador de Excel. | 🔴 Abierto |
| C14 | **Choque de niveles de cálculo.** R22 define el importe de impuesto **a nivel factura completa**; `calculations.py` calcula `imp_aud` **por renglón**. Falta decidir cuál gobierna y si conviven. | 🔴 Abierto — afecta el cruce |

> ⚪ **Nota permanente (2026-07-22):** todo lo relativo a la **mecánica de descarga de CPA
> Vision** —botones, selecciones, filtros, formato de solicitud, paralelismo— **está resuelto
> y verificado**. No volver a levantarlo como pendiente. Lo documentado en la reunión 003 se
> conserva solo como referencia histórica.
