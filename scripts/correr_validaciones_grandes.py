"""Corre SOLO la Validación de los proveedores gigantes (Arca, Pepsico).

Cada proveedor se corre en un **proceso propio** (subprocess `main.py cpa-validacion-grande`)
para que la memoria se libere por completo entre uno y otro — clave en estos gigantes. Si
uno falla, se registra y sigue con el siguiente.

Uso:  .venv/Scripts/python.exe scripts/correr_validaciones_grandes.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PY = RAIZ / ".venv" / "Scripts" / "python.exe"
PARQUET = "outputs/cpa_vision/parquet"
OUTDIR = "outputs"
PROVEEDORES = [
    ("391250", "2020-01-01", "2025-12-31", "ARCA CONTINENTAL"),
    ("76034", "2020-01-01", "2025-12-31", "PEPSICO MEXICO"),
]


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    logdir = RAIZ / "outputs" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resumen = logdir / f"validaciones_grandes_{stamp}.txt"

    def anota(texto: str) -> None:
        print(texto, flush=True)
        with resumen.open("a", encoding="utf-8") as fh:
            fh.write(texto + "\n")

    anota(f"=== Validaciones de gigantes (proceso por proveedor) · inicio {_ts()} ===")
    for vendor, ini, fin, nombre in PROVEEDORES:
        log = logdir / f"{vendor}_val_{stamp}.log"
        t0 = time.time()
        anota(f"\n>>> {nombre} [{vendor}] {ini}..{fin}  ·  inicio {_ts()}  ->  {log.name}")
        with log.open("w", encoding="utf-8") as fh:
            code = subprocess.call(
                [
                    str(PY), "-u", "main.py", "cpa-validacion-grande",
                    "--vendor", vendor, "--start", ini, "--end", fin,
                    "--parquet", PARQUET, "--output-dir", OUTDIR,
                ],
                cwd=str(RAIZ),
                stdout=fh,
                stderr=subprocess.STDOUT,
            )
        dur = time.time() - t0
        estado = "OK" if code == 0 else f"FALLO (exit {code})"
        anota(f"    {estado}  ·  {int(dur // 60)}m{int(dur % 60):02d}s")
    anota(f"\n=== fin {_ts()}  ·  resumen: {resumen} ===")


if __name__ == "__main__":
    main()
