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

En `calculations.recalculate_dataframe()`. La bandera que gobierna las tres columnas
auditadas es **"¿la fila cruzó con CPA Vision?"** — es decir, si trae CFDI. Se detecta por
la **presencia real** de `uuid` o `ctonto_edi` (celda con dato), **no** por que el valor
sea distinto de cero (ver §3.1).

```
Si la fila CRUZÓ con CPA (hay CFDI):
    cto_aud  = min(ctonto_edi, ctouni)   (el menor; pero nunca 0, ver abajo)
    iva_aud  = poriva_edi                (aunque sea 0)
    ieps_aud = prieps_edi                (aunque sea 0)

Si la fila NO cruzó (sin CFDI):
    cto_aud  = ctouni                    (el del sistema; no se pone 0 al costo)
    iva_aud  = iva_t007s                 (tasa SAP)
    ieps_aud = ieps_t007s               (tasa SAP)
```

**Si el proveedor facturó un costo MENOR al de sistema, el correcto es el del proveedor.**
Es una regla conservadora: **solo corrige a la baja**, nunca al alza. El costo del CFDI
solo gana si es válido (`ctonto_edi > 0`) y menor a `ctouni`; nunca se deja el costo en 0.

```
imp_aud = cto_aud × can_rec × (1 + iva_aud) × (1 + ieps_aud)
```

### 3.1 Por qué la bandera es "cruzó", no "valor ≠ 0"  — reunión 2026-07-31

Acuerdo con **Mónica López** y **Perla Maya**:

- **Lo que prima es la factura.** Si la información se ligó con CPA Vision, los tres campos
  auditados toman lo del CFDI, *aunque el impuesto facturado sea 0*. Ejemplo: cruzó y
  `poriva_edi = 0` → `iva_aud = 0`, aunque `iva_t007s` traiga 0.16.
- **Si NO se ligó nada de EDI**, no se puede deducir que el impuesto es 0 ni poner el costo
  en 0 (generaría una diferencia falsa que no podemos justificar): se deja lo del sistema
  (`cto_aud = ctouni`, `iva_aud = iva_t007s`, `ieps_aud = ieps_t007s`).

Detalle en [reuniones/005-2026-07-31-costo-impuestos-cruce.md](reuniones/005-2026-07-31-costo-impuestos-cruce.md).

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

Implementado en `FUENTES_COMPRAS` ([database.py](../automation_costos/database.py)), que
recorta el periodo pedido contra el rango de cada fuente. **No ampliar esos rangos:** no
solo duplicaría renglones, metería datos parciales en la auditoría.

---

## 10. Contradicciones y huecos por resolver

Lista viva. Cada punto debe cerrarse con Mónica o Luis.

| # | Tema | Estado |
|---|---|---|
| C1 | **¿El criterio de `costo OUT` que está en el código es el original de Data Services?** El código hace `si cruzó CPA y ctonto_edi < ctouni → ctonto_edi; si no → ctouni` (§3). | ✅ **CERRADO** por reunión 005 (2026-07-31, Mónica/Perla): sin cruce se deja `ctouni` (nunca 0); con cruce gana el menor. La bandera es "¿cruzó CPA?" (presencia de CFDI), no "valor ≠ 0", y los impuestos del CFDI se respetan aunque sean 0 (§3.1). |
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

---

## 11. Ajustes de pagos MR8M y KG-14 (acordado 2026-08-04, reunión 006)

El Line Item de Compras (Audit Tools) **no contempla ciertas devoluciones/ajustes de pago**
que sí anulan diferencias reales. Viven en `SORIANA_PROJECTS.dbo.F_APV2` y se aplican como
**paso extra** al Consolidado de la Validación de Condiciones.
Implementado en [`ajustes_pagos.py`](../automation_costos/ajustes_pagos.py), integrado en
[`validation_exporter.py`](../automation_costos/validation_exporter.py).

**Consulta base:**
```sql
SELECT * FROM SORIANA_PROJECTS.dbo.[F_APV2](@proveedor, @inicio, @fin)
```

**Dos tipos de devolución** (importe en `GrsInvAmt`, siempre negativo):

| Tipo | Cómo se identifica | Llave de cruce con el Consolidado |
|---|---|---|
| **MR8M** | `DOC_TEXT = 'MR8M'` | `VndNbr + InvNbr` ↔ **Proveedor + Factura** (no trae tienda ni nota) |
| **KG-14** | `COD_TYPE_CODE = 'KG'` y `BSAK_BSIK_XREF3 LIKE '14%'` | `RcpNbr + StrNbr` ↔ **Nota de entrada + Tienda** (= el folio del Consolidado; corrección 2026-08-04) |

**Reglas según el estado de compensación (`ChkNbr`):**

1. **Compensada** (`ChkNbr` con valor = el pago ya fue efectivo): el importe (`GrsInvAmt`,
   negativo) **se consume contra la diferencia disponible** del renglón cruzado, sin dejarla
   por debajo de 0. Si una factura MR8M cae en varios folios, se reparte en cascada.
2. **No compensada** (`ChkNbr` vacío o `0` = identificado por el cliente pero **aún no
   ejecutado**): **no se resta**. El renglón cruzado se **marca como alerta**
   ("No compensado/ejecutado") con el conteo y el monto pendiente, para que el auditor vigile
   esa factura/nota en el sistema del cliente y haga la resta manual cuando se compense
   (acordado 2026-08-04, reunión 007). Ej. real 741: la factura 12244 (`ChkNbr` vacío,
   −$155,020.78) conserva su diferencia y queda marcada.
3. `cto/iva/ieps` **no se tocan**: esto opera sobre la **diferencia de pago** del Consolidado,
   no sobre el costo auditado (§3).

**Salida (Validación de Condiciones):**

- Al **Consolidado** se le agregan seis columnas: `Tipo Ajuste` (MR8M / KG / MR8M+KG),
  `Ajuste Pagos` (suma compensada aplicada, negativa), `Diferencia Ajustada` (= `Diferencia` +
  `Ajuste Pagos`), `Compensado` (bandera "No compensado/ejecutado" cuando aplica),
  `Conteo No Compensados` (# de devoluciones pendientes que cruzan el renglón) y
  `Monto No Compensado` (suma pendiente).
- Los renglones que una devolución **compensada** deja en ~0 **desaparecen del Consolidado**
  y quedan en la hoja **"Ajustes"**. Los que solo tienen devoluciones **no compensadas**
  **se quedan** en el Consolidado con su diferencia intacta y la bandera de alerta.
- La hoja **"Ajustes"** es la bitácora de cada devolución cruzada (compensada o pendiente):
  factura, tienda, nota, `Compensado` (Sí/No), monto aplicado o pendiente, `ChkNbr`, `DOC_TEXT`.
- Si el proveedor no tiene devoluciones o la BD no está disponible, la Validación se genera
  **igual que antes** (sin columnas extra ni hoja Ajustes): es un paso aditivo y seguro.

Detalle y evidencia en [reuniones/006-2026-08-04-ajustes-pagos-mr8m-kg.md](reuniones/006-2026-08-04-ajustes-pagos-mr8m-kg.md)
y [reuniones/007-2026-08-04-alerta-no-compensados.md](reuniones/007-2026-08-04-alerta-no-compensados.md).

---

## 12. Periodo a descargar/ejecutar — margen 2026 (acordado 2026-08-05, reunión 008)

El periodo "2025" **arrastra a 2026** por facturas subidas tarde y pagos con plazo de hasta
90 días. Hay **dos cortes distintos**:

| Proveedor se trabaja como | **Compras / ejecución** (`--start`..`--end`) | **CPA (descarga)** |
|---|---|---|
| **2020-2024** | 2020-01-01 .. 2024-12-31 | años 2020-2024 completos |
| **2025** | 2025-01-01 .. **2026-03-31** | 2025 completo + **solo ENE 2026** |
| **2020-2025** | 2020-01-01 .. **2026-03-31** | 2020-2025 + **solo ENE 2026** |

- **Compras (SQL):** `FUENTES_COMPRAS` extiende `SORIANA_2025_PROJECTS` a 2026 (límite
  **superior**; seguro, no hay otra fuente 2026). Ejecutar con `--end 2026-03-31` (corte
  actual de la info: la base tiene 2026 cargado hasta ~marzo). ⚠️ El límite **inferior** de esa
  base sigue prohibido (2022-2024 incompletos ahí; §10 C-histórico). No duplica años.
- **CPA (CFDIs):** el portal tiene malla por **mes**. Cuando el periodo incluye 2025 se marca,
  además de los años completos, **solo enero 2026** (celda del mes, no el año 2026 entero) —
  `cpa_vision._set_month_checkbox` + `_MES_MARGEN=(2026,1)`. **No** cambia el `FECHAS` de los
  lotes: el scraper agrega enero 2026 solo. Máxima descarga por proveedor: **31-ene-2026**.
- **Por qué distinto:** CFDIs = facturas emitidas poco después de la compra (+1 mes margen);
  compras/pagos = hasta 90 días (marzo). Las compras feb-mar 2026 sin CFDI quedan sin EDI —
  la extensión a marzo es por el **pago**, no por nuevas facturas.

Detalle en [reuniones/008-2026-08-05-periodo-margen-2026.md](reuniones/008-2026-08-05-periodo-margen-2026.md).

## 13. Enfoque de descarga por cobertura <90% (acordado 2026-08-10, reunión 009)

**Cambio de criterio.** Ya no se descarga "todo el historial de cada proveedor pendiente por
prioridad". Se descarga **solo proveedor+año con cobertura EDI < 90%**, según el archivo
**"Planeacion vs %EDI poblado Soriana.xlsx"** (una fila por proveedor–año), columna `acción`:

| `acción` | Significado | Cobertura |
|---|---|---|
| **Descargar/Ejecutar** | 👉 descargar ese año de CPA | siempre <90% |
| Ejecutar | ejecutar directo, sin descargar | ≥90% |
| ninguna | no tocar (o ya "Terminado" 2020-2024) | mixto |

**Reglas operativas.**
- **Granularidad por año.** `FECHAS` del lote lleva los años sueltos <90% de cada proveedor
  (ej. `"2021 2022 2025"`). El scraper agrega enero-2026 solo cuando 2025 está presente (§12).
- **Fuente de verdad = parquet** (`outputs/cpa_vision/parquet`, partición `rfc/year`). Se
  excluye todo proveedor-año ya presente. NUNCA se confía en CSV/métricas (ver §"Validar datos").
- **Orden** = misma prioridad definida (`Prioridad_Proveedores_CPA.xlsx`); los ausentes, al final.
- **Extranjeros sin RFC** (LLC, LTD, GmbH…): no emiten CFDI mexicano → imposible por CPA. Se
  reportan aparte, no se descargan.
- **Un solo parquet**; copiar lo descargado a la carpeta de Data Services (Fase 3, la hace Óscar).
  Los proveedores ya descargados que quedaron ≥90% **no se eliminan**.

**Definiciones (validadas contra los conteos de Mónica).**
- `reg_compras` = renglones de `F_COMPRAS` con `cod_tipo_mvto` **distinto de 161 y 162**.
- **El año se define por `rcvdt`** (fecha de recibo). Reproduce exacto `reg_compras` de Mónica.
- Cobertura EDI = renglones con `ctonto_edi <> 0` / `reg_compras`.

**Indicador de beneficio por año** (`scripts/beneficio_cpa.py`). Por proveedor-año:
- cobertura **antes** = `ctonto_edi<>0` tal como viene de la base (EDI del cliente);
- cobertura **después** = `ctonto_edi<>0` tras cruzar con el parquet CPA;
- beneficio = después − antes (puntos porcentuales y renglones ganados).
- Validado: Selecta (741) "antes" 2020-2024 = 20.86% (idéntico a Mónica). El "después" mide el
  cruce real; en 2020 casi no sube porque los CFDIs bajados no ligan por barcode+factura
  (hallazgo de calidad de datos, no defecto del cálculo).

**Scripts.** `scripts/gen_lote_monica.py` (genera el maestro `descarga_monica_pendientes.xlsx`
+ `reporte_monica_extranjeros.xlsx`) y `scripts/beneficio_cpa.py`.

Detalle en [reuniones/009-2026-08-10-enfoque-cobertura-90-monica.md](reuniones/009-2026-08-10-enfoque-cobertura-90-monica.md).

---

## Reporte consolidado de diferencias (2026-08-13 08:40:34)

Pedido por **Héctor Saucedo**: un solo archivo de control con la diferencia de cada
proveedor ejecutado, con **proveedor, periodo, monto y concepto**. Vive en la raíz de los
entregables como `Reporte_Diferencias_Consolidado.xlsx` y lo produce
`automation_costos/reporte_diferencias.py`.

**Es un espejo, no un recálculo.** La fuente es la hoja `Consolidado` de cada
`Validacion_*.xlsx` ya entregada. Por construcción el reporte cuadra al centavo con los
entregables; si un número se ve raro, el error está en la Validación, no en el reporte.

### Definición de los montos

| Concepto | Cómo se obtiene |
|---|---|
| **Diferencia a reclamar** | Suma de `Diferencia Ajustada` (o `Diferencia` si el proveedor no trae devoluciones) de la hoja Consolidado. **Es idéntico al número de la hoja "Resumen" de esa Validación.** |
| **Compensado por devoluciones** | Suma de `Ajuste Aplicado` de la hoja Ajustes (MR8M/KG-14). Informativo: **no se reclama**, ya se recuperó por devolución. |
| **Diferencia detectada** | `Diferencia a reclamar` + `Compensado por devoluciones`. Es el hallazgo bruto de la auditoría. |

### Definición del concepto

1. Si el auditor escribió algo en `Observaciones Auditor`, **eso es el concepto**. El reporte
   se afina solo conforme se trabajan los archivos.
2. Si la celda trae un error de Excel (`#N/A`, `#REF!`, …) se ignora: es un BUSCARV roto, no
   una clasificación. Celaya (73692) trae 26,319 `#N/A`.
3. Si no hay clasificación, se deriva del dato: `Diferencia de costos`, o
   `Diferencia de costos (parcialmente compensada)` cuando hubo devolución pero quedó saldo.

**Proveedores sin una sola nota en el Consolidado.** No significa que no se les encontrara
nada: si las devoluciones anularon **todas** sus diferencias, `aplicar_ajustes_a_consolidado`
las saca del Consolidado y quedan solo en la hoja Ajustes. Se etiquetan
`Compensado por devoluciones (nada que reclamar)`, no "Sin diferencias", y su periodo se toma
de la **fecha de pago de la devolución** (la única que queda), marcado como tal en la propia
celda para no mezclar bases en silencio. Son 5 proveedores y $3,787,583.77 ya recuperados:
25133, 23873, 43398, 394213 y 61788. `Sin diferencias` se reserva para el caso real de cero.

El concepto que se muestra a nivel proveedor es el que **concentra el dinero**, no el más
frecuente: una nota grande pesa más para el control que veinte chicas.

### Qué Validación representa a cada proveedor

Una carpeta puede tener varias. La regla evita duplicar y evita tomar la equivocada:

1. **`Rejecución_validación_pagos/` manda sobre todo.** Los 6 entregables que están ahí se
   rehicieron ya con las devoluciones MR8M/KG-14; los de sus carpetas normales son de antes
   de esa regla y **no traen hoja Ajustes**, así que sobrestiman el monto a reclamar. La
   diferencia no es menor: Pepsico pasa de $160.6 M a $75.6 M, y en total son **$187.8 M**
   de más. Son Arca (391250), Nestlé (5462), Celaya (73692), Selecta (741), Pepsico (76034)
   y 3M (80622).
2. Si no está reejecutado, la completa `Validacion_<carpeta>.xlsx` de su carpeta. Esa gana
   sobre las variantes que conviven ahí: Arca guarda además `_2020` … `_2025` (subconjuntos
   del mismo total) y Pepsico una reejecución parcial.
3. Si no existe la completa, todas las `Validacion_<carpeta>_*.xlsx`, que ahí sí son
   complementarias. (3M estaba así, partido en `_2020-2024` y `_2025`; ya no aplica porque
   su reejecución trae un archivo único.)

**Cómo se reconoce una corrida vieja:** no tiene hoja `Ajustes`. Si aparece otro proveedor
en ese caso, su archivo bueno va a `Rejecución_validación_pagos/` y el reporte lo toma solo.

### Histórico de montos

El reporte lee el Excel de la Validación, así que refleja **siempre el último estado**. Si un
auditor revisa un proveedor de $6.0 M y sus ajustes lo dejan en $5.6 M, el reporte diría
$5.6 M y el monto original se perdería.

`Historico_Diferencias.parquet` (en la raíz de entregables, junto al reporte) lo conserva: se
anota un renglón por proveedor **cada vez que sus cifras cambian** — nunca se reescribe ni se
borra. De ahí salen tres columnas del Resumen:

- **Monto inicial** — lo que dio la primera corrida.
- **Variación vs inicial** — cuánto se movió desde entonces (negativo = el auditor bajó el monto).
- **Revisiones** — cuántas veces han cambiado sus cifras.

Y la hoja **Historico de montos** trae la bitácora completa con fecha. Correr el reporte sin
que nada cambie **no** agrega renglones.

### Actualización automática

Se regenera solo al terminar **cada** proveedor (enganche en
`pipeline.generar_salida_proveedor` y `pipeline_streaming.generar_validacion_grande`, así que
cubre la GUI, `cpa-salida` y los gigantes) y al cerrar un lote (`ejecutar_bloque1.py`). Es
incremental: cachea por `(archivo, fecha, tamaño)`, así que un lote nuevo solo paga la lectura
de lo nuevo. Un fallo del reporte **nunca** tumba el entregable del proveedor.

Se escribe a un temporal y se mueve encima del destino: si alguien tiene el reporte abierto
en Excel, el archivo bueno **queda intacto** y el mensaje dice qué hacer. La siguiente corrida
lo pone al día sola.

Regeneración manual: `python scripts/reporte_diferencias.py [--forzar]`.

**Estado (2026-08-13, ya con la carpeta de reejecución):** 50 proveedores, 254,551 notas,
**$1,025,482,778.03 detectados** → **$663,485,884.05 a reclamar** y $361,996,893.98 ya
compensados por devoluciones.

---

## Las dos carpetas de CPA Vision y sus inventarios (2026-08-13)

Dos carpetas hermanas, con propósito distinto. **Ninguna sustituye a la otra** y cada una
lleva su propio `Inventario_CPA_Vision.xlsx`.

| Carpeta | Qué contiene |
|---|---|
| `cpa_vision` | **TODO** lo descargado, sin filtro. El acervo completo. |
| `cpa_vision_complemento` | **Solo** los proveedor-año con cobertura EDI **< 90%**. Es lo que se entrega como complemento. |

Un proveedor puede estar en las dos con distinto alcance: FRABEL (7112) tiene 2020–2025 en el
acervo y **solo 2025** en el complemento, porque sus otros años ya venían ≥90%.

**Estar en el complemento se decide por cobertura, no por haberse descargado.** Procter
(17222) se descargó porque la columna `accion` de Mónica lo pedía, pero no aparece en el
objetivo `<90% EDI`, así que **no** va al complemento. Son dos criterios distintos.

### Ambos procesos corren solos al cerrar un lote

Enganchados en `cpa_vision.py`, **separados a propósito**: si uno falla el otro ya quedó
escrito, y ninguno de los dos tumba un lote que costó horas.

1. `inventario_cpa.actualizar_inventario()` → inventario de `cpa_vision`.
2. `complemento_cpa.actualizar_complemento()` → copia las particiones y ZIP que falten al
   complemento y regenera **su** inventario.

Funciona igual desde el `.exe`.

### Por qué el objetivo vive en un CSV

Saber qué proveedor-año está bajo el 90% requiere el Excel de planeación (del repositorio) y
resolver el RFC de cada proveedor contra SQL. **El `.exe` no tiene ninguna de las dos**, y no
se quiere una consulta de minutos al cerrar cada lote.

Por eso el objetivo se persiste en `cpa_vision_complemento/_objetivo_edi_menor_90.csv`:

- lo **escribe** `scripts/complemento_cpa.py` (que sí tiene Excel y base);
- lo **lee** `automation_costos/complemento_cpa.py`, que es lo que corre en cada lote.

Como vive junto a los entregables en la unidad de red, el `.exe` siempre lo alcanza. Si el
archivo falta, no se inventa nada: se avisa y no se copia.

> ⚠️ **Cuando cambie la planeación** (proveedores o años nuevos en el objetivo) hay que
> correr `python scripts/complemento_cpa.py` para reescribir ese CSV. Las descargas del día
> a día ya se sincronizan solas.

**Estado (2026-08-13):** acervo 452 RFC / 1,155 pares · complemento 204 RFC / 354 pares.
Faltan 44 pares del objetivo por descargar.
