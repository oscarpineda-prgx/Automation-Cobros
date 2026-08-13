"""Cobertura en CPA Vision del "Bloque 1" prioritario (+ proveedores sueltos).

Responde: de los proveedores de `Bloque 1 Sem 10Ago026.xlsx`, cuales ya tienen su
informacion descargada en el Parquet y cuales no, año por año.

Es el mismo criterio que `gen_lote_monica.py`: la fuente de verdad es el Parquet
(`outputs/cpa_vision/parquet`, particion rfc/year), nunca los CSV ni las metricas. Un
proveedor-año cuenta como descargado solo si su partición existe ahí.

Salida:
  - `cobertura_bloque1.xlsx` con el detalle por proveedor-año.
  - `descarga_bloque1_pendientes.xlsx` en el formato que consume `cpa-batch-vendors`
    (RFC, FECHAS, num, Nombre), listo para lanzar la descarga de lo que falte.

Uso:
    python scripts/cobertura_bloque1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import pandas as pd
import pyodbc

import config
from scripts.gen_lote_monica import cobertura_parquet, resolver_rfc

BLOQUE = Path(
    r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)"
    r"\Bloque 1 Sem 10Ago026.xlsx"
)
# Pedido suelto de Oscar, fuera del archivo del bloque.
EXTRA: list[tuple[int, int]] = [(17222, 2021)]

DETALLE = RAIZ / "cobertura_bloque1.xlsx"
PENDIENTES = RAIZ / "descarga_bloque1_pendientes.xlsx"


def cargar_bloque() -> pd.DataFrame:
    df = pd.read_excel(BLOQUE)
    df.columns = [
        "anio", "prov", "nombre", "reg_compras", "reg_edi", "pct",
        "accion", "planeacion", "est2024", "est2025",
    ]
    df = df[df["prov"].notna()].copy()
    df["prov"] = df["prov"].astype(int)
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["origen"] = "Bloque 1"
    return df[df["anio"].notna()]


def agregar_extra(df: pd.DataFrame) -> pd.DataFrame:
    """Añade los proveedor-año sueltos que no vienen en el archivo del bloque."""
    faltan = [
        {"anio": anio, "prov": prov, "nombre": "(fuera del bloque)", "origen": "Suelto"}
        for prov, anio in EXTRA
        if not ((df["prov"] == prov) & (df["anio"] == anio)).any()
    ]
    return pd.concat([df, pd.DataFrame(faltan)], ignore_index=True) if faltan else df


def main() -> None:
    bloque = agregar_extra(cargar_bloque())
    provs = sorted(bloque["prov"].unique())
    print(f"{len(provs)} proveedores | {len(bloque)} filas proveedor-anio\n", flush=True)

    cob = cobertura_parquet()
    print(f"Parquet: {len(cob)} RFC\n", flush=True)

    rfcs: dict[int, str] = {}
    with pyodbc.connect(config.get_connection_string()) as conn:
        cur = conn.cursor()
        for prov in provs:
            rfcs[prov] = resolver_rfc(cur, prov)

    bloque["RFC"] = bloque["prov"].map(rfcs)
    bloque["descargado"] = [
        bool(rfc) and int(anio) in cob.get(rfc, set())
        for rfc, anio in zip(bloque["RFC"], bloque["anio"])
    ]
    bloque["estado"] = bloque["descargado"].map({True: "Descargado", False: "PENDIENTE"})
    bloque.loc[bloque["RFC"].eq("") | bloque["RFC"].isna(), "estado"] = "SIN RFC (extranjero)"

    _reportar(bloque, provs, rfcs)
    _escribir_pendientes(bloque)

    bloque.sort_values(["prov", "anio"]).to_excel(DETALLE, index=False)
    print(f"\nDetalle por proveedor-anio -> {DETALLE}")


def _reportar(bloque: pd.DataFrame, provs: list[int], rfcs: dict[int, str]) -> None:
    print("=" * 78)
    print("RESUMEN")
    print("=" * 78)
    print(bloque["estado"].value_counts().to_string())
    print()

    por_prov = bloque.groupby("prov").agg(
        anios=("anio", "size"),
        descargados=("descargado", "sum"),
        nombre=("nombre", "first"),
    )
    completos = por_prov[por_prov["anios"] == por_prov["descargados"]]
    parciales = por_prov[(por_prov["descargados"] > 0) & (por_prov["anios"] > por_prov["descargados"])]
    nada = por_prov[por_prov["descargados"] == 0]
    print(f"Proveedores COMPLETOS (todos sus anios) : {len(completos):>3} de {len(provs)}")
    print(f"Proveedores PARCIALES                   : {len(parciales):>3}")
    print(f"Proveedores SIN NADA descargado         : {len(nada):>3}")
    print()

    faltantes = bloque[bloque["estado"] == "PENDIENTE"]
    if not faltantes.empty:
        print("Faltantes por anio:")
        print(faltantes["anio"].value_counts().sort_index().to_string())
        print()
        print("Proveedores con anios pendientes:")
        detalle = (
            faltantes.groupby(["prov", "nombre"])["anio"]
            .apply(lambda s: " ".join(str(int(a)) for a in sorted(s)))
            .reset_index(name="anios_pendientes")
        )
        detalle["RFC"] = detalle["prov"].map(rfcs)
        print(detalle.to_string(index=False))


def _escribir_pendientes(bloque: pd.DataFrame) -> None:
    faltantes = bloque[bloque["estado"] == "PENDIENTE"]
    if faltantes.empty:
        print("\nNo hay nada pendiente: no se genera archivo de descarga.")
        return
    # Se agrupa por RFC, NO por numero de proveedor: CPA Vision descarga por RFC, y aqui
    # hay seis RFC que aparecen con dos numeros distintos (p. ej. Essity como 90738 y 99457).
    # Agrupar por proveedor pediria dos veces la misma descarga —minutos de portal tirados—
    # y la segunda ni siquiera aportaria datos nuevos. Los años se unen entre los duplicados.
    filas = [
        {
            "RFC": rfc,
            "FECHAS": " ".join(str(int(a)) for a in sorted(set(grupo["anio"]))),
            "num": int(grupo["prov"].min()),
            "Nombre": str(grupo["nombre"].iloc[0]).strip(),
            "Proveedores": " ".join(str(p) for p in sorted(set(grupo["prov"]))),
        }
        for rfc, grupo in faltantes.groupby("RFC")
    ]
    out = pd.DataFrame(filas).sort_values("num").reset_index(drop=True)
    out.to_excel(PENDIENTES, index=False)
    print(f"\nLote de descarga ({len(out)} proveedores) -> {PENDIENTES}")
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
