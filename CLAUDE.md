# CLAUDE.md — Automation-Costos

> **Índice maestro del proyecto.** Este archivo se carga automáticamente al inicio de cada
> sesión de Claude Code. Si el chat se cierra o se borra, leyendo este archivo y los que
> aquí se enlazan se recupera todo el contexto del proyecto.

**Última actualización:** 2026-07-22 10:53:41

---

## 1. Qué es este proyecto

Automatización del proceso de costos de la auditoría Soriana 2020–2024 (PRGX).
Pipeline en dos etapas que **todavía no están conectadas**:

1. **SQL → Excel**: consulta de datos de compras/convenios y exportación a plantillas Excel.
2. **Scraping CPA Vision**: descarga de documentos del portal del cliente.

**Desde el 2026-07-22 la GUI expone las dos etapas**: la tarjeta *ETAPA 2* ejecuta el cruce
CPA Vision → Compras. Ver [docs/GUI.md](docs/GUI.md).

## 1.1 Quién es quién

| Persona | Rol |
|---|---|
| **Mónica López** | Experta en el proceso de costos — autoridad sobre las reglas de negocio |
| **Luis** | Experto en el proceso de costos, junto con Mónica |
| **Héctor Saucedo** | Jefe de Óscar |
| **Óscar Pineda** | Desarrollo de la automatización — el usuario de este repo |

## 2. Mapa de la documentación

Lee estos archivos en este orden para ponerte al día:

| Archivo | Qué contiene |
|---|---|
| [docs/LOGICA_NEGOCIO.md](docs/LOGICA_NEGOCIO.md) | Reglas de negocio, definiciones de columnas, criterios de auditoría. **La fuente de verdad.** |
| [docs/MAPEO_CRUCE_CPA_COMPRAS.md](docs/MAPEO_CRUCE_CPA_COMPRAS.md) | 🔑 **Qué columna de CPA Vision llena qué columna de compras, y con qué fórmula.** Especificación del cruce. |
| [docs/CRUCE_IMPLEMENTACION.md](docs/CRUCE_IMPLEMENTACION.md) | Cómo quedó construido el cruce: arquitectura, estrategia de llaves, métricas y pruebas. |
| [docs/GUI.md](docs/GUI.md) | Interfaz gráfica: lenguaje visual PRGX, estructura, concurrencia y build del .exe/.zip. |
| [docs/PLANEACION.md](docs/PLANEACION.md) | Qué proveedores se trabajan, en qué orden y periodo. Master 2026 y los 6 urgentes. |
| [docs/reuniones/README.md](docs/reuniones/README.md) | Índice de reuniones con el cliente/equipo, una nota por reunión |
| [docs/BITACORA.md](docs/BITACORA.md) | Registro fechado de cada cambio de código y cada decisión tomada |
| [docs/ESTADO_ACTUAL.md](docs/ESTADO_ACTUAL.md) | Dónde vamos ahora mismo: pendientes, bloqueos, siguiente paso |
| [README.md](README.md) | Instalación y uso para el usuario final |

## 3. Estructura del código

```
main.py                        Punto de entrada / subcomandos de terminal
config.py                      Rutas, credenciales, parámetros
automation_costos/
  app.py                       GUI (customtkinter) — Etapa 1 + Etapa 2 (cruce CPA Vision)
  ui.py                        Tema visual PRGX y widgets (sin lógica de negocio)
  assets/                      prgx-icon.png/.ico, Soriana-Logo.png
  database.py                  Conexión a SQL Server (Trusted_Connection)
  utils.py                     make_folio() y helpers
  calculations.py              recalculate_dataframe() — la regla del costo auditado
  excel_exporter.py            Genera el Excel "Compras"
  recalculate.py               Relee el Excel editado por el auditor
  validation_exporter.py       Genera "Validacion de Condiciones" y el consolidado
  cpa_vision.py                Scraping del portal CPA Vision (Playwright) — 80 KB
  cpa_parquet.py               ZIP -> dataset Parquet particionado
  cpa_consolidator.py          Consolidación de salidas CPA
  cruce_cpa.py                 🔑 Cruce CPA Vision -> Compras (llena el bloque EDI)
  ajustes_pagos.py             🔑 Devoluciones MR8M/KG-14 (F_APV2) que anulan diferencias
scripts/
  log_cambio.py                Helper que estampa fecha/hora en la bitácora
  validar_formulas_impuesto.py Doble validación de las fórmulas de impuesto (DuckDB)
test_cruce_cpa.py              Prueba del cruce con datos reales de Alceda
templates/                     Plantillas Excel base
outputs/                       Salidas generadas (no versionado)
logs/                          Logs de ejecución (no versionado)
scripts/log_cambio.py          Helper para agregar entradas fechadas a la bitácora
```

## 4. Reglas de trabajo para Claude en este proyecto

Estas reglas son obligatorias, no sugerencias.

### 4.1 Documentar todo con fecha y hora
Después de **cada cambio de código** o **cada decisión de lógica**, agrega una entrada a
[docs/BITACORA.md](docs/BITACORA.md). La fecha y hora **siempre** se obtienen ejecutando
Python, nunca de memoria:

```bash
python scripts/log_cambio.py --tipo codigo --titulo "Título corto" --detalle "Qué y por qué"
```

O si necesitas solo el timestamp:

```bash
python -c "from datetime import datetime; print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))"
```

### 4.2 Toda lógica nueva va a LOGICA_NEGOCIO.md
Si se define una regla, un criterio, el significado de una columna o una fórmula, se
escribe en [docs/LOGICA_NEGOCIO.md](docs/LOGICA_NEGOCIO.md) con su fecha. No se deja
solo en el chat ni solo en un comentario del código.

### 4.3 Cada reunión genera su nota
Una transcripción de reunión se resume en `docs/reuniones/NNN-YYYY-MM-DD-tema.md` y se
enlaza desde [docs/reuniones/README.md](docs/reuniones/README.md). Todo acuerdo o regla
que salga de ahí se propaga a LOGICA_NEGOCIO.md.

### 4.4 Validar datos antes de actuar
Los CSV de estatus del proyecto **mienten**. Antes de tomar cualquier decisión sobre el
avance del lote de CPA Vision, verificar contra el Parquet real, no contra el CSV.

### 4.5 Actualizar ESTADO_ACTUAL.md al cerrar sesión
Antes de terminar una sesión de trabajo larga, dejar en
[docs/ESTADO_ACTUAL.md](docs/ESTADO_ACTUAL.md) dónde quedó todo y cuál es el siguiente paso.
