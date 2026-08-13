"""Recalcula el objetivo `<90% EDI` y sincroniza `cpa_vision_complemento`.

Reparto de responsabilidades
----------------------------
- **Este script** resuelve QUIENES cumplen la condicion: lee "Planeacion vs %EDI poblado
  Soriana.xlsx", resuelve el RFC de cada proveedor contra SQL y deja el resultado escrito en
  `cpa_vision_complemento/_objetivo_edi_menor_90.csv`. Necesita el repositorio y la base.
- **`automation_costos.complemento_cpa`** hace la copia y el inventario leyendo ese CSV. Eso
  es lo que corre solo al cerrar cada lote de descarga, tambien desde el .exe.

Por eso solo hace falta correr este script cuando **cambia la planeacion** (proveedores o
años nuevos en el objetivo). Las descargas del dia a dia ya se sincronizan solas.

Uso:
    python scripts/complemento_cpa.py                 # recalcula objetivo + sincroniza
    python scripts/complemento_cpa.py --solo-objetivo # solo reescribe el CSV del objetivo
    python scripts/complemento_cpa.py --solo-reporte  # no copia nada, solo informa
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import pandas as pd
import pyodbc

import config
from automation_costos.complemento_cpa import (
    cargar_objetivo,
    guardar_objetivo,
    particiones_elegidas,
    ruta_objetivo,
    sincronizar,
)
from scripts.gen_lote_monica import cargar_objetivo as cargar_planeacion, resolver_rfc

CACHE_RFC = RAIZ / "outputs" / "_rfc_por_proveedor.csv"


def origen_por_defecto() -> Path:
    """La raiz configurada; si aun no se ha movido el acervo, la del proyecto."""
    if config.CPA_VISION_DIR.exists():
        return config.CPA_VISION_DIR
    heredada = RAIZ / "outputs" / "cpa_vision"
    if heredada.exists():
        print(f"AVISO: {config.CPA_VISION_DIR} no existe todavia; se usa {heredada}", flush=True)
        return heredada
    raise SystemExit(f"No se encontro el acervo de CPA Vision ({config.CPA_VISION_DIR})")


def rfcs_de(provs: list[int]) -> dict[int, str]:
    """RFC por numero de proveedor, con cache en disco (la consulta SQL tarda minutos)."""
    cache: dict[int, str] = {}
    if CACHE_RFC.exists():
        previo = pd.read_csv(CACHE_RFC, dtype={"prov": int, "rfc": str})
        cache = dict(zip(previo["prov"], previo["rfc"].fillna("")))
    faltan = [p for p in provs if p not in cache]
    if faltan:
        print(f"Resolviendo RFC de {len(faltan)} proveedores en SQL...", flush=True)
        with pyodbc.connect(config.get_connection_string()) as conn:
            cur = conn.cursor()
            for prov in faltan:
                cache[prov] = resolver_rfc(cur, prov)
        CACHE_RFC.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"prov": list(cache), "rfc": list(cache.values())}).to_csv(CACHE_RFC, index=False)
    return cache


def calcular_objetivo() -> set[tuple[str, int]]:
    """Pares (rfc, año) con cobertura EDI < 90%, segun la planeacion."""
    plan = cargar_planeacion()
    rfcs = rfcs_de(sorted(plan["prov"].unique().tolist()))
    plan["rfc"] = plan["prov"].map(rfcs)
    plan = plan[plan["rfc"].astype(bool)]
    pares = {
        (str(r).strip().upper(), int(a))
        for r, a in zip(plan["rfc"], plan["anio"])
        if pd.notna(a)
    }
    print(f"Objetivo <90% EDI: {len(pares):,} pares RFC-anio ({plan['prov'].nunique()} proveedores)")
    return pares


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origen", default=None, help="Raiz de cpa_vision de donde copiar")
    p.add_argument("--destino", default=str(config.CPA_VISION_COMPLEMENTO_DIR), help="Carpeta del complemento")
    p.add_argument("--solo-objetivo", action="store_true", help="Solo reescribe el CSV del objetivo")
    p.add_argument("--solo-reporte", action="store_true", help="No copia; solo informa")
    args = p.parse_args()

    origen = Path(args.origen) if args.origen else origen_por_defecto()
    destino = Path(args.destino)
    print(f"Origen : {origen}")
    print(f"Destino: {destino}\n")

    pares = calcular_objetivo()
    print(f"Objetivo escrito -> {guardar_objetivo(pares, destino)}\n")
    if args.solo_objetivo:
        return

    if args.solo_reporte:
        elegidas = particiones_elegidas(origen / "parquet")
        objetivo = cargar_objetivo(destino)
        listos = sum(
            1 for r, y in zip(elegidas["rfc"], elegidas["year"])
            if (str(r).strip().upper(), int(y)) in objetivo
        )
        print(f"Ya descargados : {listos:,} pares")
        print(f"Sin descargar  : {len(objetivo) - listos:,} pares")
        return

    inventario = sincronizar(origen, destino)
    if inventario is None:
        return
    inv = pd.read_excel(inventario)
    print(f"\nInventario -> {inventario}")
    print(f"  RFC           : {len(inv):,}")
    print(f"  Pares RFC-anio: {int(inv['# Años'].sum()):,}")
    print(f"  Conceptos     : {int(inv['Conceptos (renglones)'].sum()):,}")
    print(f"  Facturas UUID : {int(inv['Facturas (UUID)'].sum()):,}")


if __name__ == "__main__":
    main()
