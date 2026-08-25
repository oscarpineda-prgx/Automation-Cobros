"""Cola de trabajo de la interfaz: el modelo y su persistencia. Sin interfaz.

Cada renglon de la cola es **un proveedor, con su periodo y con lo que hay que hacerle**.
Un renglon puede pedir descargar de CPA Vision, generar el entregable, o las dos cosas en
ese orden. Ver `ACCIONES`.

El portal encola las solicitudes **por usuario**: hasta que no termina una descarga, la
siguiente no arranca. Por eso el trabajo real es una fila secuencial de proveedores y no
varias descargas en paralelo.

Los dos motores ya existen y estan probados; la cola solo los alimenta:

    descarga  ->  cpa_vision.request_vendor_master_batch   (via un Excel RFC/FECHAS)
    salida    ->  ejecutor.ejecutar                        (via TrabajoSalida)

Decisiones
----------
- **Los años se validan con el MISMO parser del CLI** (`cpa_vision._parse_years`). Un
  periodo que la interfaz acepta se comporta igual en terminal, con los mismos mensajes de
  error y el mismo rango valido (2014-2026). Duplicar la regla seria condenarlas a
  separarse.
- **La cola se entrega a cada motor en el formato que ese motor ya sabe leer**: un Excel
  `RFC`/`FECHAS` para la descarga, un `TrabajoSalida` para la generacion. La interfaz **no
  reimplementa** ni el scraping ni la decision de "proveedor gigante".
- **Las dos fases llevan estado por separado** (`estado` y `estado_salida`). Un proveedor
  que ya se descargo pero al que le falta el entregable sigue pendiente: si compartieran
  un solo campo, terminar la descarga lo sacaria de la fila.
- **Persistente**: una tanda dura horas. Si se cierra la aplicacion, la cola y lo ya hecho
  siguen ahi al volver a abrir.

Aqui no se toca Tk ni Playwright: es un modelo puro y por eso se puede probar solo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

import config

# Se reusa a proposito el parser del CLI en vez de escribir otro: ver el encabezado.
from automation_costos.cpa_vision import _parse_years

if TYPE_CHECKING:  # solo para el tipo: importarlo en runtime encadenaria pandas/duckdb
    from automation_costos.ejecutor import TrabajoSalida

RUTA_COLA = config.LOG_DIR / "cola_descarga.json"

PENDIENTE = "pendiente"
CORRIENDO = "corriendo"
OK = "ok"
SIN_VALORES = "sin_valores"
OMITIDO = "omitido"
ERROR = "error"

#: Estados que no hay que volver a intentar en una reanudacion.
#: "Sin valores" entra aqui a proposito: el portal ya confirmo que ese RFC no tiene CFDI en
#: el periodo. Es un resultado DEFINITIVO, no un fallo, y reintentarlo solo gasta tiempo.
#: "Omitido" tambien: el entregable ya existe en disco, que es justamente el objetivo.
TERMINADOS = frozenset({OK, SIN_VALORES, OMITIDO})

#: Traduccion de los estatus que emiten los dos motores a los estados de la cola.
#: `downloaded_after_recovery` es una descarga BUENA: tropezo y el reintento la completo.
_DESDE_MOTOR = {
    # cpa_vision.request_vendor_master_batch
    "downloaded": OK,
    "downloaded_after_recovery": OK,
    "sin_valores": SIN_VALORES,
    # ejecutor.ejecutar
    "ok": OK,
    "omitido": OMITIDO,
    # comunes
    "corriendo": CORRIENDO,
    "error": ERROR,
}


def estado_desde_motor(estatus: str) -> str:
    """Estado de cola equivalente al estatus que reporta un motor."""
    return _DESDE_MOTOR.get(str(estatus).strip(), ERROR)


# --- Que hacerle a cada proveedor -----------------------------------------
#
# Las cuatro opciones no son cuatro caminos distintos: son tres interruptores
# (descargar / generar / cruzar con CPA). Modelarlas asi evita el `if accion == ...`
# repartido por la interfaz y hace que agregar una quinta combinacion sea un renglon.


@dataclass(frozen=True)
class Accion:
    clave: str
    etiqueta: str
    #: Una linea que explica CUANDO se usa. La interfaz la muestra bajo el desplegable.
    ayuda: str
    #: Pedir los CFDI al portal de CPA Vision.
    descarga: bool
    #: Correr el pipeline hasta la Validacion de Condiciones.
    genera: bool
    #: Al generar, llenar el bloque EDI con el Parquet de CPA. Sin efecto si `genera` es
    #: falso; con el falso, el pipeline corre `--sin-cpa`.
    cpa: bool


# Las etiquetas dicen QUE hace cada una, no como esta implementada. "Generar con CPA" y
# "Generar sin CPA" se prestaban a confusion —parecian variantes de descargar— porque el
# "con/sin CPA" no acompaña al descargar sino al generar. Lo reporto Oscar.
ACCIONES: dict[str, Accion] = {
    a.clave: a
    for a in (
        Accion(
            "descargar", "Solo descargar",
            "Trae los CFDI del portal al Parquet. No produce ningún Excel.",
            descarga=True, genera=False, cpa=False,
        ),
        Accion(
            "descargar+generar", "Descargar y generar",
            "Baja del portal y luego arma la Validación. Para un proveedor que aún no está descargado.",
            descarga=True, genera=True, cpa=True,
        ),
        Accion(
            "generar", "Generar con lo ya descargado",
            "No baja nada: arma la Validación cruzando los CFDI que ya están en el Parquet.",
            descarga=False, genera=True, cpa=True,
        ),
        Accion(
            "generar_sin_cpa", "Generar sin cruce de CPA",
            "Arma la Validación dejando el bloque EDI vacío. Para extranjeros sin RFC o "
            "proveedores sin CFDI en el portal.",
            descarga=False, genera=True, cpa=False,
        ),
    )
}

#: Lo que hacia la cola antes de tener acciones. Se mantiene como omision para que una cola
#: guardada por una version anterior se lea con su significado original.
ACCION_PREDETERMINADA = "descargar"

ETIQUETAS_ACCION = [a.etiqueta for a in ACCIONES.values()]

#: Nombres anteriores. Un Excel de lote exportado antes del cambio de nombre sigue leyendose:
#: la clave nunca cambio, solo el texto que ve el usuario.
_ALIAS = {
    "GENERAR CON CPA": "generar",
    "GENERAR SIN CPA": "generar_sin_cpa",
}
_POR_ETIQUETA = {a.etiqueta.upper(): a.clave for a in ACCIONES.values()} | _ALIAS


def clave_accion(texto: str) -> str:
    """Normaliza a clave de accion. Acepta la clave o la etiqueta que ve el usuario."""
    texto = str(texto).strip()
    if texto in ACCIONES:
        return texto
    clave = _POR_ETIQUETA.get(texto.upper())
    if clave is None:
        raise ValueError(f"Acción desconocida: {texto!r}. Opciones: {', '.join(ETIQUETAS_ACCION)}")
    return clave


@dataclass
class Trabajo:
    """Un proveedor de la cola: su periodo, que hay que hacerle y como va cada fase."""

    proveedor: str
    fechas: str
    nombre: str = ""
    rfc: str = ""
    accion: str = ACCION_PREDETERMINADA
    #: Renglones en F_COMPRAS. Lo resuelve la fase de salida al arrancar (`contar_compras`)
    #: porque de el depende si el proveedor va por el camino normal o por el de gigantes.
    renglones: int = 0
    # -- fase de descarga --
    estado: str = PENDIENTE
    detalle: str = ""
    segundos: float = 0.0
    # -- fase de salida --
    estado_salida: str = PENDIENTE
    detalle_salida: str = ""
    segundos_salida: float = 0.0

    @property
    def anios(self) -> tuple[int, ...]:
        return _parse_years(self.fechas)

    @property
    def plan(self) -> Accion:
        """Que hay que hacerle. Una accion desconocida cae en la de omision, no revienta:
        la cola vive en disco y no puede impedir que la aplicacion abra."""
        return ACCIONES.get(self.accion, ACCIONES[ACCION_PREDETERMINADA])

    @property
    def descarga_pendiente(self) -> bool:
        return self.plan.descarga and self.estado not in TERMINADOS

    @property
    def salida_pendiente(self) -> bool:
        return self.plan.genera and self.estado_salida not in TERMINADOS

    @property
    def terminado(self) -> bool:
        """Ya no queda nada por hacerle, en ninguna de las dos fases."""
        return not (self.descarga_pendiente or self.salida_pendiente)

    @property
    def identidad(self) -> str:
        """Con que se reconoce este trabajo: el numero de proveedor, o el RFC si no hay.

        Capturando a mano siempre hay numero. Importando un Excel puede venir solo el RFC,
        que es lo unico que el portal necesita para descargar.
        """
        return self.proveedor or self.rfc

    def periodo_sql(self) -> tuple[str, str]:
        """Rango de fechas para resolver el RFC contra F_COMPRAS."""
        anios = self.anios
        return f"{anios[0]}-01-01", f"{anios[-1]}-12-31"

    def reiniciar(self) -> None:
        self.estado, self.detalle, self.segundos = PENDIENTE, "", 0.0
        self.estado_salida, self.detalle_salida, self.segundos_salida = PENDIENTE, "", 0.0

    def a_salida(self) -> "TrabajoSalida":
        """Traduce a la entrada del motor de generacion.

        El cruce con CPA se pide **solo si la accion lo dice**, aunque el Parquet tenga
        datos de ese RFC: es la misma regla que aplica el plan por terminal (ver
        `ejecutor.comandos`), para que el resultado no dependa de lo que alguien haya
        bajado por fuera.
        """
        from automation_costos.ejecutor import TrabajoSalida

        if not self.proveedor:
            raise ValueError(
                f"{self.identidad}: para generar el entregable hace falta el número de "
                "proveedor, no solo el RFC."
            )
        anios = self.anios
        return TrabajoSalida(
            prov=self.proveedor,
            nombre=self.nombre,
            anios=anios,
            anios_cruce=anios if self.plan.cpa else (),
            renglones=int(self.renglones),
        )


def crear_trabajo(
    proveedor: str = "",
    fechas: str = "",
    *,
    rfc: str = "",
    nombre: str = "",
    accion: str = ACCION_PREDETERMINADA,
) -> Trabajo:
    """Valida y construye un `Trabajo`. Lanza `ValueError` con un mensaje legible.

    Sirve a los dos caminos de alta: capturando a mano llega `proveedor` y el RFC se
    resuelve despues contra SQL; importando un Excel puede llegar solo el `rfc`, que es lo
    unico que el portal necesita. Basta con que venga uno de los dos.
    """
    proveedor, rfc = str(proveedor).strip(), str(rfc).strip().upper()
    if not (proveedor or rfc):
        raise ValueError("Captura el número de proveedor.")
    if proveedor and not proveedor.isdigit():
        raise ValueError(f"El proveedor debe ser un número: {proveedor!r}")
    # Valida el periodo y la accion AHORA, no cuando el lote lleve dos horas corriendo.
    _parse_years(fechas)
    clave = clave_accion(accion)
    if ACCIONES[clave].genera and not proveedor:
        raise ValueError(
            f"{rfc}: «{ACCIONES[clave].etiqueta}» necesita el número de proveedor, "
            "no solo el RFC."
        )
    return Trabajo(
        proveedor=proveedor,
        fechas=str(fechas).strip(),
        rfc=rfc,
        nombre=str(nombre).strip(),
        accion=clave,
    )


@dataclass
class Cola:
    """La lista de trabajos. Todas las operaciones son sobre indices visibles."""

    trabajos: list[Trabajo] = field(default_factory=list)

    # -- consulta ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self.trabajos)

    def __iter__(self):
        return iter(self.trabajos)

    def pendientes(self) -> list[Trabajo]:
        """Los que tienen algo por hacer, en cualquiera de las dos fases."""
        return [t for t in self.trabajos if not t.terminado]

    def por_descargar(self) -> list[Trabajo]:
        return [t for t in self.trabajos if t.descarga_pendiente]

    def por_generar(self) -> list[Trabajo]:
        """Los que falta generar. Para contar y estimar."""
        return [t for t in self.trabajos if t.salida_pendiente]

    def listos_para_generar(self) -> list[Trabajo]:
        """Los que se pueden generar YA. Para ejecutar.

        Distinto de `por_generar`: un "Descargar y generar" cuya descarga fallo sigue
        pendiente de generar, pero generarlo ahora produciria un entregable con el bloque
        EDI vacio y sin marcar error. Se queda fuera hasta que su descarga termine bien.
        """
        return [t for t in self.trabajos if t.salida_pendiente and not t.descarga_pendiente]

    def indice_de(self, identidad: str) -> int | None:
        """Busca por numero de proveedor o, si el trabajo no lo trae, por RFC."""
        identidad = str(identidad).strip()
        return self._buscar(lambda t: t.identidad.upper() == identidad.upper())

    def indice_de_rfc(self, rfc: str) -> int | None:
        """El motor reporta avance por RFC, que es lo unico que conoce del trabajo."""
        return self._buscar(lambda t: t.rfc == str(rfc).strip().upper())

    def _buscar(self, coincide) -> int | None:
        return next((i for i, t in enumerate(self.trabajos) if coincide(t)), None)

    # -- edicion -----------------------------------------------------------
    def agregar(self, trabajo: Trabajo) -> None:
        if self.indice_de(trabajo.identidad) is not None:
            raise ValueError(f"El proveedor {trabajo.identidad} ya está en la cola.")
        self.trabajos.append(trabajo)

    def quitar(self, indices: list[int]) -> None:
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self.trabajos):
                del self.trabajos[i]

    def mover(self, indice: int, delta: int) -> int:
        """Sube (-1) o baja (+1) un trabajo. Devuelve su nueva posicion."""
        destino = indice + delta
        if not (0 <= indice < len(self.trabajos) and 0 <= destino < len(self.trabajos)):
            return indice
        self.trabajos[indice], self.trabajos[destino] = (
            self.trabajos[destino],
            self.trabajos[indice],
        )
        return destino

    def cambiar_accion(self, indices: list[int], accion: str) -> int:
        """Cambia que hacerle a los trabajos indicados. Devuelve cuantos cambiaron.

        Cambiar la accion **reinicia los estados**: lo que se pide ahora no es lo mismo que
        se pidio antes, y dejar el "listo" de la fase anterior escondería trabajo por hacer.
        """
        clave = clave_accion(accion)
        cambiados = 0
        for i in indices:
            if not (0 <= i < len(self.trabajos)):
                continue
            trabajo = self.trabajos[i]
            if trabajo.accion == clave:
                continue
            if ACCIONES[clave].genera and not trabajo.proveedor:
                raise ValueError(
                    f"{trabajo.identidad}: «{ACCIONES[clave].etiqueta}» necesita el número "
                    "de proveedor, no solo el RFC."
                )
            trabajo.accion = clave
            trabajo.reiniciar()
            cambiados += 1
        return cambiados

    def limpiar(self) -> None:
        self.trabajos.clear()

    def reiniciar_estados(self) -> None:
        for t in self.trabajos:
            t.reiniciar()

    # -- persistencia ------------------------------------------------------
    #
    # `ruta=None` -> se resuelve `RUTA_COLA` AL LLAMAR, no al definir la funcion. Con el
    # valor por omision puesto directo, la ruta quedaba grabada al importar el modulo y no
    # habia forma de redirigirla: una prueba que creyera estar escribiendo en un temporal
    # machacaba la cola real del usuario. Paso.
    def guardar(self, ruta: Path | str | None = None) -> Path:
        ruta = Path(ruta or RUTA_COLA)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(
            json.dumps([asdict(t) for t in self.trabajos], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return ruta

    @classmethod
    def cargar(cls, ruta: Path | str | None = None) -> "Cola":
        """Lee la cola guardada. Si no existe o esta corrupta, arranca vacia."""
        ruta = Path(ruta or RUTA_COLA)
        if not ruta.exists():
            return cls()
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            campos = {f for f in Trabajo.__dataclass_fields__}
            return cls([Trabajo(**{k: v for k, v in d.items() if k in campos}) for d in datos])
        except Exception:
            # Una cola ilegible no puede impedir que la aplicacion abra.
            return cls()

    # -- puentes con los motores -------------------------------------------
    def a_excel(self, ruta: Path | str, *, solo_pendientes: bool = True) -> Path:
        """Escribe el Excel `RFC`/`FECHAS` que consume `request_vendor_master_batch`.

        Con `solo_pendientes` (lo normal al arrancar una tanda) baja unicamente lo que
        falta descargar; sin el, vuelca la cola completa y sirve para guardarla.
        """
        trabajos = self.por_descargar() if solo_pendientes else list(self.trabajos)
        if not trabajos:
            raise ValueError("No hay proveedores pendientes de descarga en la cola.")
        sin_rfc = [t.identidad for t in trabajos if not t.rfc]
        if sin_rfc:
            raise ValueError(f"Estos proveedores no tienen RFC resuelto: {', '.join(sin_rfc)}")
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "RFC": t.rfc,
                    "FECHAS": t.fechas,
                    "num": t.proveedor,
                    "Nombre": t.nombre,
                    "ACCION": t.plan.etiqueta,
                }
                for t in trabajos
            ]
        ).to_excel(ruta, index=False)
        return ruta

    def a_salidas(self) -> list["TrabajoSalida"]:
        """Los `TrabajoSalida` de lo que se puede generar ya, en el orden de la cola."""
        return [t.a_salida() for t in self.listos_para_generar()]

    def importar_excel(self, ruta: Path | str) -> tuple[int, list[str]]:
        """Carga un Excel de lote (`RFC`/`FECHAS`, y `num`/`Nombre`/`ACCION` si vienen).

        Devuelve (cuantos entraron, avisos). No lanza por una fila mala: la salta y lo
        reporta, para que un renglon roto no tire la importacion completa.
        """
        df = pd.read_excel(ruta, dtype=str).fillna("")
        columnas = {str(c).strip().upper(): c for c in df.columns}
        if "FECHAS" not in columnas:
            raise ValueError("El Excel debe tener al menos las columnas RFC y FECHAS.")

        def celda(fila, nombre: str) -> str:
            columna = columnas.get(nombre)
            return "" if columna is None else str(fila[columna]).strip()

        entraron, avisos = 0, []
        for pos, fila in df.iterrows():
            rfc = celda(fila, "RFC").upper()
            proveedor = celda(fila, "NUM")
            if not (rfc or proveedor):
                continue
            try:
                self.agregar(
                    crear_trabajo(
                        proveedor,
                        celda(fila, "FECHAS"),
                        rfc=rfc,
                        nombre=celda(fila, "NOMBRE"),
                        accion=celda(fila, "ACCION") or ACCION_PREDETERMINADA,
                    )
                )
                entraron += 1
            except ValueError as exc:
                avisos.append(f"Fila {pos + 2}: {exc}")
        return entraron, avisos
