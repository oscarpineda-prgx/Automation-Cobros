# Reunión 007 — 2026-08-04 — Alerta de devoluciones NO compensadas

**Documentado el:** 2026-08-04 12:33:50
**Participantes:** Mónica López, Perla Maya, Óscar Pineda
**Duración / contexto:** Continuación de la 006. Se define qué hacer con las devoluciones
MR8M/KG cuyo `ChkNbr` viene **vacío** (identificadas por el cliente pero aún no ejecutadas).

---

## Resumen en 5 líneas

1. El `ChkNbr` (documento compensatorio) se genera cuando Soriana **paga** al proveedor (corte
   semanal, los miércoles): si trae folio, el pago ya fue efectivo.
2. Si el `ChkNbr` está **vacío**, el ajuste está identificado pero **no ejecutado**: no se
   puede restar todavía.
3. En vez de ignorarlo, se **marca una alerta** en el renglón del Consolidado que cruzaría con
   esa devolución.
4. La alerta indica que "en esta factura/nota hay un monto que no está compensado" para que el
   auditor lo vigile y haga la resta manual cuando se compense.
5. Se agrega también un **conteo** de registros no compensados por renglón.

## Decisiones tomadas

| # | Decisión | Impacto | Responsable |
|---|---|---|---|
| 1 | Las devoluciones MR8M/KG con `ChkNbr` vacío **no se restan**, se marcan como alerta | Evita restar algo aún no ejecutado | Mónica |
| 2 | Bandera `Compensado` = "No compensado/ejecutado" en el renglón cruzado | El auditor vigila esa factura/nota | Mónica / Óscar |
| 3 | Columna `Conteo No Compensados` (# de registros pendientes) y `Monto No Compensado` | Cuantifica lo pendiente | Óscar |
| 4 | El cruce usa las mismas llaves que la 006 (MR8M: prov+factura; KG: nota+tienda) | Consistencia | Óscar |

## Reglas de negocio nuevas o modificadas

> Copiado a [../LOGICA_NEGOCIO.md](../LOGICA_NEGOCIO.md) §11.

- **Compensada** (`ChkNbr` con valor): se resta (comportamiento de la 006).
- **No compensada** (`ChkNbr` vacío/0): no se resta; se marca el renglón con
  `Compensado = "No compensado/ejecutado"`, se suma `Monto No Compensado` y se incrementa
  `Conteo No Compensados`.
- El auditor usa la alerta para revisar en el sistema del cliente hasta que el pago se
  compense y entonces aplicar la resta manualmente.

## Validación con datos reales (741)

- De 29 devoluciones MR8M/KG, **28 compensadas** y **1 no compensada** (factura 12244,
  −$155,020.78, `ChkNbr` vacío).
- Con la nueva lógica, la 12244 **conserva** su diferencia ($155,020.34) y queda marcada
  "No compensado/ejecutado" con `Monto No Compensado = 155,020.78`. Antes se ignoraba.

## Columnas / campos / datos mencionados

| Campo | Significado |
|---|---|
| `ChkNbr` | Documento compensatorio; con valor = pago efectivo, vacío = no ejecutado |
| `Compensado` (salida) | Bandera "No compensado/ejecutado" en el Consolidado |
| `Conteo No Compensados` | # de devoluciones pendientes que cruzan el renglón |
| `Monto No Compensado` | Suma pendiente (aún no restada) |

## Compromisos y pendientes

- [x] Marcar alerta + conteo + monto pendiente en el Consolidado.
- [x] Registrar cada devolución (compensada/pendiente) en la hoja "Ajustes".
- [ ] Nueva reunión para validar cómo quedó la información una vez extraída y cruzada.
- [ ] Mónica: revisar si en algún periodo Data Services omitió integrar estos movimientos.

## Dudas abiertas

- El volumen de no compensados podría ser mínimo (Mónica). Se avanza y se ajusta si el cruce
  necesita más filtros.

## Citas textuales relevantes

> **Mónica:** "si el check number ya trae un número, es que el pago fue efectivo hacia la
> cuenta del proveedor."

> **Mónica:** "no sé cómo le pudiéramos poner una alerta al auditor de que, oye, en esta
> factura el neto es este, pero hay un registro que no está compensado."

> **Óscar:** "un registro que no está compensado cuando el check number esté vacío... cruzar
> estos pagos por factura y proveedor contra validación de condiciones y hacer un conteo de
> los registros que en check number sea igual a vacío. Esa sería la bandera."
