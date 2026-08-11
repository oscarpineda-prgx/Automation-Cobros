"""Piloto del cruce de punta a punta con datos reales de SQL Server + Parquet.

Mide la tasa de cruce real de un proveedor sin pasar por el workbook de Excel
(que es lento y trunca el VLOOKUP), para validar la mecanica del cruce.

Uso:
    python scripts/piloto_cruce.py 5462 2024-01-01 2025-01-01
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation_costos.cruce_cpa import cargar_cpa, cruzar, rfc_de_compras, solo_digitos
from automation_costos.database import fetch_compras

PARQUET = "outputs/cpa_vision/parquet"


def main() -> None:
    vendor, inicio, fin = sys.argv[1], sys.argv[2], sys.argv[3]

    t = time.time()
    print(f"[1/3] Compras de {vendor} {inicio}..{fin} desde SQL...", flush=True)
    compras = fetch_compras(vendor, inicio, fin)
    rfc = rfc_de_compras(compras)
    print(f"      {len(compras):,} renglones · RFC {rfc} · {time.time() - t:.0f}s", flush=True)

    t = time.time()
    barcodes = set(compras["codbarra"].map(solo_digitos)) - {""}
    print(f"[2/3] CPA Vision del RFC (filtrado a {len(barcodes):,} códigos)...", flush=True)
    cpa = cargar_cpa(rfc, PARQUET, barcodes=barcodes)
    print(f"      {len(cpa):,} conceptos · {time.time() - t:.0f}s", flush=True)

    t = time.time()
    print("[3/3] Cruzando...", flush=True)
    resultado = cruzar(compras, cpa)
    print(f"      {time.time() - t:.0f}s\n", flush=True)
    print(resultado.resumen(), flush=True)


if __name__ == "__main__":
    main()
