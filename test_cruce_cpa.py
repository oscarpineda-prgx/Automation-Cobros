"""Prueba del cruce CPA Vision -> Compras.

Usa `invnbr` y `codbarra` reales del archivo de Compras de Alceda y arma el lado de
CPA Vision imitando su estructura (`Serie` y `Folio` separados), para comprobar que la
normalizacion aguanta los formatos inconsistentes vistos en produccion.

Uso:
    python test_cruce_cpa.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from automation_cobros.cruce_cpa import cruzar, leer_compras

COMPRAS = Path("outputs/Compras_ALC0011111Y9_ALCEDA S. A. DE C. V.xlsx")
FILAS = 400


def simular_cpa(compras: pd.DataFrame) -> pd.DataFrame:
    """Convierte renglones de Compras en conceptos con la forma de CPA Vision."""
    filas = []
    for _, fila in compras.iterrows():
        invnbr = str(fila["invnbr"] or "")
        codbarra = str(fila["codbarra"] or "")
        if not invnbr or not codbarra:
            continue
        # CPA Vision entrega la serie y el folio en columnas separadas y limpias.
        serie = re.sub(r"[^A-Za-z]", "", invnbr)
        folio = re.sub(r"\D", "", invnbr)
        filas.append(
            {
                "Serie": serie,
                "Folio": folio,
                "noIdentificacion": codbarra,
                "Cantidad": "10",
                "Valor Unitario": "25.50",
                "TASA IEPS": "0",
                "IEPS": "0",
                "TASA IVA": "0.16",
                "IVA": "40.80",
                "Total": "295.80",
                "UUID": f"uuid-{folio}",
            }
        )
    return pd.DataFrame(filas).drop_duplicates(subset=["Serie", "Folio", "noIdentificacion"])


def main() -> None:
    if not COMPRAS.exists():
        raise SystemExit(f"No se encontro {COMPRAS}")

    compras = leer_compras(COMPRAS).head(FILAS)
    # El cruce solo llena celdas vacias; el caso real es un Compras con el bloque EDI
    # vacio (hoja Pendientes_EDI). Se vacia para probar el camino de relleno.
    for columna in ("canfac_edi", "ctonto_edi", "ctobto_edi", "impart_edi",
                    "prieps_edi", "imieps_edi", "poriva_edi", "impiva_edi",
                    "totfactura", "uuid", "factem_edi"):
        if columna in compras.columns:
            compras[columna] = None
    cpa = simular_cpa(compras)
    print(f"Compras: {len(compras)} renglones | CPA simulado: {len(cpa)} conceptos\n")

    resultado = cruzar(compras, cpa)
    print(resultado.resumen())

    df = resultado.df
    cruzados = df[df["uuid"].notna()]
    print(f"\nMuestra de renglones cruzados ({len(cruzados)}):")
    columnas = [
        "invnbr",
        "codbarra",
        "factem_edi",
        "canfac_edi",
        "ctonto_edi",
        "ctobto_edi",
        "impart_edi",
        "impiva_edi",
        "impiva_edi_formula",
    ]
    print(cruzados[columnas].head(5).to_string(index=False))

    # factem_edi debe haber quedado igual a fact_empaq en los renglones cruzados.
    ok_factem = (
        pd.to_numeric(cruzados["factem_edi"], errors="coerce")
        .eq(pd.to_numeric(cruzados["fact_empaq"], errors="coerce"))
        .all()
    )
    # ctobto_edi = ctonto_edi x factem_edi ; impart_edi = ctobto_edi x canfac_edi x (1+iva)
    esperado_bruto = 25.50 * pd.to_numeric(cruzados["factem_edi"], errors="coerce")
    ok_bruto = ((cruzados["ctobto_edi"] - esperado_bruto).abs() < 0.01).all()
    esperado_importe = cruzados["ctobto_edi"] * 10 * 1.16
    ok_importe = ((cruzados["impart_edi"] - esperado_importe).abs() < 0.01).all()
    print(f"\nfactem_edi = fact_empaq : {ok_factem}")
    print(f"ctobto_edi correcto     : {ok_bruto}")
    print(f"impart_edi correcto     : {ok_importe}")


if __name__ == "__main__":
    main()
