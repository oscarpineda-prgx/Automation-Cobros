"""Motor de ejecucion: que comandos produce un proveedor y como se corren en fila.

Aqui vive **la decision**: si un proveedor va por el camino normal o por el de gigantes, si
lleva cruce con CPA o no, si hay que recortar años salteados. Antes vivia dentro de
`scripts/ejecutar_bloque1.py`, asi que solo la terminal podia usarla; se saco al paquete
para que la interfaz grafica ejecute **exactamente lo mismo**.

    ejecutar_bloque1.py  ──┐
                           ├──> ejecutor  (esta unica definicion)
    app.py (la cola)     ──┘

Sin este paso, la GUI tendria que reimplementar "que es un proveedor gigante" y las dos
copias se irian separando con el tiempo.

Cada proveedor corre en **su propio proceso**: la memoria se libera entre uno y otro y un
fallo no arrastra al resto. Es RESUMIBLE: si la Validacion ya existe, se omite.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

import config
from automation_costos.cancelacion import SenalCancelacion, revisar

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = RAIZ / ".venv" / "Scripts" / "python.exe"

#: ¿Corremos dentro del .exe empaquetado por PyInstaller?
CONGELADO = bool(getattr(sys, "frozen", False))


def lanzador(python: Path | str = PYTHON) -> list[str]:
    """Con que se arranca un subcomando.

    Empaquetado **no hay `python.exe` ni `main.py`**: los dos viven en el repositorio, no
    dentro del ejecutable. Pero el punto de entrada del .exe *es* `main.py`, que ya despacha
    subcomandos (y abre la interfaz solo cuando no le dan ninguno), asi que el ejecutable se
    **auto-invoca**: `AutomationCostos.exe cpa-salida --vendor ...` corre exactamente el
    mismo codigo que `python main.py cpa-salida ...`.

    Sin empaquetar, el interprete del entorno y el script de siempre.
    """
    return [sys.executable] if CONGELADO else [str(python), "main.py"]


def directorio_trabajo() -> Path:
    """Desde donde se lanzan los subprocesos.

    Empaquetado, `RAIZ` apunta dentro de `_internal` (es donde acaba este modulo), que no es
    un directorio de trabajo util. Se usa la carpeta del ejecutable.
    """
    return Path(sys.executable).parent if CONGELADO else RAIZ

# El periodo "2025" arrastra a 2026: facturas subidas tarde y pagos con plazo de hasta 90
# dias (acuerdo con Monica, reunion 008).
CIERRE_2025 = "2026-03-31"

# Nestle (1.3M) salio bien por el camino normal en 32 min; Arca (11.5M) y Pepsico (10.1M)
# solo salieron por trimestres. El corte se pone con holgura entre ambos.
UMBRAL_GRANDE = 1_500_000


@dataclass(frozen=True)
class TrabajoSalida:
    """Un proveedor a ejecutar, con lo unico que hace falta para decidir sus comandos.

    Es el punto de encuentro entre los dos frentes: `ejecutar_bloque1` lo arma desde el
    Excel del plan y la GUI desde su cola. A partir de aqui, el camino es el mismo.
    """

    prov: str
    nombre: str = ""
    anios: tuple[int, ...] = ()
    #: Años que llevan cruce con CPA. Vacio = el proveedor entero va `--sin-cpa`.
    anios_cruce: tuple[int, ...] = ()
    renglones: int = 0

    @property
    def inicio(self) -> str:
        return f"{min(self.anios)}-01-01"

    @property
    def fin(self) -> str:
        return CIERRE_2025 if max(self.anios) >= 2025 else f"{max(self.anios)}-12-31"

    @property
    def usar_cpa(self) -> bool:
        return bool(self.anios_cruce)

    @property
    def cruce_parcial(self) -> bool:
        """Mezcla años con y sin cruce: el cruce se acota en vez de aplicarse al periodo."""
        return self.usar_cpa and tuple(self.anios_cruce) != tuple(self.anios)

    @property
    def con_huecos(self) -> bool:
        """F_COMPRAS se pide por rango continuo; un año de en medio que el plan NO pidio
        llegaria al entregable y se volveria a reclamar. `--anios` lo recorta."""
        return list(self.anios) != list(range(min(self.anios), max(self.anios) + 1))

    @property
    def grande(self) -> bool:
        return self.renglones > UMBRAL_GRANDE

    @property
    def describe_cruce(self) -> str:
        """Como se anuncia el cruce en la bitacora, para leer de un vistazo que se hizo."""
        if not self.usar_cpa:
            return "SIN CPA"
        if self.cruce_parcial:
            return f"cruce CPA solo {' '.join(map(str, self.anios_cruce))}"
        return "con cruce CPA"


@dataclass
class Resultado:
    ok: int = 0
    fallos: int = 0
    omitidos: int = 0
    logs: dict[str, Path] = field(default_factory=dict)


def comandos(
    trabajo: TrabajoSalida,
    *,
    salida: Path | str,
    parquet: Path | str | None = None,
    python: Path | str = PYTHON,
) -> list[list[str]]:
    """Los comandos que hay que correr para este proveedor, en orden.

    El cruce con CPA se hace SOLO donde el plan lo pidio. Donde no, se ejecuta sin CPA
    **aunque el Parquet tenga datos de ese RFC**: buena parte de lo que hay se bajo fuera
    del alcance del plan, y dejar que el resultado dependa de eso haria la corrida
    irreproducible. Decision de Oscar.
    """
    parquet = str(parquet or config.CPA_VISION_PARQUET_DIR)
    if not trabajo.usar_cpa:
        extra = ["--sin-cpa"]
    elif trabajo.cruce_parcial:
        extra = ["--cruzar-anios", *map(str, trabajo.anios_cruce)]
    else:
        extra = []
    # Solo cuando hay huecos: sin `--anios` el pipeline no recorta nada, que es justo el
    # comportamiento que quieren los proveedores de periodo continuo.
    if trabajo.con_huecos:
        extra = [*extra, "--anios", *map(str, trabajo.anios)]

    base = ["--vendor", str(trabajo.prov), "--start", trabajo.inicio, "--end", trabajo.fin,
            "--parquet", parquet, "--output-dir", str(salida), *extra]
    # `lanzador()` decide si esto es `python main.py ...` o el propio .exe auto-invocandose.
    arranque = lanzador(python)
    if not trabajo.grande:
        return [[*arranque, "cpa-salida", *base]]
    # Gigante: primero los Compras por trimestre, luego la Validacion en streaming.
    return [
        [*arranque, "cpa-compras-grande", *base],
        [*arranque, "cpa-validacion-grande", *base],
    ]


def entregados(salida: Path | str) -> dict[int, list[Path]]:
    """Numero de proveedor -> Validaciones que ya existen en la carpeta de entregables.

    Se indexa por NUMERO, no reconstruyendo el nombre del archivo, porque ese camino falla
    de dos formas y las dos se vieron en disco:

    - El nombre de la planeacion no siempre es el `vndname` de SQL con el que se creo la
      carpeta (acentos, cortes, espacios dobles).
    - Hay entregables con **sufijo de periodo**: 3M (80622) tiene
      `Validacion_80622_3M MEXICO SA DE CV_2020-2024.xlsx` y `..._2025.xlsx`.

    Un solo escaneo de la carpeta en vez de un `exists()` por proveedor: son cientos de
    consultas a una unidad de red.
    """
    indice: dict[int, list[Path]] = {}
    salida = Path(salida)
    if not salida.exists():
        return indice
    for carpeta in salida.iterdir():
        if not carpeta.is_dir():
            continue
        m = re.match(r"^(\d+)_", carpeta.name)
        if not m:
            continue
        # `~$...` son temporales de Excel abierto, no entregables.
        vals = [v for v in carpeta.glob("Validacion_*.xlsx") if not v.name.startswith("~$")]
        if vals:
            indice.setdefault(int(m.group(1)), []).extend(vals)
    return indice


def ya_entregado(trabajo: TrabajoSalida, indice: dict[int, list[Path]]) -> Path | None:
    rutas = indice.get(int(trabajo.prov))
    return rutas[0] if rutas else None


def ejecutar(
    trabajos: Sequence[TrabajoSalida],
    *,
    salida: Path | str,
    parquet: Path | str | None = None,
    log: Callable[[str], None] = print,
    cancelado: SenalCancelacion | None = None,
    rehacer: bool = False,
    progreso: Callable[[dict], None] | None = None,
    logdir: Path | None = None,
) -> Resultado:
    """Corre los trabajos en fila, uno por proceso. Devuelve el conteo del resultado.

    `progreso` recibe un dict por cada cambio de estado, igual que el motor de descarga:
    es lo que permite a la interfaz pintar su cola en vivo.

    `cancelado` se consulta **entre proveedores**, nunca a media escritura de un entregable.
    """
    # Sin empaquetar hace falta el interprete del entorno. Se comprueba UNA vez y de entrada:
    # si falta, el sintoma seria N fallos seguidos con "el sistema no puede encontrar el
    # archivo" enterrados en N logs. Empaquetado no aplica: el lanzador es el propio .exe.
    if not CONGELADO and not Path(PYTHON).exists():
        raise FileNotFoundError(
            f"No se encontró el intérprete del entorno virtual: {PYTHON}\n"
            "La generación de entregables lanza `main.py` como subproceso y lo necesita. "
            "Crea el .venv (ver README)."
        )

    salida = Path(salida)
    logdir = Path(logdir or config.LOG_DIR)
    logdir.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")

    indice = entregados(salida)
    resultado = Resultado()
    total = len(trabajos)

    for n, trabajo in enumerate(trabajos, start=1):
        revisar(cancelado, f"antes del proveedor {trabajo.prov}")
        etiqueta = f"[{n}/{total}] {trabajo.prov} {trabajo.nombre[:40]}"

        hecho = None if rehacer else ya_entregado(trabajo, indice)
        if hecho is not None:
            log(f"{etiqueta}  ya existe, se omite")
            resultado.omitidos += 1
            _avisar(progreso, trabajo, n, total, estado="omitido")
            continue

        detalle = f"{trabajo.renglones:,} renglones"
        if trabajo.grande:
            detalle += ", GIGANTE"
        log(f"{etiqueta}  {trabajo.inicio}..{trabajo.fin}  ({detalle}, {trabajo.describe_cruce})")
        _avisar(progreso, trabajo, n, total, estado="corriendo")

        t0 = time.time()
        log_prov = logdir / f"salida_{trabajo.prov}_{sello}.log"
        resultado.logs[str(trabajo.prov)] = log_prov
        exito = True
        with log_prov.open("w", encoding="utf-8") as fh:
            for cmd in comandos(trabajo, salida=salida, parquet=parquet):
                completado = subprocess.run(
                    cmd, cwd=directorio_trabajo(), stdout=fh, stderr=subprocess.STDOUT
                )
                if completado.returncode:
                    exito = False
                    break
        dur = time.time() - t0

        if exito:
            resultado.ok += 1
            log(f"        OK  ·  {dur / 60:.1f} min")
        else:
            resultado.fallos += 1
            log(f"        FALLO  ·  {dur / 60:.1f} min  ·  ver {log_prov.name}")
        _avisar(
            progreso, trabajo, n, total,
            estado="ok" if exito else "error",
            segundos=dur,
            log=str(log_prov),
        )

    return resultado


def _avisar(
    progreso: Callable[[dict], None] | None,
    trabajo: TrabajoSalida,
    posicion: int,
    total: int,
    **datos,
) -> None:
    """Notifica el avance. NUNCA lanza: un reporte no puede tumbar una ejecucion."""
    if progreso is None:
        return
    try:
        progreso({"posicion": posicion, "total": total, "prov": trabajo.prov, **datos})
    except Exception:  # noqa: BLE001 — el entregable manda, el aviso es accesorio
        pass
