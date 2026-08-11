"""Consolida TODOS los cpa_batch_metrics_*.csv en la metrica total (txt + csv).

Se ejecuta solo al terminar cada lote; tambien se puede correr a mano:
    .venv/Scripts/python.exe scripts/metricas_totales.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from automation_costos.cpa_vision import actualizar_metricas_totales

if __name__ == "__main__":
    actualizar_metricas_totales(Path("outputs/cpa_vision"))
