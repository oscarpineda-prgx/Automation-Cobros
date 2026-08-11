# Reunión 009 — 2026-08-10 — Enfoque por cobertura <90% (correo de Mónica)

**Documentado el:** 2026-08-10 09:47:04
**Origen:** Correo de Mónica López a Óscar Pineda (validado con Héctor Saucedo).
**Contexto:** Cambia el criterio de qué descargar de CPA Vision. Ya no es "todo el
historial de cada proveedor pendiente por prioridad", sino **solo proveedor+año con
cobertura EDI < 90%**.

---

## Resumen en 5 líneas

1. Nuevo insumo: **"Planeacion vs %EDI poblado Soriana.xlsx"** — una fila por **proveedor–año**
   (2020…2025) con `% poblado EDI` **sin** el cruce CPA (estado original de la base).
2. Se descarga **solo** lo marcado `acción = Descargar/Ejecutar` (siempre <90%). Lo demás
   (`Ejecutar` ≥90%, o `ninguna` ya "Terminado") **no se toca**.
3. Granularidad **por año**: un proveedor puede necesitar solo algunos años.
4. La info descargada **de ahora en adelante se comparte con Data Services**.
5. Piden un **indicador de beneficio desagregado por año** (cobertura antes vs después del
   cruce), en vez del consolidado 2020-2024 del ejemplo (Selecta 20.86% → 60%).

## Decisiones tomadas

| # | Decisión | Responsable |
|---|---|---|
| 1 | Descargar solo proveedor-año con cobertura EDI <90% (`acción=Descargar/Ejecutar`) | Mónica/Héctor |
| 2 | Mantener el orden por la prioridad ya definida, acotado a ese objetivo | Óscar |
| 3 | Un solo parquet como fuente de verdad; copiar a la carpeta de Data Services | Óscar |
| 4 | Indicador de beneficio **por año** (no solo consolidado) | Mónica |
| 5 | Conservar los proveedores ya descargados aunque queden ≥90% (no borrar) | Óscar |

## Foto del objetivo (análisis del archivo, Fase 0)

- Total filas prov-año en el archivo: **4,202** (760 proveedores × años).
- `acción`: **Descargar/Ejecutar 416** (todas <90%) · `Ejecutar` 1,399 (≥90%) ·
  `ninguna` 2,387 (1,593 ≥90% + **794 <90% pero ya "Terminado" 2020-2024**, no se re-hacen).
- **Objetivo real = 416 filas / 246 proveedores.** Contra el parquet (fuente de verdad):

| Concepto | Filas prov-año | Proveedores |
|---|---|---|
| Ya cubiertas en parquet (lotes por prioridad previos) | 104 | — |
| 🌎 Extranjeros sin RFC (imposible por CPA) | 17 | 17 |
| **Faltan de verdad (descargables)** | **295** | **159** |

Faltantes por año: 2020→39, 2021→55, 2022→53, 2023→49, 2024→12, 2025→87.

## Hallazgos

- **17 proveedores extranjeros sin RFC mexicano** (LLC, LTD, GmbH, NV, SL — China, España,
  EUA, Brasil, Argentina, HK): no emiten CFDI mexicano → **CPA Vision no tiene nada de ellos**.
  Se reportan aparte (`reporte_monica_extranjeros.xlsx`), no entran a descarga.
- **El año se define por `rcvdt`** (fecha de recibo): reproduce EXACTO los conteos de
  `reg_compras` de Mónica. `reg_compras` = renglones con `cod_tipo_mvto` distinto de 161 y 162.
- **Validación del indicador:** Selecta (741) "antes" 2020-2024 = 10,278/49,273 = **20.86%**,
  idéntico a Mónica. El "después" medido (37.5%) queda por debajo de su ejemplo de 60% porque
  **2020 casi no cruza** (8.5%→8.7%) pese a tener 14,913 CFDIs bajados: los CFDIs 2020 existen
  pero no ligan por barcode+factura. Es un hallazgo real de calidad de datos, no un defecto.

## Entregables construidos

- `scripts/gen_lote_monica.py` → `descarga_monica_pendientes.xlsx` (maestro ordenado por
  prioridad, `FECHAS` = años sueltos <90% por proveedor) + `reporte_monica_extranjeros.xlsx`.
- `scripts/beneficio_cpa.py` → `outputs/beneficio_cpa_por_anio.xlsx` (cobertura antes/después
  por proveedor-año).

## Compromisos y pendientes

- [x] Fase 0 (dimensionar), Fase 1 (generador de lotes), Fase 2 (indicador de beneficio).
- [ ] Descargar los 159 proveedores faltantes (paginando el maestro con `--start-index`).
- [ ] Fase 3 (la hace Óscar): copiar lo descargado a la carpeta de Data Services
      `...\Proceso Validación de condiciones (Oscar Pineda)\cpa_vision`.
- [ ] Confirmar con Mónica el caso 2020 de Selecta (CFDIs bajados que no cruzan).

## Citas textuales relevantes

> **Mónica (correo):** "requerimos enfocar los esfuerzos en aquellos proveedores y periodos que
> presentan una cobertura inferior al 90%… descarga de información únicamente de los proveedores
> y periodos identificados con un porcentaje de población menor al 90%."

> **Mónica (correo):** "agradeceríamos que este indicador pudiera generarse de forma desagregada
> por año, con el fin de medir con mayor precisión el incremento en la cobertura de información."

Transcripción íntegra: [transcripciones/009-2026-08-10-correo-monica-cobertura.md](transcripciones/009-2026-08-10-correo-monica-cobertura.md)
