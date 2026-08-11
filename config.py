from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
LOG_DIR = BASE_DIR / "logs"


# SQL Server connection. These defaults match the information provided for
# SORIANA_PROJECTS. They can be overridden with environment variables.
DB_DRIVER = os.getenv("COSTOS_DB_DRIVER", "ODBC Driver 18 for SQL Server")
DB_SERVER = os.getenv("COSTOS_DB_SERVER", "ATL20AF2222SQ19")
DB_NAME = os.getenv("COSTOS_DB_NAME", "SORIANA_PROJECTS")
# Las compras de 2025 viven en OTRA base del MISMO servidor. F_COMPRAS existe
# en ambas; cada una cubre un rango de años (ver FUENTES_COMPRAS en database.py).
DB_NAME_2025 = os.getenv("COSTOS_DB_NAME_2025", "SORIANA_2025_PROJECTS")
DB_TRUSTED_CONNECTION = os.getenv("COSTOS_DB_TRUSTED_CONNECTION", "yes")
DB_TRUST_SERVER_CERTIFICATE = os.getenv("COSTOS_DB_TRUST_SERVER_CERTIFICATE", "yes")


# Validation output rules.
FOLIO_PREFIX = os.getenv("COSTOS_FOLIO_PREFIX", "11004")
VALIDATION_DIFFERENCE_THRESHOLD = float(
    os.getenv("COSTOS_VALIDATION_DIFFERENCE_THRESHOLD", "1")
)


# CPA Vision / Playwright automation.
CPA_VISION_URL = os.getenv("CPA_VISION_URL", "https://cpavision.mx/")
CPA_VISION_DOWNLOAD_DIR = Path(
    os.getenv("CPA_VISION_DOWNLOAD_DIR", str(OUTPUT_DIR / "cpa_vision"))
)
CPA_VISION_STATE_PATH = Path(
    os.getenv("CPA_VISION_STATE_PATH", str(LOG_DIR / "cpavision_state.json"))
)
CPA_VISION_HEADLESS = os.getenv("CPA_VISION_HEADLESS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "si",
}
CPA_VISION_BROWSER_CHANNEL = os.getenv("CPA_VISION_BROWSER_CHANNEL", "msedge").strip() or None
CPA_VISION_USER = os.getenv("CPA_VISION_USER", "")
CPA_VISION_PASSWORD = os.getenv("CPA_VISION_PASSWORD", "")
CPA_VISION_RFC = os.getenv("CPA_VISION_RFC", "")


def get_connection_string() -> str:
    parts = [
        f"DRIVER={{{DB_DRIVER}}}",
        f"SERVER={DB_SERVER}",
        f"DATABASE={DB_NAME}",
        f"Trusted_Connection={DB_TRUSTED_CONNECTION}",
    ]
    if DB_TRUST_SERVER_CERTIFICATE:
        parts.append(f"TrustServerCertificate={DB_TRUST_SERVER_CERTIFICATE}")
    return ";".join(parts) + ";"


OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
