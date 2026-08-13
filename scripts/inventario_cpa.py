"""Regenera a mano el Inventario_CPA_Vision.xlsx.

Normalmente NO hace falta: se actualiza solo al terminar cada lote de descarga. Esto es
para regenerarlo a demanda (p. ej. tras mover el dataset o si un lote murió a la mitad).

Uso:
    python scripts/inventario_cpa.py
    python scripts/inventario_cpa.py --parquet outputs/cpa_vision/parquet --salida inv.xlsx
"""

from __future__ import annotations

import argparse
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

import config
from automation_costos.inventario_cpa import generar_inventario


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parquet", default=None, help="Carpeta raiz del dataset Parquet")
    p.add_argument("--salida", default=None, help="Excel de salida")
    args = p.parse_args()

    raiz = Path(args.parquet) if args.parquet else config.CPA_VISION_PARQUET_DIR
    if not raiz.exists():
        raise SystemExit(f"No existe el Parquet: {raiz}")

    print(f"Leyendo {raiz} ...", flush=True)
    destino = generar_inventario(raiz, args.salida)
    df = pd.read_excel(destino)
    print(f"\nInventario -> {destino}")
    print(f"  RFC con datos     : {len(df):,}")
    print(f"  Conceptos         : {df['Conceptos (renglones)'].sum():,}")
    print(f"  Facturas (UUID)   : {df['Facturas (UUID)'].sum():,}")
    print(f"  Pares RFC-anio    : {df['# Años'].sum():,}")


if __name__ == "__main__":
    main()
