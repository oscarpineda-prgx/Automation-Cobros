"""Genera/actualiza el Reporte_Diferencias_Consolidado.xlsx de todos los proveedores.

Normalmente NO hace falta correrlo a mano: el reporte se actualiza solo al terminar cada
proveedor y al cerrar un lote. Esto es para regenerarlo a demanda o para reconstruirlo
desde cero si se editaron Validaciones fuera del pipeline.

Uso:
    python scripts/reporte_diferencias.py                    # incremental (usa caché)
    python scripts/reporte_diferencias.py --forzar           # relee TODAS las Validaciones
    python scripts/reporte_diferencias.py --raiz "D:\\otra"   # otra carpeta de entregables
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROYECTO))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from automation_costos.reporte_diferencias import NOMBRE_REPORTE, actualizar_reporte

ENTREGABLES = Path(
    r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)"
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raiz", default=str(ENTREGABLES), help="Carpeta con las carpetas de proveedor")
    p.add_argument("--salida", default=None, help=f"Excel de salida (por omision <raiz>/{NOMBRE_REPORTE})")
    p.add_argument("--forzar", action="store_true", help="Ignorar la cache y releer todo")
    args = p.parse_args()

    inicio = time.time()
    print(f"Entregables: {args.raiz}\n")
    destino = actualizar_reporte(args.raiz, salida=args.salida, forzar=args.forzar)
    print(f"\nReporte -> {destino}")
    print(f"Tiempo  : {time.time() - inicio:.0f}s")


if __name__ == "__main__":
    main()
