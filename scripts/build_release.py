"""Compila el ejecutable con PyInstaller y lo empaqueta en un .zip distribuible.

Uso:
    python scripts/build_release.py
    python scripts/build_release.py --sin-compilar   # solo re-empaqueta dist/

Deja `dist/AutomationCostos.exe` y `dist/AutomationCostos_<version>_<fecha>.zip`.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SPEC = RAIZ / "AutomationCostos.spec"
DIST = RAIZ / "dist"
EXE = DIST / "AutomationCostos.exe"
VERSION = "1.0"

# Archivos que acompañan al ejecutable dentro del zip.
EXTRAS = ("README.md",)


def compilar() -> None:
    print(f"Compilando con {SPEC.name}...")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC)],
        cwd=RAIZ,
        check=True,
    )


def empaquetar() -> Path:
    if not EXE.exists():
        raise SystemExit(f"No se encontro el ejecutable: {EXE}")

    nombre = f"AutomationCostos_{VERSION}_{datetime.now():%Y%m%d}.zip"
    destino = DIST / nombre
    print(f"Empaquetando {destino.name}...")

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(EXE, EXE.name)
        for extra in EXTRAS:
            ruta = RAIZ / extra
            if ruta.exists():
                zf.write(ruta, ruta.name)

    tamano = destino.stat().st_size / 1_048_576
    print(f"Listo: {destino}  ({tamano:.1f} MB)")
    return destino


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sin-compilar",
        action="store_true",
        help="Omite PyInstaller y solo re-empaqueta lo que ya esta en dist/",
    )
    args = parser.parse_args()

    if not args.sin_compilar:
        if shutil.which("pyinstaller") is None:
            print("Aviso: pyinstaller no esta en el PATH; se invoca como modulo de Python.")
        compilar()
    empaquetar()


if __name__ == "__main__":
    main()
