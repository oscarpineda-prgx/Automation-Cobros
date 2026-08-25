from __future__ import annotations

import os
import sys
from pathlib import Path


# Hay DOS raices distintas y confundirlas rompe el .exe:
#
# - RESOURCE_DIR: los archivos que van EMPAQUETADOS (plantillas, logos). Con PyInstaller
#   viven en la carpeta temporal que el bootloader extrae (`sys._MEIPASS`), no junto al .exe.
# - BASE_DIR: los datos del USUARIO (salidas, logs, sesion de CPA Vision). Tienen que quedar
#   junto al .exe, porque `sys._MEIPASS` se BORRA al cerrar el programa: escribir ahi
#   equivale a perder el trabajo.
#
# En desarrollo (sin congelar) las dos apuntan a la raiz del proyecto y todo sigue igual.
_CONGELADO = getattr(sys, "frozen", False)

RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
BASE_DIR = (
    Path(sys.executable).resolve().parent if _CONGELADO else Path(__file__).resolve().parent
)

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

# Raiz del acervo de CPA Vision. UNA sola fuente de verdad para todo el proyecto: la GUI,
# el .exe, el scraper y los scripts de cobertura. Si cada uno apuntara a su propia carpeta
# el dataset quedaria partido y `gen_lote_monica.py` reportaria como pendientes proveedores
# que en realidad ya se bajaron.
#
# Por convencion los ZIP quedan en la raiz y el Parquet en <raiz>/parquet
# (ver `cpa_descarga.descargar_cpa_proveedor`). Vive fuera del repositorio, junto a los
# entregables, porque son ~5 GB de datos del cliente que no pertenecen al codigo.
# Se puede mover con la variable de entorno CPA_VISION_DIR sin tocar el codigo.
CPA_VISION_DIR = Path(
    os.getenv(
        "CPA_VISION_DIR",
        r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)\cpa_vision",
    )
)
CPA_VISION_DOWNLOAD_DIR = Path(os.getenv("CPA_VISION_DOWNLOAD_DIR", str(CPA_VISION_DIR)))
# Donde viven los entregables por proveedor (una carpeta por proveedor) y el reporte
# consolidado. Es la salida por omisión de la GUI: si apuntara a `outputs/`, la ETAPA 2
# dejaría el paquete del proveedor fuera del acervo y crearía un reporte suelto ahí.
ENTREGABLES_DIR = Path(os.getenv("ENTREGABLES_DIR", str(CPA_VISION_DIR.parent)))
# Carpeta hermana con SOLO los proveedor-año de cobertura EDI < 90% (lo que se entrega como
# complemento). `CPA_VISION_DIR` conserva TODO lo descargado, sin filtro.
CPA_VISION_COMPLEMENTO_DIR = Path(
    os.getenv("CPA_VISION_COMPLEMENTO_DIR", str(CPA_VISION_DIR.parent / "cpa_vision_complemento"))
)
CPA_VISION_PARQUET_DIR = Path(
    os.getenv("CPA_VISION_PARQUET_DIR", str(CPA_VISION_DIR / "parquet"))
)
CPA_VISION_STATE_PATH = Path(
    os.getenv("CPA_VISION_STATE_PATH", str(LOG_DIR / "cpavision_state.json"))
)
# Por omision se descarga SIN ventana. Es lo que quiere el uso real: lotes largos que corren
# de noche o mientras el auditor trabaja en otra cosa, sin que el navegador robe el foco.
# Para ver el navegador (depurar un cambio del portal): CPA_VISION_HEADLESS=0
CPA_VISION_HEADLESS = os.getenv("CPA_VISION_HEADLESS", "1").strip().lower() in {
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


def _crear_carpeta(ruta: Path) -> None:
    """Crea la carpeta sin tumbar el arranque si no se puede.

    Importar `config` no debe poder matar el programa. Si el .exe se copia a una carpeta
    de solo lectura, a una unidad de red caida o a un USB que se quito, un `mkdir` que
    lanza aqui deja la GUI muerta ANTES de poder mostrar un mensaje —y compilada con
    `console=False` el usuario no ve absolutamente nada—. Se falla despues, al escribir,
    donde si hay como avisarle.
    """
    try:
        ruta.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


_crear_carpeta(OUTPUT_DIR)
_crear_carpeta(LOG_DIR)
