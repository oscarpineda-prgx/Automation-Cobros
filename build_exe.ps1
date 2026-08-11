# Compila el ejecutable. Un solo camino de build: AutomationCostos.spec.
# El .spec es la unica fuente de verdad del empaquetado (recoge los assets de
# automation_costos, los temas de customtkinter y los imports diferidos de main.py);
# no compilar a mano con --onefile o el .exe sale sin esos datos.
#
# Nota: usar "python -m pip" / "python -m PyInstaller", no pip.exe ni pyinstaller.exe,
# porque los lanzadores del .venv traen la ruta absoluta incrustada.

python -m pip install -r requirements.txt
python scripts/build_release.py
