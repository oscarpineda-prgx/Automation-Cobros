"""Genera el Excel maestro de descarga CPA Vision segun el requerimiento de Monica
(correo 2026-08-10): descargar SOLO proveedor+anio con cobertura EDI < 90%.

Fuente del objetivo: "Planeacion vs %EDI poblado Soriana.xlsx", columna `accion`:
  - "Descargar/Ejecutar" -> hay que descargar de CPA ese anio (siempre <90%).
  - "Ejecutar" / "ninguna" -> NO se descarga.

Reglas (ver docs/LOGICA_NEGOCIO.md §13 y docs/reuniones/009-...):
  - Granularidad por ANIO: un proveedor puede necesitar solo algunos anios.
    FECHAS lleva los anios sueltos (ej. "2021 2022 2025"); el scraper agrega
    enero-2026 automatico cuando 2025 esta presente (_MES_MARGEN).
  - Fuente de verdad = parquet (outputs/cpa_vision/parquet, particion rfc/year):
    se excluye todo proveedor-anio ya presente ahi. NUNCA se confia en CSV/metricas.
  - Orden = misma prioridad definida (Prioridad_Proveedores_CPA.xlsx). Los que no
    esten en esa tabla van al final.
  - Proveedores extranjeros (sin RFC mexicano) NO emiten CFDI -> imposible por CPA;
    se reportan aparte, no se incluyen en el lote.

Salida:
  - descarga_monica_pendientes.xlsx  (RFC, FECHAS, num, Nombre, Prioridad) ordenado.
    Se descarga paginando: cpa-batch-vendors --start-index N --batch-size 50.
  - reporte_monica_extranjeros.xlsx  (proveedores sin RFC, para Monica).

Uso:
    .venv/Scripts/python.exe scripts/gen_lote_monica.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd
import pyodbc

import config

PLAN = RAIZ / "Planeacion vs %EDI poblado Soriana.xlsx"
PRIORIDAD = RAIZ / "Prioridad_Proveedores_CPA.xlsx"
PARQUET = config.CPA_VISION_PARQUET_DIR
SALIDA = RAIZ / "descarga_monica_pendientes.xlsx"
EXTRANJEROS = RAIZ / "reporte_monica_extranjeros.xlsx"

# Ventanas validas por base de compras (limite superior real de cada una).
VENTANAS = [
    ("SORIANA_PROJECTS", date(2020, 1, 1), date(2024, 12, 31)),
    ("SORIANA_2025_PROJECTS", date(2025, 1, 1), date(2026, 3, 31)),
]


def cobertura_parquet() -> dict[str, set[int]]:
    """rfc -> {anios ya presentes en parquet}."""
    cob: dict[str, set[int]] = {}
    for d in PARQUET.iterdir():
        if d.is_dir() and d.name.startswith("rfc="):
            rfc = d.name[4:].strip().upper()
            cob[rfc] = {
                int(y.name[5:])
                for y in d.iterdir()
                if y.is_dir() and y.name.startswith("year=")
            }
    return cob


def resolver_rfc(cursor, vendor: int) -> str:
    for dbn, ini, fin in VENTANAS:
        q = f"SELECT TOP (1) cnpj FROM {dbn}.dbo.F_COMPRAS(?, ?, ?) WHERE cnpj IS NOT NULL;"
        try:
            row = cursor.execute(q, str(vendor), ini.isoformat(), fin.isoformat()).fetchone()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! error SQL vendor {vendor}: {exc}")
            row = None
        if row and row[0]:
            return str(row[0]).strip().upper()
    return ""


def cargar_objetivo() -> pd.DataFrame:
    df = pd.read_excel(PLAN, sheet_name="PLANEACION", header=1)
    df.columns = [
        "anio", "prov", "nombre", "reg_compras", "reg_edi", "pct",
        "ejemplos", "accion", "planeacion", "est2024", "est2025",
    ]
    df = df[df["prov"].notna()].copy()
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["prov"] = df["prov"].astype(int)
    df["accion_base"] = df["accion"].astype(str).str.replace(r"\d+", "", regex=True).str.strip()
    return df[df["accion_base"] == "Descargar/Ejecutar"].copy()


def main() -> None:
    cob = cobertura_parquet()
    print(f"Parquet: {len(cob)} RFC")

    de = cargar_objetivo()
    print(f"Objetivo Descargar/Ejecutar: {len(de)} filas, {de['prov'].nunique()} proveedores")

    prio = pd.read_excel(PRIORIDAD, dtype=str)
    prio_por_prov = {
        int(r["Proveedor"]): int(r["Prioridad"])
        for _, r in prio.iterrows()
        if pd.notna(r["Proveedor"]) and pd.notna(r["Prioridad"])
    }

    filas: list[dict] = []
    extranjeros: list[dict] = []
    with pyodbc.connect(config.get_connection_string()) as conn:
        cur = conn.cursor()
        for prov, grupo in de.groupby("prov"):
            nombre = str(grupo["nombre"].iloc[0]).strip()
            rfc = resolver_rfc(cur, prov)
            if not rfc:
                extranjeros.append({"prov": prov, "nombre": nombre,
                                    "anios_bajo90": " ".join(map(str, sorted(grupo["anio"].tolist())))})
                continue
            presentes = cob.get(rfc, set())
            faltan = sorted(a for a in grupo["anio"].tolist() if int(a) not in presentes)
            if not faltan:
                continue  # todos los anios <90% de este proveedor ya estan en parquet
            filas.append({
                "RFC": rfc,
                "FECHAS": " ".join(str(a) for a in faltan),
                "num": prov,
                "Nombre": nombre,
                "Prioridad": prio_por_prov.get(prov, 99999),
            })

    out = pd.DataFrame(filas).sort_values(["Prioridad", "num"]).reset_index(drop=True)
    out.to_excel(SALIDA, index=False)
    print(f"\nLote maestro -> {SALIDA}")
    print(f"  proveedores a descargar: {len(out)}")
    print(f"  filas prov-anio cubiertas: {int(out['FECHAS'].str.split().apply(len).sum())}")

    ext = pd.DataFrame(extranjeros)
    ext.to_excel(EXTRANJEROS, index=False)
    print(f"\nExtranjeros sin RFC (para Monica) -> {EXTRANJEROS}  ({len(ext)} proveedores)")


if __name__ == "__main__":
    main()
