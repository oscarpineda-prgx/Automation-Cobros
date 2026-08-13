"""Ejecuta el Bloque 1: compras -> cruce -> recálculo -> Validación, proveedor por proveedor.

Lee `plan_ejecucion_bloque1.xlsx` (que sale de la columna `accion` del archivo del bloque)
y corre solo los proveedores y años que ahí se piden. No inventa alcance: si un año no
aparece en el plan, no se ejecuta.

Decisiones que aplica
---------------------
- **Periodo**: del 1-ene del primer año pedido al 31-dic del último. Si el último año es
  2025, el corte se extiende al **31-mar-2026**: el periodo "2025" de la auditoría arrastra
  a 2026 por facturas subidas tarde y pagos con plazo de hasta 90 días (acuerdo con Mónica
  del 2026-08-05, reunión 008).
- **RFC compartidos**: cada número de proveedor se ejecuta por separado aunque comparta RFC
  con otro. Es lo que indicó Mónica: se usa la misma descarga del RFC para ambos números y
  el cruce liga solo lo que corresponde a cada uno por factura + código de barras. Medido
  antes de ejecutar: los 6 pares tienen CERO facturas en común, ni siquiera colapsando a
  solo dígitos, asi que no hay forma de que un número jale los CFDI del otro.
- **Proveedores grandes**: por encima de `UMBRAL_GRANDE` renglones se usa el camino por
  trimestres (`cpa-compras-grande` + `cpa-validacion-grande`), que no carga el periodo
  completo en memoria. Es el que sobrevivió con Arca y Pepsico.

Cada proveedor corre en su **propio proceso**, para que la memoria se libere entre uno y
otro y para que un fallo no arrastre al resto. Es RESUMIBLE: si la Validación ya existe,
se omite.

Uso:
    python scripts/ejecutar_bloque1.py                 # todos
    python scripts/ejecutar_bloque1.py --solo 386029   # uno, para probar
    python scripts/ejecutar_bloque1.py --listar        # no ejecuta, solo muestra el plan
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import pandas as pd

import config
from automation_costos.utils import safe_filename

PY = RAIZ / ".venv" / "Scripts" / "python.exe"
PLAN = RAIZ / "plan_ejecucion_bloque1.xlsx"
SALIDA = Path(
    r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)"
)
# Nestlé (1.3M) salió bien por el camino normal en 32 min; Arca (11.5M) y Pepsico (10.1M)
# solo salieron por trimestres. El corte se pone con holgura entre ambos.
UMBRAL_GRANDE = 1_500_000
CIERRE_2025 = "2026-03-31"


def periodo(anios: list[int]) -> tuple[str, str]:
    ini = f"{min(anios)}-01-01"
    fin = CIERRE_2025 if max(anios) >= 2025 else f"{max(anios)}-12-31"
    return ini, fin


def _anios_texto(valor) -> str:
    """Normaliza una celda de años a "2020 2021 ...", sin decimales sueltos de Excel."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return " ".join(str(int(float(a))) for a in str(valor).split())


def cargar_plan() -> pd.DataFrame:
    df = pd.read_excel(PLAN)
    df["anios_lista"] = df["anios"].astype(str).str.split().apply(lambda s: [int(a) for a in s])
    df["renglones"] = pd.to_numeric(df["renglones"], errors="coerce").fillna(0)
    df[["inicio", "fin"]] = df["anios_lista"].apply(lambda a: pd.Series(periodo(a)))
    df["grande"] = df["renglones"] > UMBRAL_GRANDE
    # `anios_cruce` trae los años marcados "Descargar/Ejecutar", que son los unicos que
    # llevan cruce con CPA. Dos proveedores (23873 y 43398) mezclan verbos entre sus años,
    # asi que el cruce se acota a ese subconjunto en vez de aplicarse al periodo completo.
    # Excel devuelve "2025" como el numero 2025.0 cuando la celda trae un solo año; sin
    # normalizar, `--cruzar-anios 2025.0` reventaria en argparse y la comparacion contra
    # `anios` marcaria como parcial un cruce que en realidad cubre todo el periodo.
    df["anios_cruce"] = df["anios_cruce"].fillna("").apply(_anios_texto)
    df["anios"] = df["anios"].apply(_anios_texto)
    df["usar_cpa"] = df["anios_cruce"] != ""
    df["cruce_parcial"] = df["usar_cpa"] & (df["anios_cruce"] != df["anios"])
    return df.sort_values(["grande", "renglones"])  # los chicos primero, el gigante al final


def revisar_cpa(plan: pd.DataFrame) -> list[str]:
    """Verifica que los proveedores que SI llevan cruce tengan datos en el Parquet.

    Sin esta barrera el fallo es silencioso y caro: el pipeline no encuentra CPA, cae en la
    rama de "el Compras ya trae cobertura alta" y entrega un archivo SIN el cruce que el
    plan pedia, sin marcar error. Paso exactamente eso con Grupo Carmi (43398), cuyo RFC se
    descargo despues de la ultima copia manual del acervo y por eso no estaba en la ruta
    configurada. Vale mas abortar aqui que revisar 43 entregables a mano.
    """
    raiz = config.CPA_VISION_PARQUET_DIR
    problemas = []
    for fila in plan[plan["usar_cpa"]].itertuples(index=False):
        rfc = RFC_POR_PROVEEDOR.get(int(fila.prov), "")
        anios = [int(a) for a in (fila.anios_cruce or fila.anios).split()]
        if not rfc:
            problemas.append(f"  {int(fila.prov)}: no se pudo resolver su RFC")
            continue
        faltan = [a for a in anios if not (raiz / f"rfc={rfc}" / f"year={a}").exists()]
        if faltan:
            problemas.append(
                f"  {int(fila.prov)} ({rfc}): faltan en el Parquet los años {faltan}"
            )
    return problemas


# RFC de los proveedores que llevan cruce. Se fijan aqui porque son cinco y resolverlos
# contra SQL en cada corrida cuesta minutos para nada.
RFC_POR_PROVEEDOR = {
    7112: "FRA961126F59",
    11914: "GCH141112BG4",
    17222: "PAG150819C57",
    23873: "CEGM8802092Z8",
    43398: "GCA960122UD0",
}


def ya_hecho(fila) -> Path | None:
    """La Validación esperada, si ya existe (para poder reanudar)."""
    base = safe_filename(f"{int(fila.prov)}_{str(fila.nombre).strip()}").rstrip(" .")
    ruta = SALIDA / base / f"Validacion_{base}.xlsx"
    return ruta if ruta.exists() else None


def comandos(fila) -> list[list[str]]:
    parquet = str(config.CPA_VISION_PARQUET_DIR)
    prov, ini, fin = str(int(fila.prov)), fila.inicio, fila.fin
    # El cruce con CPA se hace SOLO donde la columna `accion` dice "Descargar/Ejecutar".
    # Donde dice solo "Ejecutar" se ejecuta sin CPA aunque el Parquet tenga datos de ese
    # RFC: buena parte de lo que hay se bajó fuera del alcance del plan, y dejar que el
    # resultado dependa de eso haría la corrida irreproducible. Decisión de Oscar.
    if not fila.usar_cpa:
        extra = ["--sin-cpa"]
    elif fila.cruce_parcial:
        extra = ["--cruzar-anios", *fila.anios_cruce.split()]
    else:
        extra = []
    if not fila.grande:
        return [[str(PY), "main.py", "cpa-salida", "--vendor", prov, "--start", ini,
                 "--end", fin, "--parquet", parquet, "--output-dir", str(SALIDA), *extra]]
    # Gigante: primero los Compras por trimestre, luego la Validación en streaming.
    base = ["--vendor", prov, "--start", ini, "--end", fin, "--parquet", parquet,
            "--output-dir", str(SALIDA), *extra]
    return [
        [str(PY), "main.py", "cpa-compras-grande", *base],
        [str(PY), "main.py", "cpa-validacion-grande", *base],
    ]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--solo", type=int, default=None, help="Ejecutar un solo proveedor")
    p.add_argument("--listar", action="store_true", help="Mostrar el plan sin ejecutar")
    p.add_argument("--rehacer", action="store_true", help="Rehacer aunque ya exista la salida")
    args = p.parse_args()

    plan = cargar_plan()
    if args.solo:
        plan = plan[plan["prov"] == args.solo]
        if plan.empty:
            raise SystemExit(f"El proveedor {args.solo} no esta en el plan.")

    if args.listar:
        print(plan[["prov", "nombre", "anios", "inicio", "fin", "renglones", "grande", "usar_cpa", "anios_cruce"]].to_string(index=False))
        return

    problemas = revisar_cpa(plan)
    if problemas:
        print("NO se puede ejecutar: faltan datos de CPA para proveedores que SI llevan cruce.")
        for linea in problemas:
            print(linea)
        print(f"\nParquet consultado: {config.CPA_VISION_PARQUET_DIR}")
        print("Sincroniza el acervo antes de ejecutar (robocopy desde outputs/cpa_vision).")
        raise SystemExit(1)

    logdir = RAIZ / "outputs" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resumen = logdir / f"bloque1_{stamp}.txt"

    def anota(texto: str) -> None:
        print(texto, flush=True)
        with resumen.open("a", encoding="utf-8") as fh:
            fh.write(texto + "\n")

    anota(f"=== Bloque 1 · {len(plan)} proveedores · inicio {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    anota(f"Salida : {SALIDA}")
    anota(f"Parquet: {config.CPA_VISION_PARQUET_DIR}\n")

    ok = fallos = omitidos = 0
    for n, fila in enumerate(plan.itertuples(index=False), start=1):
        etiqueta = f"[{n}/{len(plan)}] {int(fila.prov)} {str(fila.nombre).strip()[:40]}"
        hecho = ya_hecho(fila)
        if hecho and not args.rehacer:
            anota(f"{etiqueta}  ya existe, se omite")
            omitidos += 1
            continue

        anota(f"{etiqueta}  {fila.inicio}..{fila.fin}  ({int(fila.renglones):,} renglones"
              f"{', GIGANTE' if fila.grande else ''}"
              f"{f', cruce CPA solo {fila.anios_cruce}' if fila.cruce_parcial else ', con cruce CPA' if fila.usar_cpa else ', SIN CPA'})")
        t0 = time.time()
        log_prov = logdir / f"bloque1_{int(fila.prov)}_{stamp}.log"
        exito = True
        with log_prov.open("w", encoding="utf-8") as fh:
            for cmd in comandos(fila):
                r = subprocess.run(cmd, cwd=RAIZ, stdout=fh, stderr=subprocess.STDOUT)
                if r.returncode != 0:
                    exito = False
                    break
        dur = time.time() - t0
        if exito:
            ok += 1
            anota(f"        OK  ·  {dur/60:.1f} min")
        else:
            fallos += 1
            anota(f"        FALLO  ·  {dur/60:.1f} min  ·  ver {log_prov.name}")

    anota(f"\n=== Fin {datetime.now():%Y-%m-%d %H:%M:%S} · OK {ok} · fallos {fallos} · omitidos {omitidos} ===")
    anota(f"Resumen: {resumen}")

    # Cada proveedor ya refresca el reporte al terminar, pero si TODOS se omitieron (corrida
    # reanudada) ningun subproceso lo habria tocado. Con la cache esto cuesta segundos.
    try:
        from automation_costos.reporte_diferencias import actualizar_reporte

        anota("\nActualizando el reporte consolidado de diferencias...")
        anota(f"Reporte: {actualizar_reporte(SALIDA, log=anota)}")
    except Exception as exc:  # noqa: BLE001 — los entregables ya estan escritos
        anota(f"No se pudo actualizar el reporte consolidado: {exc}")


if __name__ == "__main__":
    main()
