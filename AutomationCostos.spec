# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Los subcomandos de main.py importan modulos dentro de funciones; el analisis
# estatico no los detecta, asi que se recolectan explicitamente.
_hidden = collect_submodules("automation_costos")

# customtkinter carga sus temas JSON y sus imagenes en tiempo de ejecucion desde
# el directorio del paquete: hay que incluirlos como datos.
_datas = collect_data_files("customtkinter")
_datas += [
    ("automation_costos\\assets", "automation_costos\\assets"),
    ("templates", "templates"),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Empaquetado en modo ONEDIR (EXE + COLLECT), no onefile.
#
# En onefile el .exe es un contenedor comprimido de ~123 MB que el bootloader extrae
# COMPLETO a una carpeta temporal en CADA arranque, y la borra al cerrar: son 10-40 s de
# pantalla en blanco cada vez que se abre, peor desde unidad de red o con el antivirus
# revisando cada DLL recien extraida. En onedir no hay nada que extraer y arranca en
# segundos. El costo es entregar una carpeta en vez de un archivo suelto, que no cambia
# nada para quien lo recibe porque la distribucion ya va en .zip.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # las librerias las recoge COLLECT, no van dentro del .exe
    name="AutomationCostos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["automation_costos\\assets\\prgx-icon.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AutomationCostos",
)
