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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AutomationCostos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["automation_costos\\assets\\prgx-icon.ico"],
)
