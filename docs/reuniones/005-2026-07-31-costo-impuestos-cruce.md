# Reunión 005 — 2026-07-31 — Costo e impuestos auditados según cruce con CPA Vision

**Documentado el:** 2026-07-31 15:30:40
**Participantes:** Mónica López, Perla Maya, Óscar Pineda
**Duración / contexto:** Revisión del archivo de validación de un proveedor donde el
"Costo unitario sistema" salía en cero y donde una fila sin cruce con CPA Vision dejaba
impuesto en 0.

---

## Resumen en 5 líneas

1. `CtoUnitario_sistema` del archivo de Validación debe mostrar **`ctouni`** (costo del
   sistema), no `ctonto_edi`. Por eso salía en cero cuando no había EDI.
2. La bandera que decide `cto_aud`/`iva_aud`/`ieps_aud` es **"¿la fila cruzó con CPA
   Vision?"**, no "¿el valor es distinto de cero?".
3. **Si cruza**, los tres campos toman lo del CFDI **aunque el impuesto sea 0** ("lo que
   prima es la factura").
4. **Si no cruza**, se deja lo del sistema: `cto_aud = ctouni`, `iva_aud = iva_t007s`,
   `ieps_aud = ieps_t007s`. No se pone 0 al costo ni se asume 0 de impuesto.
5. La regla del "menor de los dos" para el costo **sigue vigente** cuando sí hubo cruce.

## Decisiones tomadas

| # | Decisión | Impacto | Responsable |
|---|---|---|---|
| 1 | `CtoUnitario_sistema` = `ctouni` (antes `ctonto_edi`) | Corrige el cero en el archivo de validación | Mónica |
| 2 | La bandera de cruce es presencia de CFDI (UUID/costo EDI), no valor ≠ 0 | Respeta IVA/IEPS = 0 facturados | Mónica / Perla |
| 3 | Sin cruce → costo e impuesto del sistema; nunca 0 | Evita diferencias falsas no justificables | Perla |

## Reglas de negocio nuevas o modificadas

> Copiado a [../LOGICA_NEGOCIO.md](../LOGICA_NEGOCIO.md) §3 y §3.1.

```
Si la fila CRUZÓ con CPA (hay CFDI):
    cto_aud  = min(ctonto_edi, ctouni)   (el menor; nunca 0)
    iva_aud  = poriva_edi                (aunque sea 0)
    ieps_aud = prieps_edi                (aunque sea 0)

Si la fila NO cruzó (sin CFDI):
    cto_aud  = ctouni
    iva_aud  = iva_t007s
    ieps_aud = ieps_t007s
```

Implementación: `calculations.recalculate_dataframe()` usa
`cruzo_cpa = presencia(uuid) OR presencia(ctonto_edi)` en vez de `ctonto_edi != 0`.

## Columnas / campos / datos mencionados

| Campo | Significado / regla |
|---|---|
| `CtoUnitario_sistema` (validación) | Costo unitario del sistema = **`ctouni`** |
| `ctouni` | Costo unitario del sistema (SAP) |
| `ctonto_edi` | Costo unitario facturado por el proveedor (CFDI) |
| `poriva_edi` / `prieps_edi` | Tasa IVA / IEPS del CFDI (pueden ser 0) |
| `iva_t007s` / `ieps_t007s` | Tasa IVA / IEPS del sistema (tabla T007S) |
| `uuid` | Folio fiscal del CFDI; su presencia marca que la fila cruzó |

## Compromisos y pendientes

- [x] `CtoUnitario_sistema = ctouni` en `validation_exporter.py`.
- [x] Bandera de cruce por presencia de CFDI en `calculations.py`.
- [ ] Óscar valida en el archivo de validación que un proveedor sin cruce deje 27.72 y 0.16.

## Dudas abiertas

- Ninguna sobre esta regla. Queda pendiente el caso general de pagos parciales múltiples
  (ver LOGICA_NEGOCIO §4), ajeno a esta reunión.

## Citas textuales relevantes

> **Perla:** "como ahí no se te ligó información, pues no podemos deducir que es cero
> también el impuesto. Tendríamos que dejar el del sistema."

> **Mónica:** "en las que no se te cruce nada de EDI, se deja el mismo costo del sistema y
> el mismo impuesto del sistema... porque no le podríamos poner cero al costo."

> **Mónica:** "el costo out como no se ligó nada de EDI, tenemos que dejar el que trae el
> sistema, que es el costo UNI, que en este caso es el 27.72."

> **Mónica:** "como no se ligó nada de IVA con factura electrónica, entonces este es el
> T007 IVA... y este sería el T007 IEPS."
