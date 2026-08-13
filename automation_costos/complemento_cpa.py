"""Mantiene `cpa_vision_complemento`: solo los proveedor-año con cobertura EDI < 90%.

Dos carpetas hermanas con propósito distinto, y ninguna sustituye a la otra:

- `cpa_vision`             → TODO lo descargado, sin filtro. Es el acervo completo.
- `cpa_vision_complemento` → únicamente los proveedor-año que la planeación marca como
                             `Descargar/Ejecutar`, es decir los que traen menos del 90% de
                             cobertura EDI. Es lo que se entrega como complemento.

Cada una lleva su propio `Inventario_CPA_Vision.xlsx`.

Por qué el objetivo se guarda en un archivo
-------------------------------------------
Saber qué proveedor-año está por debajo del 90% requiere el Excel de planeación (que vive en
el repositorio) y resolver el RFC de cada proveedor contra SQL. **El .exe no tiene ninguna de
las dos cosas**: no se empaqueta el Excel (cambia con el tiempo, congelarlo sería peor) y no
se quiere una consulta SQL de minutos al cerrar cada lote.

Por eso el objetivo se persiste como `_objetivo_edi_menor_90.csv` DENTRO de la carpeta de
complemento. Lo escribe `scripts/complemento_cpa.py` (que sí tiene Excel y SQL) y lo lee este
módulo. Como vive junto a los entregables en la unidad de red, el .exe siempre lo alcanza.
Si el archivo no existe, no se inventa nada: se avisa y no se copia (ver `sincronizar`).

Deduplicación
-------------
Un mismo (rfc, año) puede tener varias descargas con años solapados. Se copia UNA sola: la de
mayor cobertura, con el mismo criterio de `cruce_cpa._CTE_ELEGIDO`. Así el complemento no
arrastra duplicados y su inventario no sobrecuenta.

Es INCREMENTAL: lo ya copiado se omite, así que se puede correr cuantas veces haga falta.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import pandas as pd

import config
from automation_costos.inventario_cpa import generar_inventario

NOMBRE_OBJETIVO = "_objetivo_edi_menor_90.csv"


def ruta_objetivo(destino: Path | None = None) -> Path:
    base = Path(destino) if destino else config.CPA_VISION_COMPLEMENTO_DIR
    return base / NOMBRE_OBJETIVO


def guardar_objetivo(pares: set[tuple[str, int]], destino: Path | None = None) -> Path:
    """Persiste los pares (rfc, año) del objetivo para que el .exe pueda leerlos."""
    ruta = ruta_objetivo(destino)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(sorted(pares), columns=["rfc", "anio"])
    df.to_csv(ruta, index=False)
    return ruta


def cargar_objetivo(destino: Path | None = None) -> set[tuple[str, int]]:
    """Los pares (rfc, año) con cobertura EDI < 90%. Vacío si no se ha generado."""
    ruta = ruta_objetivo(destino)
    if not ruta.exists():
        return set()
    df = pd.read_csv(ruta, dtype={"rfc": str})
    return {(str(r).strip().upper(), int(a)) for r, a in zip(df["rfc"], df["anio"])}


def particiones_elegidas(parquet_root: Path) -> pd.DataFrame:
    """(rfc, year, request_id) quedándose con UNA sola descarga por (rfc, año)."""
    import duckdb

    patron = f"{Path(parquet_root).as_posix()}/**/*.parquet"
    with duckdb.connect() as con:
        con.execute("PRAGMA disable_progress_bar")
        try:
            con.execute("SET memory_limit='4GB'")
        except Exception:  # noqa: BLE001
            pass
        df = con.execute(
            "SELECT rfc, year, request_id, count(*) AS filas "
            "FROM read_parquet(?, hive_partitioning = 1) GROUP BY 1, 2, 3",
            [patron],
        ).df()

    df["year"] = df["year"].astype(int)
    df["_anios"] = df.groupby(["rfc", "request_id"])["year"].transform("nunique")
    df = df.sort_values(
        ["rfc", "year", "_anios", "filas", "request_id"],
        ascending=[True, True, False, False, True],
    )
    return df.drop_duplicates(["rfc", "year"], keep="first")


def _copiar_zips(origen: Path, destino: Path, request_ids: set[str]) -> tuple[int, int]:
    """El ZIP se identifica por el `request_id` con el que arranca su nombre.

    Un ZIP puede traer más años que los del objetivo (se solicitó por rango): se copia igual,
    es el soporte literal de esa descarga y recortarlo no es posible.
    """
    carpeta = destino / "soportes_zip"
    carpeta.mkdir(parents=True, exist_ok=True)
    copiados = omitidos = 0
    for zip_path in origen.glob("*.zip"):
        if zip_path.name.split("_", 1)[0] not in request_ids:
            continue
        final = carpeta / zip_path.name
        if final.exists():
            omitidos += 1
            continue
        shutil.copy2(zip_path, final)
        copiados += 1
    return copiados, omitidos


def sincronizar(
    origen: Path | str | None = None,
    destino: Path | str | None = None,
    *,
    log: Callable[[str], None] = print,
) -> Path | None:
    """Copia lo que falte al complemento y regenera SU inventario. Devuelve el inventario."""
    origen = Path(origen) if origen else config.CPA_VISION_DIR
    destino = Path(destino) if destino else config.CPA_VISION_COMPLEMENTO_DIR
    parquet_origen = origen / "parquet"
    if not parquet_origen.exists():
        log(f"[Complemento] no hay Parquet en {parquet_origen}; nada que hacer")
        return None

    objetivo = cargar_objetivo(destino)
    if not objetivo:
        log(
            f"[Complemento] falta {ruta_objetivo(destino).name}; no se copia nada. "
            "Genéralo con: python scripts/complemento_cpa.py"
        )
        return None

    elegidas = particiones_elegidas(parquet_origen)
    disponibles = elegidas[
        [(str(r).strip().upper(), int(y)) in objetivo for r, y in zip(elegidas["rfc"], elegidas["year"])]
    ]
    log(
        f"[Complemento] objetivo {len(objetivo):,} pares · ya descargados {len(disponibles):,} · "
        f"faltan por descargar {len(objetivo) - len(disponibles):,}"
    )

    copiadas = omitidas = 0
    for fila in disponibles.itertuples(index=False):
        rel = Path(f"rfc={fila.rfc}") / f"year={fila.year}" / f"request_id={fila.request_id}"
        src, dst = parquet_origen / rel, destino / "parquet" / rel
        if not src.exists():
            continue
        if dst.exists():
            omitidas += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        copiadas += 1

    zips_nuevos, zips_previos = _copiar_zips(origen, destino, set(disponibles["request_id"].astype(str)))
    log(
        f"[Complemento] particiones: {copiadas} nuevas, {omitidas} ya estaban · "
        f"ZIP: {zips_nuevos} nuevos, {zips_previos} ya estaban"
    )

    inventario = generar_inventario(destino / "parquet", destino / "Inventario_CPA_Vision.xlsx")
    log(f"[Complemento] inventario actualizado: {inventario}")
    return inventario


def actualizar_complemento(
    origen: Path | str | None = None, *, log: Callable[[str], None] = print
) -> Path | None:
    """Igual que `sincronizar`, pero NUNCA lanza.

    Se llama al cerrar un lote de descarga, aparte del inventario general. Si falla (Excel
    abierto, permisos, DuckDB sin memoria, objetivo sin generar) no debe tirar un lote que
    costó horas ni hacer creer que las descargas no se hicieron: se avisa y se sigue.
    """
    try:
        return sincronizar(origen, log=log)
    except Exception as exc:  # noqa: BLE001
        log(f"[Complemento] no se pudo actualizar ({exc})")
        return None
