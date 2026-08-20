"""Define QUE proveedores hay que ejecutar y en QUE años, leyendo la planeacion de Monica.

Fuente: "Planeacion vs %EDI poblado Soriana.xlsx" (hoja PLANEACION, una fila por
proveedor-año), columna `accion`. El año viene pegado al verbo ("Ejecutar2025"), y coincide
siempre con la columna de año (verificado: 0 discrepancias en las 4,202 filas).

| `accion`               | Que significa                                              | Cruce CPA |
|------------------------|------------------------------------------------------------|-----------|
| **Descargar/Ejecutar** | habia que bajar la CPA de ese año (ya se hizo) y ejecutar   | **SI**    |
| **Ejecutar**           | ejecutar con el EDI que el Compras ya trae de origen        | NO        |
| ninguna                | no se toca: ya terminado, o cobertura EDI >= 90%             | -         |

Reglas que aplica
-----------------
- **Un proveedor puede mezclar verbos entre sus años.** El cruce con CPA se acota a los años
  "Descargar/Ejecutar" (`anios_cruce`); el resto del periodo se ejecuta sin CPA. Dejar que el
  cruce alcance años que el plan no pidio meteria CPA donde el plan no la quiso.
- **Los años pueden traer huecos** (9 proveedores, p. ej. 44586 -> 2020 2021 2023 2024 2025).
  F_COMPRAS se consulta por rango continuo, asi que el ejecutor recorta con `--anios` y el
  titulo del entregable anuncia los años reales. Ver LOGICA_NEGOCIO 13.2.
- **Orden** = `Prioridad_Proveedores_CPA.xlsx`; los que no aparecen ahi van al final.
- **Volumen** = `reg_compras` de la propia planeacion (no se consulta SQL: son 760
  proveedores y el conteo tardaria horas para un dato que el archivo ya trae).
- **Ya entregado** = existe `<entregables>/<prov>_<nombre>/Validacion_*.xlsx`. Se marca, no
  se excluye: la decision de re-ejecutar es del auditor.

Salida: `plan_ejecucion.xlsx`, con las mismas columnas que consume
`scripts/ejecutar_bloque1.py` (prov, nombre, anios, verbos, renglones, anios_cruce) mas
prioridad, periodo y estado.

Uso:
    .venv/Scripts/python.exe scripts/gen_plan_ejecucion.py
    .venv/Scripts/python.exe scripts/gen_plan_ejecucion.py --pendientes   # excluye entregados
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pandas as pd

import config
from automation_costos.utils import formatear_periodo, safe_filename

PLAN = RAIZ / "Planeacion vs %EDI poblado Soriana.xlsx"
PRIORIDAD = RAIZ / "Prioridad_Proveedores_CPA.xlsx"
SALIDA = RAIZ / "plan_ejecucion.xlsx"

COLUMNAS = [
    "anio", "prov", "nombre", "reg_compras", "reg_edi", "pct",
    "ejemplos", "accion", "planeacion", "est2024", "est2025",
]
VERBOS_EJECUTABLES = {"Ejecutar", "Descargar/Ejecutar"}
# El periodo "2025" arrastra a 2026: facturas subidas tarde y pagos con plazo de hasta 90
# dias (acuerdo con Monica, reunion 008). Mismo corte que usa ejecutar_bloque1.
CIERRE_2025 = "2026-03-31"


def cargar_planeacion() -> pd.DataFrame:
    df = pd.read_excel(PLAN, sheet_name="PLANEACION", header=1)
    df.columns = COLUMNAS
    df = df[df["prov"].notna()].copy()
    df["anio"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
    df["prov"] = df["prov"].astype(int)
    df["verbo"] = df["accion"].astype(str).str.replace(r"\d+", "", regex=True).str.strip()
    return df


def prioridades() -> dict[int, int]:
    if not PRIORIDAD.exists():
        return {}
    prio = pd.read_excel(PRIORIDAD, dtype=str)
    return {
        int(r["Proveedor"]): int(r["Prioridad"])
        for _, r in prio.iterrows()
        if pd.notna(r.get("Proveedor")) and pd.notna(r.get("Prioridad"))
    }


def ruta_validacion(prov: int, nombre: str) -> Path:
    base = safe_filename(f"{prov}_{str(nombre).strip()}").rstrip(" .")
    return config.ENTREGABLES_DIR / base / f"Validacion_{base}.xlsx"


def construir() -> pd.DataFrame:
    df = cargar_planeacion()
    ejecutables = df[df["verbo"].isin(VERBOS_EJECUTABLES)]
    prio = prioridades()

    filas = []
    for prov, grupo in ejecutables.groupby("prov"):
        anios = sorted(int(a) for a in grupo["anio"].dropna())
        cruce = sorted(int(r.anio) for r in grupo.itertuples() if r.verbo == "Descargar/Ejecutar")
        nombre = str(grupo["nombre"].iloc[0]).strip()
        entregable = ruta_validacion(prov, nombre)
        filas.append({
            "prov": prov,
            "nombre": nombre,
            "anios": " ".join(map(str, anios)),
            # Los verbos distintos que mezcla el proveedor, para leer de un vistazo por que
            # unos años llevan CPA y otros no.
            "verbos": " + ".join(sorted(set(grupo["verbo"]))),
            "anios_cruce": " ".join(map(str, cruce)),
            "periodo": formatear_periodo(anios),
            "con_huecos": anios != list(range(anios[0], anios[-1] + 1)),
            "inicio": f"{anios[0]}-01-01",
            "fin": CIERRE_2025 if anios[-1] >= 2025 else f"{anios[-1]}-12-31",
            "renglones": int(pd.to_numeric(grupo["reg_compras"], errors="coerce").fillna(0).sum()),
            "pct_edi_min": round(float(pd.to_numeric(grupo["pct"], errors="coerce").min() or 0), 4),
            "prioridad": prio.get(prov, 99999),
            "entregado": entregable.exists(),
        })

    plan = pd.DataFrame(filas)
    return plan.sort_values(["prioridad", "prov"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pendientes", action="store_true", help="Excluye los ya entregados")
    ap.add_argument("--salida", default=str(SALIDA), help="Excel de salida")
    args = ap.parse_args()

    plan = construir()
    total_filas = int(plan["anios"].str.split().apply(len).sum())
    print(f"A EJECUTAR: {len(plan)} proveedores · {total_filas} pares proveedor-año")
    print(f"  con cruce CPA (algun año Descargar/Ejecutar): {int((plan['anios_cruce'] != '').sum())}")
    print(f"  sin CPA (solo Ejecutar)                     : {int((plan['anios_cruce'] == '').sum())}")
    print(f"  con años salteados (se recortan con --anios): {int(plan['con_huecos'].sum())}")
    print(f"  ya entregados                               : {int(plan['entregado'].sum())}")

    if args.pendientes:
        plan = plan[~plan["entregado"]].reset_index(drop=True)
        print(f"\nSolo pendientes: {len(plan)} proveedores")

    print("\nPeriodos mas comunes:")
    print(plan["periodo"].value_counts().head(8).to_string())

    destino = Path(args.salida)
    plan.to_excel(destino, index=False)
    print(f"\nPlan -> {destino}")


if __name__ == "__main__":
    main()
