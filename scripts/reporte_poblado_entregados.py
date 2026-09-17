"""Cobertura EDI antes/despues del cruce, SOLO de los proveedores ya entregados.

Responde la pregunta de Oscar: "el proveedor X tenia las columnas al 70% y con el cruce
quedo en 90%". No calcula nada nuevo: **combina dos archivos que ya existen**, y por eso
tarda segundos en vez de las ~7 horas que costaria recalcular (medido: el cuello no es SQL
—0.2 s por consulta— sino cargar el Parquet de CPA, ~25 s por proveedor-anio).

Las dos fuentes
---------------
1. `Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx` — lo produce
   `actualizar_plan_beneficio.py` y trae, por proveedor-anio, la cobertura ANTES (`reg_edi`
   / `pct`) y DESPUES (`edi_despues` / `pct_despues`) de cruzar contra el acervo CPA.
2. `Historico_Cruce_CPA.parquet` — lo escribe `metricas_cruce` en CADA ejecucion real del
   pipeline, con el % de cruce medido sobre el entregable que se genero.

⚠️ LIMITE IMPORTANTE
--------------------
El "despues" de la fuente 1 es una **simulacion con corte al 2026-08-11**, que es cuando se
corrio por ultima vez. Para un proveedor cuyo RFC se descargo despues de esa fecha (el lote
del 15-ago trajo 23), la mejora que aparece aqui esta **subestimada**: se midio contra un
Parquet que todavia no tenia sus CFDI. La columna `fuente` lo distingue, y los proveedores
con ejecucion real llevan ademas su % de cruce medido.

Para numeros al dia hay que re-correr, en este orden:
    .venv/Scripts/python.exe scripts/beneficio_cpa.py
    .venv/Scripts/python.exe scripts/actualizar_plan_beneficio.py

Uso:
    .venv/Scripts/python.exe scripts/reporte_poblado_entregados.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd

from automation_costos import ejecutor, metricas_cruce
import config

PLAN = RAIZ / "datos" / "planeacion" / "Planeacion vs %EDI poblado Soriana_ACTUALIZADO.xlsx"
SALIDA = RAIZ / "outputs" / "Poblado_EDI_entregados.xlsx"
#: Fecha en que se calculo el "despues" del plan. Todo lo descargado despues esta subestimado.
CORTE_PLAN = "2026-08-11"


def _por_proveedor(detalle: pd.DataFrame) -> pd.DataFrame:
    """Suma los años de cada proveedor y recalcula los porcentajes sobre el total.

    Los porcentajes se recalculan, NO se promedian: promediar el % de un año con 100
    renglones y el de otro con 100,000 daria un numero que no significa nada.
    """
    g = detalle.groupby(["prov", "nombre"], as_index=False)[
        ["reg_compras", "reg_edi", "edi_despues", "renglones_ganados"]
    ].sum()
    g["pct_antes"] = g["reg_edi"] / g["reg_compras"]
    g["pct_despues"] = g["edi_despues"] / g["reg_compras"]
    g["mejora_pp"] = g["pct_despues"] - g["pct_antes"]
    return g.sort_values("mejora_pp", ascending=False)


def _vigencia(provs: pd.Series) -> pd.Series:
    """Marca si la cifra de cada proveedor es de fiar o esta subestimada.

    El "despues" del plan se calculo el {CORTE_PLAN} contra el Parquet de ese dia. Si los
    CFDI de un proveedor entraron al acervo DESPUES, su mejora real es mayor que la que
    aparece aqui — y quien lea el reporte tiene que saberlo antes de sacar conclusiones.
    Se resuelve mirando la fecha de la particion `rfc=<RFC>` en el Parquet.
    """
    from automation_costos.database import resolver_rfc

    raiz = config.CPA_VISION_PARQUET_DIR
    corte = pd.Timestamp(CORTE_PLAN)
    etiquetas = []
    print(f"Resolviendo el RFC de {len(provs)} proveedores para fechar su descarga...")
    for prov in provs:
        try:
            rfc = resolver_rfc(str(int(prov)), "2020-01-01", ejecutor.CIERRE_2025)
            carpeta = raiz / f"rfc={rfc}" if rfc else None
            if carpeta is None or not carpeta.exists():
                etiquetas.append("sin datos en el Parquet")
            elif pd.Timestamp.fromtimestamp(carpeta.stat().st_mtime) > corte:
                etiquetas.append("SUBESTIMADO (descargado despues del corte)")
            else:
                etiquetas.append("al dia")
        except Exception:  # noqa: BLE001 — un RFC que no resuelve no puede tumbar el reporte
            etiquetas.append("no se pudo determinar")
    return pd.Series(etiquetas, index=provs.index)


def main() -> None:
    if not PLAN.exists():
        raise SystemExit(f"No existe {PLAN.name}. Corre antes actualizar_plan_beneficio.py")

    entregados = set(ejecutor.entregados(config.ENTREGABLES_DIR))
    print(f"Proveedores con entregable en disco: {len(entregados)}")

    plan = pd.read_excel(PLAN)
    plan["prov"] = pd.to_numeric(plan["prov"], errors="coerce")
    detalle = plan[plan["prov"].isin(entregados)].copy()
    print(f"De esos, con datos en la planeacion: {detalle['prov'].nunique()} "
          f"({len(detalle)} filas proveedor-anio)")

    faltan = sorted(entregados - set(detalle["prov"].dropna().astype(int)))
    if faltan:
        print(f"Sin datos de beneficio (no estan en la planeacion): {faltan}")

    resumen = _por_proveedor(detalle)

    # Se marca quien tiene ejecucion REAL medida y quien solo la simulacion del plan.
    historico = config.ENTREGABLES_DIR / metricas_cruce.NOMBRE_HISTORICO
    if historico.exists():
        hist = pd.read_parquet(historico)
        hist["prov"] = pd.to_numeric(hist["Proveedor"], errors="coerce")
        # La ejecucion mas reciente de cada proveedor manda.
        ultima = hist.sort_values("Fecha").groupby("prov", as_index=False).last()
        resumen = resumen.merge(
            ultima[["prov", "Fecha", "% de cruce", "Celdas vacias rellenadas"]],
            on="prov", how="left",
        ).rename(columns={"Fecha": "ejecutado_el", "% de cruce": "pct_cruce_medido"})
    else:
        resumen["ejecutado_el"] = pd.NaT
        resumen["pct_cruce_medido"] = pd.NA

    resumen["fuente"] = resumen["ejecutado_el"].notna().map(
        {True: "ejecucion real medida", False: f"simulacion del plan (corte {CORTE_PLAN})"}
    )
    resumen["vigencia"] = _vigencia(resumen["prov"])

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(SALIDA, engine="openpyxl") as xls:
        resumen.to_excel(xls, sheet_name="Resumen por proveedor", index=False)
        detalle.sort_values(["prov", "anio"]).to_excel(
            xls, sheet_name="Detalle por anio", index=False
        )
        pd.DataFrame(
            [
                ("Generado", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ("Proveedores entregados", len(entregados)),
                ("Proveedores en el reporte", int(resumen["prov"].nunique())),
                ("Corte del calculo 'despues'", CORTE_PLAN),
                ("Advertencia", "Lo descargado despues del corte esta SUBESTIMADO; "
                                "re-correr beneficio_cpa.py + actualizar_plan_beneficio.py"),
                ("Fuente 1", PLAN.name),
                ("Fuente 2", metricas_cruce.NOMBRE_HISTORICO),
            ],
            columns=["Concepto", "Valor"],
        ).to_excel(xls, sheet_name="Notas", index=False)

    total_reg = int(resumen["reg_compras"].sum())
    print(f"\nGlobal: {total_reg:,} renglones · "
          f"antes {resumen['reg_edi'].sum() / total_reg:.1%} -> "
          f"despues {resumen['edi_despues'].sum() / total_reg:.1%} "
          f"(+{int(resumen['renglones_ganados'].sum()):,} renglones)")
    print(f"Listo -> {SALIDA}")


if __name__ == "__main__":
    main()
