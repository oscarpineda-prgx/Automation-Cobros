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
# Modo onedir: PyInstaller deja una CARPETA con el .exe y sus librerias al lado.
APP_DIR = DIST / "AutomationCostos"
EXE = APP_DIR / "AutomationCostos.exe"
VERSION = "1.0"

# Archivos que acompañan al ejecutable dentro del zip.
EXTRAS = ("README.md",)

# Carpetas que el .exe CREA AL USARSE y que NUNCA deben viajar en el zip.
#
# Empaquetado, `config.BASE_DIR` es la carpeta del ejecutable, asi que la aplicacion escribe
# `logs/` y `outputs/` justo al lado. Si se re-empaqueta despues de haberla usado (y con
# `--sin-compilar` es exactamente lo que pasa), esas carpetas entran en el zip.
#
# No es solo basura: `logs/cpavision_state.json` es el estado de sesion de Playwright, con
# las **cookies autenticadas del portal de CPA Vision**. Repartirlo seria entregarle a cada
# auditor la sesion de quien compilo. Tambien viajarian su cola de trabajo, sus rutas y las
# capturas de pantalla de los errores.
NO_DISTRIBUIR = ("logs", "outputs")


def _quien_bloquea(error: OSError) -> str:
    ruta = getattr(error, "filename", None) or "un archivo de dist/"
    return (
        f"\n  Archivo bloqueado: {ruta}"
        "\n\n  Algo lo tiene abierto. Casi siempre es una de estas dos:"
        "\n    · la aplicacion sigue abierta -> cierrala;"
        "\n    · una cola del .exe todavia esta generando un entregable -> espera a que"
        "\n      termine (el proceso hijo escribe su log ahi mismo)."
        "\n\n  Comprobar:  tasklist | findstr AutomationCostos"
    )


def preparar_dist() -> None:
    """Deja `dist/` listo para que PyInstaller pueda reescribirlo. **Antes** de compilar.

    Empaquetado, `config.BASE_DIR` es la carpeta del ejecutable, asi que la aplicacion
    escribe `logs/` y `outputs/` DENTRO de `dist/AutomationCostos/`. PyInstaller, al
    compilar, borra esa carpeta entera — y ahi se topa con archivos que estan en uso.

    Eso es exactamente lo que fallo el 2026-09-10: una cola lanzada desde el `.exe` seguia
    escribiendo `logs/salida_96008_*.log` y el build reventó con `WinError 32`, pero **ya
    habia empezado a borrar** `dist/AutomationCostos`. Un build que se cae a la mitad puede
    dejar la instalacion inservible (paso el 2026-08-25, sin los temas de customtkinter).

    Por eso se comprueba y se limpia **antes**: esos datos de uso no son parte del build,
    no viajan en el zip (`NO_DISTRIBUIR`) y PyInstaller los borraria de todos modos. Si algo
    esta bloqueado, se aborta **sin haber tocado nada** y se dice que archivo es.
    """
    if not APP_DIR.exists():
        return

    # 1. La aplicacion no puede estar corriendo. Windows bloquea el .exe para escritura
    #    mientras se ejecuta, asi que abrirlo en modo append es la prueba directa.
    if EXE.exists():
        try:
            with open(EXE, "ab"):
                pass
        except OSError as exc:
            raise SystemExit(
                "La aplicacion esta abierta y el build la borraria a media ejecucion."
                f"{_quien_bloquea(exc)}"
            )

    # 2. Fuera los datos que el .exe escribio al usarse; son los que suelen estar en uso.
    for carpeta in NO_DISTRIBUIR:
        ruta = APP_DIR / carpeta
        if not ruta.exists():
            continue
        try:
            shutil.rmtree(ruta)
        except OSError as exc:
            raise SystemExit(
                f"No se pudo limpiar {ruta.relative_to(RAIZ)} antes de compilar."
                f"{_quien_bloquea(exc)}"
            )
        print(f"  Limpiado antes de compilar: {ruta.relative_to(RAIZ)} (datos de uso)")


def compilar() -> None:
    preparar_dist()
    print(f"Compilando con {SPEC.name}...")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC)],
        cwd=RAIZ,
        check=True,
    )


def verificar() -> None:
    """Comprueba que el .exe recien compilado esta COMPLETO, antes de empaquetarlo.

    PyInstaller puede dejar fuera una extension en C sin decir nada, y el sintoma no aparece
    hasta que alguien abre la aplicacion. Paso el 2026-09-10: se compilo, se verifico con
    `cpa-salida --help` —que no toca la interfaz— y el .exe murio en la maquina de un auditor
    con "cannot import name '_imaging' from 'PIL'".

    `autocomprobar` importa de verdad la interfaz y las demas piezas criticas, asi que un
    hueco como aquel se detecta aqui y el zip ni se llega a crear.
    """
    print("Verificando que el paquete este completo...")
    resultado = subprocess.run(
        [str(EXE), "autocomprobar"],
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    salida = (resultado.stdout or "") + (resultado.stderr or "")
    for linea in salida.splitlines():
        if linea.strip():
            print(f"  {linea.rstrip()}")
    if resultado.returncode != 0:
        raise SystemExit(
            "\nEl ejecutable esta incompleto: NO se empaqueta.\n"
            "  Arriba dice que pieza falta. Suele arreglarse a~nadiendola a `_hidden` en "
            "AutomationCostos.spec\n  (ver el caso de Pillow, comentado en el propio .spec)."
        )


def empaquetar() -> Path:
    if not EXE.exists():
        raise SystemExit(f"No se encontro el ejecutable: {EXE}")

    nombre = f"AutomationCostos_{VERSION}_{datetime.now():%Y%m%d}.zip"
    destino = DIST / nombre
    print(f"Empaquetando {destino.name}...")

    # En onedir hay que meter la CARPETA completa: el .exe solo no arranca sin `_internal`.
    # Todo cuelga de "AutomationCostos/" para que al descomprimir quede una sola carpeta.
    omitidos = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta in sorted(APP_DIR.rglob("*")):
            if not ruta.is_file():
                continue
            relativa = ruta.relative_to(APP_DIR)
            if relativa.parts[0] in NO_DISTRIBUIR:
                omitidos += 1
                continue
            zf.write(ruta, Path(APP_DIR.name) / relativa)
        for extra in EXTRAS:
            ruta = RAIZ / extra
            if ruta.exists():
                zf.write(ruta, Path(APP_DIR.name) / ruta.name)

    if omitidos:
        print(f"  Fuera del zip: {omitidos} archivo(s) de {'/'.join(NO_DISTRIBUIR)} "
              "(datos de uso, incluida la sesion de CPA Vision).")
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
    verificar()
    empaquetar()


if __name__ == "__main__":
    main()
