"""Actualiza el archivo de Monica con la cobertura EDI DESPUES del cruce CPA y el
beneficio, SOLO para los proveedores que ya quedaron descargados (RFC en parquet).

Reusa la logica validada de scripts/beneficio_cpa.py (antes/despues por proveedor-anio,
memoria acotada anio por anio) y la mezcla contra la estructura del plan (una fila por
proveedor-anio). Los proveedores aun no descargados se dejan sin columnas nuevas.

Salida: "Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx" con columnas extra:
    edi_despues, pct_despues, mejora_pp, renglones_ganados.

Uso:
    .venv/Scripts/python.exe scripts/actualizar_plan_beneficio.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd
import pyodbc

import config
from scripts.beneficio_cpa import beneficio_proveedor
from scripts.gen_lote_monica import cobertura_parquet, resolver_rfc

PLAN = RAIZ / "Planeacion vs %EDI poblado Soriana.xlsx"
SALIDA = RAIZ / "Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx"


def cargar_plan() -> pd.DataFrame:
    df = pd.read_excel(PLAN, sheet_name="PLANEACION", header=1)
    df.columns = ["anio", "prov", "nombre", "reg_compras", "reg_edi", "pct",
                  "ejemplos", "accion", "planeacion", "est2024", "est2025"]
    df = df[df["prov"].notna()].copy()
    df["prov"] = df["prov"].astype(int)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    return df


def main() -> None:
    plan = cargar_plan()
    cob = cobertura_parquet()
    print(f"Plan: {plan['prov'].nunique()} proveedores | Parquet: {len(cob)} RFC")

    # Proveedores del plan cuyo RFC ya esta en parquet = "ya listos".
    listos: list[int] = []
    with pyodbc.connect(config.get_connection_string()) as conn:
        cur = conn.cursor()
        for prov in sorted(plan["prov"].unique()):
            rfc = resolver_rfc(cur, prov)
            if rfc and rfc in cob:
                listos.append(prov)
    print(f"Proveedores ya descargados (RFC en parquet): {len(listos)}")

    filas = []
    for i, prov in enumerate(listos, 1):
        try:
            g = beneficio_proveedor(prov)
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}/{len(listos)}] {prov} ERROR: {exc}")
            continue
        if not g.empty:
            filas.append(g)
            t = g[["reg_compras", "edi_antes", "edi_despues"]].sum()
            print(f"[{i}/{len(listos)}] {prov} {g['nombre'].iloc[0][:30]:30} "
                  f"{t.edi_antes/t.reg_compras:6.1%} -> {t.edi_despues/t.reg_compras:6.1%}")

    if not filas:
        print("Sin datos.")
        return

    ben = pd.concat(filas, ignore_index=True)[["prov", "anio", "edi_despues"]]
    ben["anio"] = ben["anio"].astype("Int64")

    out = plan.merge(ben, on=["prov", "anio"], how="left")
    out["estatus_cpa"] = out["edi_despues"].notna().map({True: "Descargado", False: "Pendiente"})
    out["pct_despues"] = out["edi_despues"] / out["reg_compras"]
    out["mejora_pp"] = out["pct_despues"] - out["pct"]
    out["renglones_ganados"] = out["edi_despues"] - out["reg_edi"]

    # Proveedor-anio sin descargar: no hay beneficio todavia, pero las columnas no se dejan
    # vacias. Se arrastra el estado actual (edi_despues = reg_edi, pct_despues = pct) y el
    # beneficio queda en 0. Asi el archivo se puede sumar/filtrar sin huecos.
    pend = out["estatus_cpa"] == "Pendiente"
    out.loc[pend, "edi_despues"] = out.loc[pend, "reg_edi"]
    out.loc[pend, "pct_despues"] = out.loc[pend, "pct"]
    out.loc[pend, "mejora_pp"] = 0
    out.loc[pend, "renglones_ganados"] = 0

    out.to_excel(SALIDA, index=False)
    print(f"\nActualizado -> {SALIDA}")
    print(f"  filas con beneficio real: {int((~pend).sum())}"
          f" | filas en 0 (pendientes de descarga): {int(pend.sum())}")


if __name__ == "__main__":
    main()
