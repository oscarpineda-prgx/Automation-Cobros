"""Descarga de un proveedor desde CPA Vision: de RFC a dataset Parquet.

Orquesta el paso *previo* al pipeline (`pipeline.generar_salida_proveedor`), el
equivalente por-proveedor de `cpa-batch-vendors` pensado para la GUI:

    RFC + periodo → solicitud en el portal (Playwright) → ZIP → dataset Parquet

La lógica del portal vive en `cpa_vision.py` y la conversión en `cpa_parquet.py`; aquí
solo se encadenan, sin tocar Playwright ni PyArrow directamente. Así la GUI queda delgada
(solo dispara esta función en un hilo) y la lógica es reutilizable y testeable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from automation_costos.cpa_parquet import zip_to_parquet_dataset
from automation_costos.cpa_vision import CPAVisionSettings, request_download_and_wait


@dataclass(slots=True)
class ResultadoDescarga:
    rfc: str
    request_id: str
    zip_path: Path
    parquet_root: Path
    filas: int
    archivos_parquet: int


def _anios(start_date: str, end_date: str) -> range:
    """Rango de años [inicio..fin] que cubre el periodo pedido."""
    inicio = pd.to_datetime(start_date).year
    fin = pd.to_datetime(end_date).year
    return range(inicio, fin + 1)


def descargar_cpa_proveedor(
    rfc: str,
    start_date: str,
    end_date: str,
    *,
    parquet_root: Path | str,
    username: str,
    password: str,
    download_dir: Path | str | None = None,
    settings: CPAVisionSettings | None = None,
    poll_seconds: int = 20,
    max_wait_minutes: int = 420,
    log: Callable[[str], None] = print,
) -> ResultadoDescarga:
    """Solicita la descarga del proveedor en CPA Vision y la deja lista en Parquet.

    Convención del proyecto: los ZIP se guardan junto al dataset (en `parquet_root.parent`,
    p. ej. `outputs/cpa_vision/` con el Parquet en `outputs/cpa_vision/parquet`), para que
    el pipeline pueda copiarlos como soporte más tarde (`pipeline.copiar_soportes_cpa`).

    Las credenciales las provee quien llama (la GUI las pide al auditor); nunca se guardan
    en código ni en disco por esta función.
    """
    rfc = (rfc or "").strip().upper()
    if not rfc:
        raise ValueError("RFC es requerido para descargar de CPA Vision.")
    if not (username and password):
        raise ValueError("Usuario y contraseña de CPA Vision son requeridos.")

    parquet_root = Path(parquet_root)
    download_dir = Path(download_dir) if download_dir else parquet_root.parent

    settings = settings or CPAVisionSettings()
    settings.download_dir = download_dir

    anios = _anios(start_date, end_date)
    log(
        f"[1/2] Solicitando descarga en CPA Vision · RFC {rfc} · "
        f"años {anios.start}-{anios.stop - 1}..."
    )
    log("      Se abre el portal; puede tardar mientras el sitio genera el ZIP.")
    zip_path = request_download_and_wait(
        settings,
        username=username,
        password=password,
        rfc=rfc,
        years=anios,
        poll_seconds=poll_seconds,
        max_wait_minutes=max_wait_minutes,
        keep_open=False,
    )
    # El nombre del ZIP empieza con el id de solicitud: "<request_id>_...zip".
    request_id = zip_path.name.split("_", 1)[0]
    log(f"      ZIP descargado: {zip_path.name} (request {request_id})")

    log("[2/2] Convirtiendo el ZIP a dataset Parquet...")
    result = zip_to_parquet_dataset(zip_path, parquet_root, rfc=rfc, request_id=request_id)
    log(
        f"      {result.rows:,} filas en {result.files} archivos Parquet "
        f"(de {result.csv_files} CSV) → {parquet_root}"
    )

    return ResultadoDescarga(
        rfc=rfc,
        request_id=request_id,
        zip_path=zip_path,
        parquet_root=parquet_root,
        filas=result.rows,
        archivos_parquet=result.files,
    )
