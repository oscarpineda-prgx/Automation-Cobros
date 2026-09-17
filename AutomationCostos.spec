# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Los subcomandos de main.py importan modulos dentro de funciones; el analisis
# estatico no los detecta, asi que se recolectan explicitamente.
_hidden = collect_submodules("automation_costos")

# Pillow: hay que pedir sus modulos EXPLICITAMENTE o el .exe no abre la interfaz.
#
# `PIL/Image.py` importa su extension en C dentro de un `try/except ImportError`
# (`from . import _imaging as core`), y el analisis estatico de PyInstaller no la arrastra.
# El resultado es silencioso y enga~noso: los ~76 modulos Python de PIL SI viajan en el
# paquete, pero ninguna de sus 8 extensiones C, asi que `Image.py` se carga y muere en esa
# linea con "cannot import name '_imaging' from 'PIL'". Paso el 2026-09-10 en la maquina
# de un auditor, con el .exe recien compilado.
#
# `collect_dynamic_libs("PIL")` NO sirve aqui: solo busca .dll y no .pyd, porque las
# extensiones de Python se supone que las descubre el grafo de imports. `collect_submodules`
# si las lista (PIL._imaging, PIL._imagingft, PIL._webp, ...) y al declararlas como
# hiddenimports PyInstaller las recoge como binarios.
_hidden += collect_submodules("PIL")

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
    # upx=False a proposito: UPX comprime las DLL y los .pyd, y es una causa conocida de
    # extensiones de Python que dejan de cargar, ademas de falsos positivos de antivirus en
    # equipos corporativos. Hoy no esta instalado y PyInstaller lo omite en silencio, asi
    # que dejarlo en True solo significa que el binario saldria distinto segun la maquina
    # donde se compile. Se fija en False para que el resultado sea el mismo siempre.
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name="AutomationCostos",
)
