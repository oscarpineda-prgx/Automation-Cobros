# Reunión 006 — 2026-08-04 — Ajustes de pagos MR8M y KG-14

**Documentado el:** 2026-08-04 10:34:49
**Participantes:** Perla Maya, Mónica López, Óscar Pineda
**Duración / contexto:** Revisión de los resultados de los 6 proveedores iniciales. Perla
cruzó el resultado del auditor y encontró diferencias que el Line Item de Compras no
contempla porque son **ajustes/devoluciones de pago** que viven en otra tabla.

---

## Resumen en 5 líneas

1. Hay diferencias en el Consolidado que **no son reales**: ya se anularon con devoluciones
   de pago que Audit Tools no incluye en el Line Item.
2. Son dos tipos: **MR8M** y **KG-14**, ambos en `SORIANA_PROJECTS.dbo.F_APV2`.
3. **MR8M** no trae nota ni tienda, solo factura → se liga por **proveedor + factura**.
4. **KG-14** sí trae tienda y nota → se liga por **proveedor + factura + tienda**.
5. Solo aplican las devoluciones **ejecutadas** (`ChkNbr` con valor). El importe
   (`GrsInvAmt`, negativo) resta la diferencia del renglón.

## Decisiones tomadas

| # | Decisión | Impacto | Responsable |
|---|---|---|---|
| 1 | Sumar un proceso extra que lee `F_APV2` y aplica las devoluciones al Consolidado | Diferencias más precisas | Óscar |
| 2 | MR8M se identifica con `DOC_TEXT = 'MR8M'`; llave proveedor+factura | Cruce sin nota/tienda | Perla |
| 3 | KG-14 se identifica con `COD_TYPE_CODE='KG'` y `BSAK_BSIK_XREF3 LIKE '14%'`; llave **nota de entrada (`RcpNbr`) + tienda (`StrNbr`)** — corrección de Óscar 2026-08-04, antes era factura+tienda | Cruce a nivel folio | Perla / Óscar |
| 4 | Solo cuentan las devoluciones con `ChkNbr` (ejecutadas); vacío o 0 = no aplica | Evita contar ajustes no compensados | Mónica |
| 5 | Los renglones que la devolución deja en ~0 salen del Consolidado y quedan en una hoja nueva **"Ajustes"** | Trazabilidad | Óscar |

## Reglas de negocio nuevas o modificadas

> Copiado a [../LOGICA_NEGOCIO.md](../LOGICA_NEGOCIO.md) §11.

- Consulta base: `SELECT * FROM SORIANA_PROJECTS.dbo.[F_APV2](proveedor, inicio, fin)`.
- **MR8M**: `DOC_TEXT = 'MR8M'` + `ChkNbr` con valor + `GrsInvAmt < 0`. Sin `StrNbr`/`RcpNbr`.
  Llave: `VndNbr + InvNbr` ↔ `Proveedor + Factura`.
- **KG-14**: `COD_TYPE_CODE = 'KG'` + `BSAK_BSIK_XREF3 LIKE '14%'` + `ChkNbr` con valor +
  `GrsInvAmt < 0`. Llave: `RcpNbr + StrNbr` ↔ `Nota de entrada + Tienda` (corrección
  2026-08-04: KG **sí** trae `RcpNbr`/`StrNbr`, así que se liga por folio, no por factura).
- El importe de la devolución (`GrsInvAmt`, negativo) **se consume** contra la diferencia
  disponible del renglón, sin dejarla por debajo de 0.

## Validación con datos reales (741 - Selecta)

- MR8M: 6 movimientos; **5 aplican** (la factura 12244 tiene `ChkNbr` vacío → no ejecutada,
  se excluye; es justo el caso que Perla dudaba en la reunión). Los 5 cuadran exacto con las
  diferencias del Consolidado (12801→236,721.60, 12100→130,797.11, …).
- KG-14: 23 movimientos, todos con `ChkNbr`, todos con tienda y nota.
- Confirmado que **no** hace falta parsear los últimos 3 dígitos de `CONCA`: la tienda viene
  directa en `StrNbr`.

## Columnas / campos / datos mencionados

| Campo (F_APV2) | Significado |
|---|---|
| `VndNbr` / `InvNbr` | Proveedor / número de factura (llave del cruce) |
| `StrNbr` / `RcpNbr` | Tienda / nota de entrada (solo poblados en KG-14) |
| `GrsInvAmt` | Importe de la devolución (negativo) que anula la diferencia |
| `ChkNbr` / `ChkDt` | Cheque/folio de compensación y su fecha (ejecutado si tiene valor) |
| `DOC_TEXT` | "MR8M" identifica ese tipo de devolución |
| `COD_TYPE_CODE` / `BSAK_BSIK_XREF3` | "KG" + prefijo "14" identifican el ajuste KG-14 |

## Compromisos y pendientes

- [x] Módulo `ajustes_pagos.py` (consulta + aplicación) e integración en la Validación.
- [x] Hoja "Ajustes" + columnas `Tipo Ajuste`, `Ajuste Pagos`, `Diferencia Ajustada`.
- [ ] Óscar: re-generar la Validación de los 6 proveedores iniciales para aplicar los ajustes.
- [ ] Revisar si el Line Item ya trae dos pagos (por factura y por nota) en algún periodo,
      y si en alguno se omitió (lo revisa Mónica con Data Services).

## Dudas abiertas

- Si una factura MR8M cae en varios folios del Consolidado, la devolución se reparte en
  cascada; en 741 no ocurre (1:1). Revisar si en otros proveedores el reparto es correcto.
- El Exception Report lee `Diferencia` (original); para renglones parcialmente ajustados
  convendría que lea `Diferencia Ajustada`. Pendiente de decidir.

## Citas textuales relevantes

> **Perla:** "todos estos que dicen ajuste MR8M se cancelan por estos movimientos
> adicionales que tú no tuviste alcance… no viene por el número de nota de entrada, pero
> viene por el número de factura. Entonces yo lo ligué con el número de factura."

> **Perla:** "todos los movimientos aparecen como KG y que tengan en BSAK_BSIK inicien con
> el número 14 hacen referencia a una afectación directo de la factura."

> **Mónica:** "solo cuando está compensado… si está identificado por el cliente pero no está
> ejecutado" (no aplica sin `ChkNbr`).

> **Mónica:** "agregar por columna ese ajuste de pagos, por ejemplo todos los MR8M y todos
> los KG que son 14."
