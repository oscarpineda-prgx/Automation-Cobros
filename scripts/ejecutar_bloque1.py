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
import sys
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
from automation_costos import ejecutor
from automation_costos.ejecutor import CIERRE_2025, TrabajoSalida

PY = ejecutor.PYTHON
PLAN = RAIZ / "plan_ejecucion_bloque1.xlsx"
SALIDA = Path(
    r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Proceso Validación de condiciones (Oscar Pineda)"
)


def _anios_texto(valor) -> str:
    """Normaliza una celda de años a "2020 2021 ...", sin decimales sueltos de Excel."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return " ".join(str(int(float(a))) for a in str(valor).split())


def cargar_plan(ruta: Path | None = None, orden: str = "tamano") -> pd.DataFrame:
    df = pd.read_excel(ruta or PLAN)
    df["renglones"] = pd.to_numeric(df["renglones"], errors="coerce").fillna(0)
    # `anios_cruce` trae los años marcados "Descargar/Ejecutar", que son los unicos que
    # llevan cruce con CPA. Dos proveedores (23873 y 43398) mezclan verbos entre sus años,
    # asi que el cruce se acota a ese subconjunto en vez de aplicarse al periodo completo.
    # Excel devuelve "2025" como el numero 2025.0 cuando la celda trae un solo año; sin
    # normalizar, `--cruzar-anios 2025.0` reventaria en argparse y la comparacion contra
    # `anios` marcaria como parcial un cruce que en realidad cubre todo el periodo.
    df["anios_cruce"] = df["anios_cruce"].fillna("").apply(_anios_texto)
    df["anios"] = df["anios"].apply(_anios_texto)

    # A partir de aqui manda `ejecutor.TrabajoSalida`: periodo, camino gigante, cruce y
    # recorte por años salteados tienen UNA sola definicion, la misma que usa la interfaz.
    df["trabajo"] = [
        TrabajoSalida(
            prov=str(int(f.prov)),
            nombre=str(f.nombre).strip(),
            anios=tuple(int(a) for a in str(f.anios).split()),
            anios_cruce=tuple(int(a) for a in str(f.anios_cruce).split()),
            renglones=int(f.renglones),
        )
        for f in df.itertuples(index=False)
    ]
    for columna in ("inicio", "fin", "grande", "usar_cpa", "cruce_parcial", "con_huecos"):
        df[columna] = [getattr(t, columna) for t in df["trabajo"]]

    if orden == "prioridad" and "prioridad" in df.columns:
        # Orden del plan tal cual (por prioridad de negocio). Es el que se quiere cuando se
        # ejecuta por bloques: el bloque 1 son los 20 mas prioritarios, no los 20 mas chicos.
        df = df.sort_values(["prioridad", "prov"])
    else:
        df = df.sort_values(["grande", "renglones"])  # los chicos primero, el gigante al final
    # Indice ESTABLE del plan ya ordenado: es a lo que apunta --start-index. Se calcula una
    # sola vez aqui para que el numero que imprime el resumen sirva tal cual en la siguiente
    # corrida, aunque despues se filtre por --solo.
    return df.reset_index(drop=True).assign(pos=lambda d: range(len(d)))


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
    con_cruce = plan[plan["usar_cpa"]]
    tabla = _cargar_cache_rfc()

    # Los que aun no tengan RFC se resuelven contra SQL de una sola conexion (~2 s cada uno)
    # y se cachean, para que las tandas siguientes no vuelvan a pagarlo.
    faltan_rfc = [int(f.prov) for f in con_cruce.itertuples(index=False) if int(f.prov) not in tabla]
    if faltan_rfc:
        print(f"Resolviendo el RFC de {len(faltan_rfc)} proveedor(es) contra SQL...")
        import pyodbc

        try:
            with pyodbc.connect(config.get_connection_string()) as conn:
                cur = conn.cursor()
                for prov in faltan_rfc:
                    tabla[prov] = resolver_rfc(cur, prov)
            _guardar_cache_rfc(tabla)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! no se pudo conectar a SQL para resolver RFC: {exc}")

    for fila in con_cruce.itertuples(index=False):
        rfc = tabla.get(int(fila.prov), "")
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


# RFC ya conocidos (bloque 1). Los demas se resuelven contra SQL la primera vez y se
# guardan en CACHE_RFC, porque el plan completo tiene 246 proveedores con cruce y fijarlos
# a mano no escala.
RFC_POR_PROVEEDOR = {
    7112: "FRA961126F59",
    11914: "GCH141112BG4",
    17222: "PAG150819C57",
    23873: "CEGM8802092Z8",
    43398: "GCA960122UD0",
}
CACHE_RFC = RAIZ / "rfc_por_proveedor.csv"
# Ventanas validas por base de compras: el RFC se busca donde haya movimientos.
_VENTANAS_RFC = [
    ("SORIANA_PROJECTS", "2020-01-01", "2024-12-31"),
    ("SORIANA_2025_PROJECTS", "2025-01-01", CIERRE_2025),
]


def _cargar_cache_rfc() -> dict[int, str]:
    tabla = dict(RFC_POR_PROVEEDOR)
    if CACHE_RFC.exists():
        cache = pd.read_csv(CACHE_RFC, dtype=str)
        tabla.update({
            int(r["prov"]): str(r["rfc"]).strip().upper()
            for _, r in cache.iterrows()
            if str(r.get("rfc", "")).strip()
        })
    return tabla


def _guardar_cache_rfc(tabla: dict[int, str]) -> None:
    filas = [{"prov": p, "rfc": r} for p, r in sorted(tabla.items()) if r]
    pd.DataFrame(filas).to_csv(CACHE_RFC, index=False)


def resolver_rfc(cursor, vendor: int) -> str:
    """RFC del proveedor, buscandolo en la base que tenga movimientos suyos (~2 s)."""
    for dbn, ini, fin in _VENTANAS_RFC:
        q = f"SELECT TOP (1) cnpj FROM {dbn}.dbo.F_COMPRAS(?, ?, ?) WHERE cnpj IS NOT NULL;"
        try:
            row = cursor.execute(q, str(vendor), ini, fin).fetchone()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! error SQL resolviendo el RFC de {vendor}: {exc}")
            row = None
        if row and row[0]:
            return str(row[0]).strip().upper()
    return ""



def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--solo", type=int, default=None, help="Ejecutar un solo proveedor")
    p.add_argument("--listar", action="store_true", help="Mostrar el plan sin ejecutar")
    p.add_argument("--rehacer", action="store_true", help="Rehacer aunque ya exista la salida")
    p.add_argument("--plan", default=None,
                   help="Excel del plan a ejecutar (por omision, el del bloque 1). "
                        "Para el plan completo: plan_ejecucion.xlsx")
    p.add_argument("--start-index", type=int, default=0,
                   help="Indice base 0 dentro del plan ordenado: por donde empieza el bloque")
    p.add_argument("--batch-size", type=int, default=None,
                   help="Cuantos proveedores ejecutar en esta corrida (por omision, todos)")
    p.add_argument("--orden", choices=["tamano", "prioridad"], default="tamano",
                   help="tamano: los chicos primero (por omision). "
                        "prioridad: el orden del plan, el recomendado para ejecutar por bloques")
    args = p.parse_args()

    plan = cargar_plan(Path(args.plan) if args.plan else None, orden=args.orden)

    # Los ya entregados salen ANTES de cortar el bloque, no despues. Si se filtraran dentro
    # del bucle, un "--batch-size 20" que topara con 5 entregados rendiria 15 proveedores
    # nuevos en vez de 20, y el --start-index seguiria contando huecos. Se comprueba contra
    # el DISCO (existe su Validacion), no contra la columna `entregado` del Excel, que se
    # queda vieja en cuanto corre la primera tanda.
    indice = ejecutor.entregados(SALIDA)
    if not args.rehacer:
        antes = len(plan)
        plan = plan[~plan["prov"].astype(int).isin(indice)]
        if antes != len(plan):
            print(f"Ya entregados, fuera del plan: {antes - len(plan)}  "
                  f"(quedan {len(plan)} pendientes de {antes})")
    total_plan = len(plan)
    if not total_plan:
        raise SystemExit("No queda ningun proveedor pendiente en el plan.")

    if args.solo:
        plan = plan[plan["prov"] == args.solo]
        if plan.empty:
            raise SystemExit(
                f"El proveedor {args.solo} no esta en el plan, o ya esta entregado "
                "(usa --rehacer para volver a generarlo)."
            )
    else:
        # El corte va DESPUES de ordenar y de quitar los entregados, asi que el bloque
        # rinde siempre `--batch-size` proveedores de trabajo real.
        fin_bloque = args.start_index + args.batch_size if args.batch_size else total_plan
        plan = plan.iloc[args.start_index:fin_bloque]
        if plan.empty:
            raise SystemExit(
                f"El bloque queda vacio: --start-index {args.start_index} sobre "
                f"{total_plan} proveedores pendientes."
            )
        print(f"Bloque: pendientes {args.start_index}..{args.start_index + len(plan) - 1} "
              f"de {total_plan} (orden: {args.orden})")

    if args.listar:
        print(plan[["prov", "nombre", "anios", "inicio", "fin", "renglones", "grande", "usar_cpa", "anios_cruce", "con_huecos"]].to_string(index=False))
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

    # El bucle vive en `automation_costos.ejecutor`, que es el mismo que usa la interfaz.
    res = ejecutor.ejecutar(
        list(plan["trabajo"]),
        salida=SALIDA,
        log=anota,
        rehacer=args.rehacer,
        logdir=logdir,
    )
    ok, fallos, omitidos = res.ok, res.fallos, res.omitidos

    anota(f"\n=== Fin {datetime.now():%Y-%m-%d %H:%M:%S} · OK {ok} · fallos {fallos} · omitidos {omitidos} ===")
    anota(f"Resumen: {resumen}")
    # El indice con el que arrancar la proxima tanda, ya calculado: evita tener que contar a
    # mano cuantos iban y equivocarse repitiendo o saltandose proveedores.
    if not args.solo:
        siguiente = args.start_index + len(plan)
        if siguiente < total_plan:
            anota(f"Siguiente bloque: --start-index {siguiente}"
                  + (f" --batch-size {args.batch_size}" if args.batch_size else "")
                  + f"   ({total_plan - siguiente} proveedores por delante)")
        else:
            anota("Plan recorrido completo: no queda nada por delante.")

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
