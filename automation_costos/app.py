"""GUI de Automation Costos — PRGX Soriana Audit Suite.

Tres vistas, no "etapas". La pregunta del usuario al abrir no es "¿que etapa?" sino
**"¿cuantos proveedores?"**, y la interfaz se organiza por eso:

- **Un proveedor** — el trabajo del dia. Un boton para hacerlo todo de corrido, y debajo la
  lista de pasos numerada para cuando el auditor edita el Compras en Excel a medio camino.
- **Por lotes** — la cola: varios proveedores, cada uno con su periodo y con que hacerle.
- **Ajustes** — credenciales de CPA Vision, carpetas, conexion y tema. Se tocan una vez.

Agrupar por "Etapa 1 / Etapa 2" describia como se construyo el codigo, no como se trabaja.
La prueba fue la pregunta de una auditora: *"le di a generar Compras, luego a descargar
CPA... ¿ahora que?"*. La lista de pasos existe para contestar eso sin preguntar.

La presentacion (paleta, barra de estado, pasos) vive en `ui.py`, que ademas documenta el
presupuesto de recursos: esto corre en equipos de un solo nucleo.
"""

from __future__ import annotations

import queue
import threading
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

import config
from automation_costos import cola_descarga, ui
from automation_costos.cancelacion import CancelacionSolicitada
from automation_costos.database import (
    fetch_compras,
    resolver_proveedor,
    resolver_rfc,
    test_connection,
)
from automation_costos.excel_exporter import write_compras_workbook
from automation_costos.recalculate import recalculate_compras_file
from automation_costos.utils import clean_code, safe_filename
from automation_costos.validation_exporter import write_validation_workbook

# Periodo por omisión de la auditoría. Se deja como constante (y no calculado desde la fecha
# de hoy) porque el alcance lo fija el cliente, no el calendario: cambiarlo debe ser una
# decisión explícita, no algo que se mueva solo al cambiar de año.
PERIODO_INICIAL = "2020-01-01"
PERIODO_FINAL = "2026-01-31"

#: Como se pinta cada estado de la cola: (etiqueta de color de `ui.tabla`, texto).
_ESTADO_COLA = {
    cola_descarga.PENDIENTE: ("pendiente", "en espera"),
    cola_descarga.CORRIENDO: ("corriendo", "⏳  en curso"),
    cola_descarga.OK: ("ok", "✓  listo"),
    cola_descarga.SIN_VALORES: ("aviso", "⊘  sin valores en el portal"),
    cola_descarga.OMITIDO: ("aviso", "⊘  ya estaba entregado"),
    cola_descarga.ERROR: ("error", "✗  error"),
}
#: Media real medida sobre 530 intentos de descarga (docs/ESTADO_ACTUAL.md): 7 m 52 s.
_MINUTOS_POR_PROVEEDOR = 7.9
#: Media de las corridas del bloque 1 (`outputs/logs/bloque1_*.txt`). Es una referencia
#: gruesa a proposito: un proveedor gigante se lleva horas y uno chico minutos.
_MINUTOS_POR_SALIDA = 12.0
#: A partir de cuantos proveedores pendientes se muestra el tiempo estimado.
#: Con menos NO se enseña: los dos numeros de arriba son promedios, y sobre dos o tres
#: proveedores el promedio no promedia nada — un gigante solo ya se lleva horas. Un
#: estimado que puede errar por un factor de diez es peor que no dar ninguno.
MINIMO_PARA_ESTIMAR = 4

#: Alto de la bitácora desplegada. Fijo a propósito: en pantallas chicas el alto variable
#: se lo quitaba a la vista, que es donde están los botones.
ALTO_BITACORA = 130

VISTA_PROVEEDOR = "Un proveedor"
VISTA_LOTES = "Por lotes"
VISTA_AJUSTES = "Ajustes"
VISTAS = (VISTA_PROVEEDOR, VISTA_LOTES, VISTA_AJUSTES)

#: Los pasos de un proveedor, en el orden en que se usan: (clave, título, método).
#: La clave es la misma que recibe `_ejecutar`, y por eso el paso que corre se resalta solo.
#: **Ninguno bloquea a otro**: el resaltado marca la ruta habitual, no un candado.
PASOS_PROVEEDOR = (
    ("extraer", "Generar Compras preliminar", "_extraer_compras"),
    ("descarga", "Descargar de CPA Vision", "_descargar_cpa"),
    ("cruce", "Rellenar EDI con los CFDI", "_cruzar_cpa"),
    ("recalcular", "Recalcular el Compras editado", "_recalcular"),
    ("validar", "Generar Validación de Condiciones", "_validar"),
)

_TOKENS_ERROR = ("error", "exception", "traceback")
_TOKENS_OK = (
    "generado", "generada", "correcta", "completad", "cruzados", "salida:",
    "descargado", "parquet.", "✓",
)


class CostosApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.tema = ui.Tema("light")
        self.mensajes: queue.Queue[str] = queue.Queue()
        # Trabajo que los hilos de fondo necesitan que ejecute el hilo de la UI.
        self.acciones: queue.Queue[tuple] = queue.Queue()
        self._ocupado = False
        #: Clave del paso que corre ahora mismo, para resaltarlo en la lista.
        self._corriendo: str | None = None
        #: Vistas ya construidas. Se crean la PRIMERA vez que se visitan y después solo se
        #: ocultan: crear widgets Tk es lo caro, tenerlos ocultos no cuesta.
        self._vistas: dict[str, ctk.CTkFrame] = {}
        self._pasos: dict[str, ui.Paso] = {}
        #: Memoria de "este RFC ya está en el Parquet", para no golpear la unidad de red en
        #: cada repintado de la lista de pasos.
        self._cache_parquet: dict[tuple[str, str], bool] = {}
        #: La bitácora nace desplegada, pero se puede plegar para recuperar su alto.
        self._bitacora_abierta = True
        # Cancelación cooperativa: el botón "Detener" la activa y el trabajo la atiende en su
        # siguiente punto seguro. No se mata el hilo (dejaría archivos a medias).
        self._cancelacion = threading.Event()

        self.proveedor = ctk.StringVar(value="")
        self.fecha_inicial = ctk.StringVar(value=PERIODO_INICIAL)
        self.fecha_final = ctk.StringVar(value=PERIODO_FINAL)
        self.carpeta_salida = ctk.StringVar(value=str(config.ENTREGABLES_DIR))
        self.archivo_editado = ctk.StringVar(value="")
        self.archivo_recalculado = ctk.StringVar(value="")
        self.archivo_validacion = ctk.StringVar(value="")
        self.vista = ctk.StringVar(value=VISTA_PROVEEDOR)
        self.rfc = ctk.StringVar(value="")
        self.carpeta_parquet = ctk.StringVar(value=str(config.CPA_VISION_PARQUET_DIR))
        self.carpeta_cpa = ctk.StringVar(value=str(config.CPA_VISION_DOWNLOAD_DIR))
        self.cpa_usuario = ctk.StringVar(value=config.CPA_VISION_USER)
        self.cpa_password = ctk.StringVar(value=config.CPA_VISION_PASSWORD)
        self.cpa_sin_ventana = ctk.BooleanVar(value=config.CPA_VISION_HEADLESS)

        # Cola de descarga por lotes. Se recupera del disco: una tanda dura horas y cerrar
        # la ventana no puede costar la lista.
        self.cola = cola_descarga.Cola.cargar()
        self.cola_proveedor = ctk.StringVar(value="")
        self.cola_fechas = ctk.StringVar(value="2020-2025")
        self.cola_accion = ctk.StringVar(
            value=cola_descarga.ACCIONES[cola_descarga.ACCION_PREDETERMINADA].etiqueta
        )

        # La lista de pasos se recalcula sola cada vez que cambia alguna de las rutas, sin
        # importar quién las cambió: así el mapa siempre refleja el estado real.
        for variable in (
            self.archivo_editado, self.archivo_recalculado, self.archivo_validacion, self.rfc
        ):
            variable.trace_add("write", self._refrescar_pasos)
        # La carpeta de salida se elige en Ajustes pero se anuncia en las otras dos vistas.
        self.carpeta_salida.trace_add("write", self._refrescar_aviso_salida)

        ctk.set_appearance_mode(self.tema.modo)
        ctk.set_default_color_theme("dark-blue")
        self._configurar_ventana()
        self._construir()
        self._procesar_mensajes()
        self._log("Listo. «Un proveedor» para el trabajo del día, «Por lotes» para una tanda.")

    # -- Ventana ------------------------------------------------------------

    def _configurar_ventana(self) -> None:
        self.title("Automation Costos — PRGX")
        self.geometry("1160x900")
        self.minsize(1000, 740)
        self.configure(fg_color=self.tema("bg1"))
        if ui.ICONO_PRGX.exists():
            try:
                from PIL import ImageTk

                self._icono = ImageTk.PhotoImage(Image.open(ui.ICONO_PRGX).resize((32, 32)))
                self.iconphoto(True, self._icono)
            except Exception:
                pass

    def _construir(self) -> None:
        # 0 encabezado · 2 pestañas · 3 vista · 4 estado · 5 bitácora
        # Solo la vista crece: la bitácora ocupa lo que mide y el resto es de alto fijo.
        self.grid_rowconfigure(3, weight=1)
        self.grid_rowconfigure(5, weight=0)
        self.grid_columnconfigure(0, weight=1)
        self._encabezado()
        marco_pestanas = ctk.CTkFrame(self, fg_color=self.tema("bg1"), corner_radius=0)
        marco_pestanas.grid(row=2, column=0, sticky="ew")
        self.pestanas = ui.Pestanas(
            marco_pestanas, self.tema, variable=self.vista,
            valores=list(VISTAS), al_cambiar=self._mostrar_vista,
        )
        self._area_vistas()
        marco_estado = ctk.CTkFrame(self, fg_color="transparent")
        marco_estado.grid(row=4, column=0, sticky="ew")
        self.estado = ui.BarraEstado(marco_estado, self.tema, al_detener=self._detener)
        self._area_bitacora()

    # -- Vistas -------------------------------------------------------------

    def _area_vistas(self) -> None:
        # Con scroll, y a propósito. Medido: las vistas piden entre 684 y 752 px, y con el
        # encabezado, el contexto, las pestañas, la barra de estado y la bitácora no caben
        # en 900 px — menos aún en una pantalla de 1366x768, que es lo que hay en los
        # equipos de destino. Sin esto, lo que se pierde es justamente el borde inferior:
        # el botón de ejecutar. Es UN canvas para las tres vistas, no uno por vista; el
        # ahorro de recursos vino de construir solo la vista activa y de dejar una sola
        # barra de progreso, no de quitar el scroll.
        self.contenedor = ctk.CTkScrollableFrame(
            self, fg_color=self.tema("bg1"), corner_radius=0
        )
        self.contenedor.grid(row=3, column=0, sticky="nsew")
        self.contenedor.grid_columnconfigure(0, weight=1)
        self.contenedor.grid_rowconfigure(0, weight=1)
        self._mostrar_vista(self.vista.get())

    def _mostrar_vista(self, nombre: str) -> None:
        """Enseña una vista, construyéndola si es la primera vez.

        Antes se construían las tres tarjetas de golpe dentro de un `CTkScrollableFrame`:
        343 widgets y 100 canvas al abrir, en máquinas de un núcleo. Ahora nace solo lo que
        se mira, y lo ya construido se oculta con `grid_remove()` en vez de destruirse —
        crear widgets Tk es lo caro, tenerlos ocultos no.
        """
        # La pestaña también se puede cambiar por código (al reconstruir el tema, o en una
        # prueba), así que el resaltado se sincroniza aquí y no solo al hacer clic.
        self.vista.set(nombre)
        pestanas = getattr(self, "pestanas", None)
        if pestanas is not None and self._widget("contenedor") is not None:
            pestanas.pintar()
        for otro, marco in self._vistas.items():
            if otro != nombre:
                marco.grid_remove()
        marco = self._vistas.get(nombre)
        if marco is None:
            marco = ctk.CTkFrame(self.contenedor, fg_color="transparent")
            marco.grid(row=0, column=0, sticky="nsew")
            self._vistas[nombre] = marco
            {
                VISTA_PROVEEDOR: self._vista_proveedor,
                VISTA_LOTES: self._vista_lotes,
                VISTA_AJUSTES: self._vista_ajustes,
            }[nombre](marco)
        marco.grid()

    # -- Encabezado ---------------------------------------------------------

    def _encabezado(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=self.tema("bg2"), corner_radius=0, height=76)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkFrame(hdr, fg_color=self.tema("accent"), height=3, corner_radius=0).grid(
            row=0, column=0, columnspan=6, sticky="ew"
        )

        if ui.ICONO_PRGX.exists():
            icono = ctk.CTkImage(Image.open(ui.ICONO_PRGX), size=(42, 42))
            ctk.CTkLabel(hdr, image=icono, text="").grid(row=1, column=0, padx=(18, 10), pady=10)

        titulo = ctk.CTkFrame(hdr, fg_color="transparent")
        titulo.grid(row=1, column=1, sticky="w", pady=10)
        ctk.CTkLabel(
            titulo,
            text="Automation Costos",
            font=ctk.CTkFont(ui.FUENTE, 17, weight="bold"),
            text_color=self.tema("t1"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            titulo,
            text="PRGX  ·  Soriana Audit Suite",
            font=ctk.CTkFont(ui.FUENTE, 10),
            text_color=self.tema("t2"),
        ).pack(anchor="w")

        if ui.LOGO_SORIANA.exists():
            logo = ctk.CTkImage(Image.open(ui.LOGO_SORIANA), size=(140, 40))
            ctk.CTkLabel(hdr, image=logo, text="").grid(row=1, column=2, padx=(0, 14), pady=10)

        # El botón de tema vive ahora en la vista de Ajustes: se toca una vez y en el
        # encabezado costaba un canvas permanente.

    # -- Vista: un proveedor ------------------------------------------------

    def _vista_proveedor(self, parent: ctk.CTkFrame) -> None:
        # Proveedor y periodo viven AQUI, no en una barra común: solo esta vista trabaja
        # sobre un proveedor concreto. En «Por lotes» cada renglón trae el suyo, y en
        # «Ajustes» no pintan nada. La carpeta de salida sí es compartida, y por eso está
        # con las demás carpetas en Ajustes.
        quien = ui.bloque(parent, self.tema)
        ui.rotulo(quien, self.tema, titulo="Proveedor a trabajar")
        fila = ctk.CTkFrame(quien, fg_color="transparent")
        fila.pack(fill="x", padx=14)
        ui.campo(fila, self.tema, etiqueta="Número", variable=self.proveedor, ancho=110)
        ui.campo(fila, self.tema, etiqueta="Desde", variable=self.fecha_inicial, ancho=110)
        ui.campo(fila, self.tema, etiqueta="Hasta", variable=self.fecha_final, ancho=110)
        ui.boton_secundario(
            fila, self.tema, texto="↺  Limpiar", comando=self._limpiar_campos, ancho=100
        )
        self.aviso_salida = ui.pista(quien, self.tema, "")
        self._refrescar_aviso_salida()

        rapido = ui.bloque(parent, self.tema)
        ui.rotulo(
            rapido, self.tema,
            titulo="Camino rápido",
            subtitulo="Compras → cruce con CPA → recálculo → Validación, de corrido y sin intervención",
        )
        ui.boton_cta(
            rapido, self.tema, texto="▶     GENERAR TODO", comando=self._generar_salida,
            subtitulo="Usa el proveedor y el periodo de arriba. Necesita el Parquet ya descargado.",
        )
        ctk.CTkFrame(rapido, fg_color="transparent", height=10).pack()

        detalle = ui.bloque(parent, self.tema)
        ui.rotulo(
            detalle, self.tema,
            titulo="Paso a paso",
            subtitulo="Para cuando el auditor edita el Compras en Excel antes de validar",
        )
        self._pasos = {
            clave: ui.Paso(
                detalle, self.tema, numero=n, titulo=titulo, comando=getattr(self, metodo)
            )
            for n, (clave, titulo, metodo) in enumerate(PASOS_PROVEEDOR, start=1)
        }
        ui.pista(
            detalle, self.tema,
            "Puedes saltarte cualquier paso: el resaltado marca la ruta habitual, no un candado.",
        )
        # Deja a la vista QUE archivo se validaria, antes de hacer clic: es la defensa
        # contra generar la Validacion de un proveedor con el Compras de otro.
        self.aviso_validacion = ui.aviso(detalle, self.tema)
        self._selector(detalle, "Compras editado", self.archivo_editado)
        self._selector(detalle, "Compras recalculado", self.archivo_recalculado)
        ctk.CTkFrame(detalle, fg_color="transparent", height=8).pack()
        self._refrescar_pasos()

    # -- Vista: por lotes ---------------------------------------------------

    def _vista_lotes(self, parent: ctk.CTkFrame) -> None:
        card = ui.bloque(parent, self.tema)
        ui.rotulo(
            card, self.tema,
            titulo="Cola de trabajo",
            subtitulo="Varios proveedores, cada uno con su periodo y con qué hacerle · se corren uno por uno",
        )

        alta = ctk.CTkFrame(card, fg_color="transparent")
        alta.pack(fill="x", padx=14)
        ui.campo(alta, self.tema, etiqueta="Proveedor", variable=self.cola_proveedor, ancho=100)
        ui.campo(alta, self.tema, etiqueta="Periodo", variable=self.cola_fechas, ancho=130)
        ui.opciones(
            alta, self.tema, etiqueta="Qué hacer", variable=self.cola_accion,
            valores=cola_descarga.ETIQUETAS_ACCION, ancho=215,
            al_cambiar=lambda _: self._refrescar_ayuda_accion(),
        )
        self.boton_agregar = ui.boton_secundario(
            alta, self.tema, texto="+  Agregar", comando=self._cola_agregar, ancho=100
        )
        # Qué significa la acción elegida, en letra chica y siempre a la vista: son cuatro
        # opciones parecidas entre sí y el nombre solo no alcanza.
        self.ayuda_accion = ui.pista(card, self.tema, "")
        self._refrescar_ayuda_accion()
        ui.pista(card, self.tema, "Periodo: «2020-2025» o años sueltos «2021 2023 2025»")
        self.aviso_cola = ui.aviso(card, self.tema)

        self.tabla_cola = ui.tabla(
            card,
            self.tema,
            columnas=[
                ("num", "#", 34),
                ("proveedor", "Proveedor", 80),
                ("nombre", "Nombre", 210),
                ("periodo", "Periodo", 110),
                ("accion", "Qué hacer", 150),
                ("estado", "Estado", 220),
            ],
            alto=7,
        )

        acciones = ctk.CTkFrame(card, fg_color="transparent")
        acciones.pack(fill="x", padx=14, pady=(0, 4))
        for texto, comando, ancho in (
            ("↑", lambda: self._cola_mover(-1), 34),
            ("↓", lambda: self._cola_mover(1), 34),
            ("Cambiar qué hacer", self._cola_cambiar_accion, 140),
            ("Reintentar", self._cola_reintentar, 90),
            ("Quitar", self._cola_quitar, 74),
            ("Limpiar", self._cola_limpiar, 78),
            ("Importar", self._cola_importar, 84),
            ("Exportar", self._cola_exportar, 84),
        ):
            ui.boton_secundario(acciones, self.tema, texto=texto, comando=comando, ancho=ancho)

        ui.boton_cta(
            card, self.tema, texto="▶     EJECUTAR LA COLA", comando=self._cola_ejecutar,
            subtitulo="Primero baja todo lo que haya que bajar y después genera, así "
                      "«Descargar y generar» sale de un solo clic.",
        )
        ui.pista(
            card, self.tema,
            "El portal encola por usuario: se descarga uno a la vez. No abras otra descarga en paralelo.",
        )
        # También aquí se generan entregables, así que hay que ver dónde caen.
        self.aviso_salida_lotes = ui.pista(card, self.tema, "")
        self._refrescar_aviso_salida()
        ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        self._cola_pintar()

    def _widget(self, nombre: str):
        """El widget de una vista, o `None` si no existe **o ya fue destruido**.

        Los widgets de las vistas se guardan como atributos (`self.tabla_cola`,
        `self.aviso_cola`...), y al cambiar de tema la ventana se reconstruye entera: los
        atributos siguen apuntando a widgets muertos y configurarlos revienta con
        `TclError`. Un `getattr(...) is not None` no lo detecta; `winfo_exists()` sí.
        """
        widget = getattr(self, nombre, None)
        try:
            return widget if widget is not None and widget.winfo_exists() else None
        except Exception:  # noqa: BLE001 — un widget muerto ni siquiera contesta
            return None

    def _refrescar_ayuda_accion(self) -> None:
        """Muestra qué hace la acción elegida en el desplegable."""
        etiqueta = self._widget("ayuda_accion")
        if etiqueta is None:
            return
        try:
            accion = cola_descarga.ACCIONES[cola_descarga.clave_accion(self.cola_accion.get())]
        except ValueError:
            return
        etiqueta.configure(text=f"  {accion.ayuda}")

    def _refrescar_aviso_salida(self, *_) -> None:
        """Deja visible en qué carpeta caen los entregables, se mire la vista que se mire."""
        texto = f"Los entregables se guardan en:  {self.carpeta_salida.get().strip()}"
        for nombre in ("aviso_salida", "aviso_salida_lotes"):
            etiqueta = self._widget(nombre)
            if etiqueta is not None:
                etiqueta.configure(text=f"  {texto}")

    def _cola_pintar(self) -> None:
        """Repinta la tabla desde el modelo. Solo desde el hilo de la interfaz."""
        tabla = self._widget("tabla_cola")
        if tabla is None:
            return
        tabla.delete(*tabla.get_children())
        for i, t in enumerate(self.cola, start=1):
            etiqueta, texto = _estado_visible(t)
            tabla.insert(
                "", "end", iid=str(i - 1),
                values=(i, t.identidad, t.nombre or "—", t.fechas, t.plan.etiqueta, texto),
                tags=(etiqueta,),
            )
        self._cola_avisar(self._cola_resumen())
        if self._ocupado and self.cola:
            # Progreso real de la tanda: renglones sin nada pendiente, sobre el total. Sale
            # del modelo y no de lo que reporte cada motor, así vale para las dos fases.
            self.estado.progreso(len(self.cola) - len(self.cola.pendientes()), len(self.cola))
        self.cola.guardar()

    def _cola_resumen(self) -> str:
        """Qué queda por hacer y cuánto tardaría, en una línea."""
        descargas, salidas = len(self.cola.por_descargar()), len(self.cola.por_generar())
        if not (descargas or salidas):
            return f"{len(self.cola)} en la cola  ·  nada pendiente"
        partes = []
        if descargas:
            partes.append(f"{descargas} por descargar")
        if salidas:
            partes.append(f"{salidas} por generar")
        # El estimado solo aparece cuando hay bastantes proveedores como para que los
        # promedios signifiquen algo. Ver `MINIMO_PARA_ESTIMAR`.
        if len(self.cola.pendientes()) >= MINIMO_PARA_ESTIMAR:
            minutos = descargas * _MINUTOS_POR_PROVEEDOR + salidas * _MINUTOS_POR_SALIDA
            partes.append(f"~{minutos:,.0f} min estimados")
        return f"{len(self.cola)} en la cola  ·  " + "  ·  ".join(partes)

    def _cola_seleccion(self) -> list[int]:
        return sorted(int(i) for i in self.tabla_cola.selection())

    def _cola_avisar(self, texto: str, color: str = "t2") -> None:
        etiqueta = self._widget("aviso_cola")
        if etiqueta is not None:
            etiqueta.configure(text=f"  {texto}", text_color=self.tema(color))

    def _cola_agregar(self) -> None:
        """Valida el periodo al instante y resuelve RFC+nombre contra SQL en segundo plano."""
        try:
            trabajo = cola_descarga.crear_trabajo(
                self.cola_proveedor.get(), self.cola_fechas.get(),
                accion=self.cola_accion.get(),
            )
            if self.cola.indice_de(trabajo.proveedor) is not None:
                raise ValueError(f"El proveedor {trabajo.proveedor} ya está en la cola.")
        except ValueError as exc:
            self._cola_avisar(str(exc), "s_err")
            return

        self.boton_agregar.configure(state="disabled")
        self._cola_avisar(f"Resolviendo el proveedor {trabajo.proveedor} en SQL Server...")

        def resolver() -> None:
            try:
                inicio, fin = trabajo.periodo_sql()
                trabajo.rfc, trabajo.nombre = resolver_proveedor(trabajo.proveedor, inicio, fin)
            except Exception as exc:  # noqa: BLE001 — se reporta en la interfaz
                self._en_ui(self._cola_avisar, f"No se pudo consultar SQL: {exc}", "s_err")
            else:
                if trabajo.rfc:
                    self.cola.agregar(trabajo)
                    self._en_ui(self._cola_agregado, trabajo)
                else:
                    self._en_ui(
                        self._cola_avisar,
                        f"El proveedor {trabajo.proveedor} no tiene compras en {trabajo.fechas}.",
                        "s_err",
                    )
            finally:
                self._en_ui(self._cola_habilitar_agregar, True)

        threading.Thread(target=resolver, daemon=True).start()

    def _cola_habilitar_agregar(self, activo: bool) -> None:
        self.boton_agregar.configure(state="normal" if activo else "disabled")

    def _cola_agregado(self, trabajo: cola_descarga.Trabajo) -> None:
        self.cola_proveedor.set("")
        self._cola_pintar()
        self._log(f"En cola: {trabajo.proveedor} · {trabajo.nombre} · {trabajo.rfc} · {trabajo.fechas}")

    def _cola_quitar(self) -> None:
        seleccion = self._cola_seleccion()
        if not seleccion:
            self._cola_avisar("Selecciona en la tabla qué quitar.", "s_err")
            return
        self.cola.quitar(seleccion)
        self._cola_pintar()

    def _cola_cambiar_accion(self) -> None:
        """Aplica a lo seleccionado la acción elegida arriba."""
        seleccion = self._cola_seleccion()
        if not seleccion:
            self._cola_avisar("Selecciona en la tabla a qué renglones aplicarlo.", "s_err")
            return
        try:
            cambiados = self.cola.cambiar_accion(seleccion, self.cola_accion.get())
        except ValueError as exc:
            self._cola_avisar(str(exc), "s_err")
            return
        self._cola_pintar()
        self._cola_avisar(f"{cambiados} renglón(es) → «{self.cola_accion.get()}»")

    def _cola_reintentar(self) -> None:
        """Vuelve a poner en espera lo seleccionado, incluido lo que ya estaba listo."""
        seleccion = self._cola_seleccion()
        if not seleccion:
            self._cola_avisar("Selecciona en la tabla qué reintentar.", "s_err")
            return
        for i in seleccion:
            self.cola.trabajos[i].reiniciar()
        self._cola_pintar()

    def _cola_mover(self, delta: int) -> None:
        seleccion = self._cola_seleccion()
        if len(seleccion) != 1:
            self._cola_avisar("Selecciona una sola fila para moverla.", "s_err")
            return
        nueva = self.cola.mover(seleccion[0], delta)
        self._cola_pintar()
        self.tabla_cola.selection_set(str(nueva))

    def _cola_limpiar(self) -> None:
        if self.cola and not messagebox.askyesno("Limpiar cola", "¿Vaciar la cola completa?"):
            return
        self.cola.limpiar()
        self._cola_pintar()

    def _cola_importar(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Excel de lote (RFC / FECHAS)", filetypes=[("Excel", "*.xlsx *.xls")]
        )
        if not ruta:
            return
        try:
            entraron, avisos = self.cola.importar_excel(ruta)
        except Exception as exc:  # noqa: BLE001
            self._cola_avisar(f"No se pudo importar: {exc}", "s_err")
            return
        self._cola_pintar()
        self._log(f"Importados {entraron} proveedores desde {Path(ruta).name}")
        for aviso in avisos[:10]:
            self._log(f"  omitido · {aviso}")

    def _cola_exportar(self) -> None:
        if not self.cola:
            self._cola_avisar("La cola está vacía.", "s_err")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar la cola", defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")], initialfile="lote_cpa_vision.xlsx",
        )
        if not ruta:
            return
        try:
            self.cola.a_excel(ruta, solo_pendientes=False)
        except Exception as exc:  # noqa: BLE001
            self._cola_avisar(f"No se pudo exportar: {exc}", "s_err")
            return
        self._log(f"Cola exportada: {ruta}")

    def _cola_ejecutar(self) -> None:
        """Corre la cola: primero TODAS las descargas, después TODAS las salidas.

        El orden no es casual. Un renglón «Descargar y generar» necesita que su descarga ya
        esté en el Parquet antes de que el pipeline lo lea; haciéndolo por fases, el usuario
        arma la tanda completa y da un solo clic.
        """
        descargas, salidas = self.cola.por_descargar(), self.cola.por_generar()
        if not (descargas or salidas):
            self._cola_avisar("No hay nada pendiente en la cola.", "s_err")
            return

        # Todo lo que se lee de la interfaz se captura AQUI, en el hilo de Tk: el hilo de
        # fondo no puede tocar widgets (ver `_en_ui`).
        usuario, password = self.cpa_usuario.get().strip(), self.cpa_password.get()
        if descargas and not (usuario and password):
            messagebox.showerror(
                "Credenciales CPA Vision", "Captura el usuario y la contraseña de CPA Vision."
            )
            return
        carpeta_descargas = self.carpeta_cpa.get().strip() or None
        parquet = self.carpeta_parquet.get().strip() or None
        sin_ventana = bool(self.cpa_sin_ventana.get())
        carpeta_salida = Path(self.carpeta_salida.get().strip() or config.ENTREGABLES_DIR)
        if salidas and not carpeta_salida.parent.exists():
            messagebox.showerror(
                "Ruta inválida", f"No existe la carpeta de salida:\n{carpeta_salida}"
            )
            return

        def tarea() -> None:
            if descargas:
                self._cola_fase_descarga(
                    usuario=usuario, password=password, descargas=carpeta_descargas,
                    parquet=parquet, sin_ventana=sin_ventana, total=len(descargas),
                )
            if salidas:
                self._cola_fase_salida(salida=carpeta_salida, parquet=parquet)

        self._ejecutar("cola", f"Ejecutando la cola · {self._cola_resumen()}", tarea)

    def _cola_fase_descarga(
        self, *, usuario: str, password: str, descargas, parquet, sin_ventana: bool, total: int
    ) -> None:
        """Fase 1: pedirle los CFDI al portal. Corre en el hilo de fondo."""
        from automation_costos.cpa_vision import CPAVisionSettings, request_vendor_master_batch

        # El motor consume un Excel `RFC`/`FECHAS`; se le arma uno temporal con lo pendiente
        # para no reimplementar nada del scraping.
        lote = self.cola.a_excel(config.LOG_DIR / "cola_lote.xlsx")
        self._log(f"— Descargas: {total} proveedor(es), uno a la vez.")

        request_vendor_master_batch(
            CPAVisionSettings.from_overrides(download_dir=descargas, headless=sin_ventana),
            vendor_master_path=lote,
            username=usuario,
            password=password,
            batch_size=total,
            parquet_dir=parquet,
            progreso=lambda datos: self._en_ui(self._cola_progreso, datos),
            cancelado=self._cancelacion.is_set,
        )
        self._log("✓ Descargas terminadas.")

    def _cola_fase_salida(self, *, salida: Path, parquet) -> None:
        """Fase 2: generar los entregables con el MISMO motor que usa la terminal.

        Corre en el hilo de fondo. No decide nada por su cuenta: periodo, camino de
        proveedor gigante y alcance del cruce salen de `ejecutor`, igual que en
        `scripts/ejecutar_bloque1.py`.
        """
        from automation_costos import ejecutor
        from automation_costos.database import contar_compras

        trabajos = self.cola.listos_para_generar()
        if not trabajos:
            self._log("Nada que generar: las descargas que hacían falta no terminaron bien.")
            return

        self._log(f"— Entregables: {len(trabajos)} proveedor(es).")
        # El número de renglones decide si el proveedor cabe en memoria o va por trimestres.
        # Es un COUNT en el servidor (segundos), no trae las compras.
        for trabajo in trabajos:
            if trabajo.renglones:
                continue
            periodo = trabajo.a_salida()  # aún con renglones=0: solo interesa su periodo
            trabajo.renglones = contar_compras(periodo.prov, periodo.inicio, periodo.fin)
            aviso = "  ·  GIGANTE, se hará por trimestres" if trabajo.renglones > ejecutor.UMBRAL_GRANDE else ""
            self._log(f"   {trabajo.proveedor}: {trabajo.renglones:,} renglones{aviso}")
        self._en_ui(self._cola_pintar)

        resultado = ejecutor.ejecutar(
            [t.a_salida() for t in trabajos],
            salida=salida,
            parquet=parquet,
            log=self._log,
            cancelado=self._cancelacion.is_set,
            progreso=lambda datos: self._en_ui(self._cola_progreso_salida, datos),
        )
        self._log(
            f"✓ Entregables: {resultado.ok} generados  ·  {resultado.fallos} con error  ·  "
            f"{resultado.omitidos} ya existían."
        )

    def _cola_progreso(self, datos: dict) -> None:
        """Avance de la DESCARGA. Solo desde el hilo de la interfaz."""
        indice = self.cola.indice_de_rfc(datos.get("rfc", ""))
        if indice is None:
            return
        trabajo = self.cola.trabajos[indice]
        trabajo.estado = cola_descarga.estado_desde_motor(datos.get("estado", ""))
        trabajo.segundos = float(datos.get("segundos") or 0.0)
        trabajo.detalle = str(datos.get("error") or "")
        if trabajo.estado == cola_descarga.OK and datos.get("filas"):
            trabajo.detalle = f"{int(datos['filas']):,} filas"
        self._cola_pintar()

    def _cola_progreso_salida(self, datos: dict) -> None:
        """Avance de la GENERACIÓN. Solo desde el hilo de la interfaz.

        El motor identifica el trabajo por número de proveedor, que es lo único que conoce.
        """
        indice = self.cola.indice_de(str(datos.get("prov", "")))
        if indice is None:
            return
        trabajo = self.cola.trabajos[indice]
        trabajo.estado_salida = cola_descarga.estado_desde_motor(datos.get("estado", ""))
        trabajo.segundos_salida = float(datos.get("segundos") or 0.0)
        # Solo si falló: el nombre del log es lo único accionable, y es dónde está el porqué.
        trabajo.detalle_salida = (
            f"ver {Path(datos['log']).name}"
            if trabajo.estado_salida == cola_descarga.ERROR and datos.get("log")
            else ""
        )
        self._cola_pintar()

    # -- Vista: ajustes -----------------------------------------------------

    def _vista_ajustes(self, parent: ctk.CTkFrame) -> None:
        """Lo que se toca una vez y estorba en las vistas de trabajo."""
        card = ui.bloque(parent, self.tema)

        ui.grupo(card, self.tema, "CPA Vision")
        fila = ctk.CTkFrame(card, fg_color="transparent")
        fila.pack(fill="x", padx=14)
        # Credenciales del portal: las teclea el auditor, nunca se guardan en código.
        ui.campo(fila, self.tema, etiqueta="Usuario", variable=self.cpa_usuario, ancho=200)
        ui.campo(fila, self.tema, etiqueta="Contraseña", variable=self.cpa_password,
                 ancho=200, show="*")
        fila_modo = ctk.CTkFrame(card, fg_color="transparent")
        fila_modo.pack(fill="x", padx=14)
        ui.casilla(
            fila_modo, self.tema,
            texto="Descargar sin ventana (en segundo plano)",
            variable=self.cpa_sin_ventana,
        )

        ui.grupo(card, self.tema, "Carpetas")
        for etiqueta, variable, comando in (
            ("Salida (entregables)", self.carpeta_salida, self._elegir_salida),
            ("Parquet de CPA", self.carpeta_parquet, self._elegir_parquet),
            ("Descargas CPA", self.carpeta_cpa, self._elegir_cpa),
        ):
            fila = ctk.CTkFrame(card, fg_color="transparent")
            fila.pack(fill="x", padx=14)
            ui.campo(fila, self.tema, etiqueta=etiqueta, variable=variable, ancho=380)
            ui.boton_secundario(fila, self.tema, texto="Elegir", comando=comando)

        ui.grupo(card, self.tema, "Proveedor")
        fila = ctk.CTkFrame(card, fg_color="transparent")
        fila.pack(fill="x", padx=14)
        ui.campo(fila, self.tema, etiqueta="RFC (opcional)", variable=self.rfc, ancho=200)
        ui.pista(card, self.tema, "El RFC se detecta solo del Compras; llénalo solo para forzar otro")

        ui.grupo(card, self.tema, "Conexión y apariencia")
        fila = ctk.CTkFrame(card, fg_color="transparent")
        fila.pack(fill="x", padx=14)
        ui.boton_secundario(
            fila, self.tema, texto="⚡  Probar conexión a SQL Server",
            comando=self._probar_conexion, ancho=220,
        )
        ui.boton_secundario(
            fila, self.tema, texto=self.tema.etiqueta_boton,
            comando=self._alternar_tema, ancho=110,
        )
        ctk.CTkFrame(card, fg_color="transparent", height=10).pack()

    # -- La lista de pasos --------------------------------------------------

    def _refrescar_pasos(self, *_) -> None:
        """Repinta el mapa de pasos. Se dispara solo al cambiar cualquiera de las rutas.

        El estado sale de lo que hay **en disco y en los campos**, no de la última corrida:
        así reabrir la aplicación a media faena muestra el mismo mapa que al cerrarla.
        """
        self._refrescar_aviso_validacion()
        if not self._pasos:
            return
        hechos = self._pasos_hechos()
        siguiente = next((c for c, _, _ in PASOS_PROVEEDOR if c not in hechos), None)
        for clave, _, _ in PASOS_PROVEEDOR:
            paso = self._pasos[clave]
            if clave == self._corriendo:
                paso.estado("corriendo", "en curso…")
            elif clave in hechos:
                paso.estado("hecho", hechos[clave])
            elif clave == siguiente:
                paso.estado("siguiente", "←  siguiente")
            else:
                paso.estado("pendiente")

    def _pasos_hechos(self) -> dict[str, str]:
        """Qué pasos ya están hechos, y con qué detalle mostrarlo.

        Lo que NO se puede saber barato se deja como pendiente a propósito: es preferible
        que la lista se quede corta a que asegure algo falso.
        """
        hechos: dict[str, str] = {}
        editado = self.archivo_editado.get().strip()
        recalculado = self.archivo_recalculado.get().strip()
        validacion = self.archivo_validacion.get().strip()

        if editado or recalculado:
            hechos["extraer"] = Path(editado or recalculado).name[:30]
        if self._hay_parquet():
            hechos["descarga"] = f"{self.rfc.get().strip().upper()} en el Parquet"
        # El cruce deja su marca en el nombre del archivo, que es lo único que sobrevive a
        # cerrar la aplicación.
        if "_EDI" in Path(editado).stem.upper():
            hechos["cruce"] = "bloque EDI relleno"
        if recalculado:
            hechos["recalcular"] = Path(recalculado).name[:30]
        if validacion:
            hechos["validar"] = Path(validacion).name[:30]
        return hechos

    def _hay_parquet(self) -> bool:
        """¿El RFC en curso ya tiene datos descargados? Un `exists()` sobre la partición.

        Se memoriza porque el Parquet vive en una unidad de red y esto se consulta en cada
        repintado de la lista.
        """
        rfc = self.rfc.get().strip().upper()
        if not rfc:
            return False
        clave = (rfc, self.carpeta_parquet.get().strip())
        if clave not in self._cache_parquet:
            try:
                raiz = Path(clave[1] or config.CPA_VISION_PARQUET_DIR)
                self._cache_parquet[clave] = (raiz / f"rfc={rfc}").exists()
            except OSError:
                self._cache_parquet[clave] = False
        return self._cache_parquet[clave]

    def _selector(self, parent: ctk.CTkFrame, etiqueta: str, variable: ctk.StringVar) -> None:
        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.pack(fill="x", padx=14)
        ui.campo(fila, self.tema, etiqueta=etiqueta, variable=variable, ancho=250)
        ui.boton_secundario(
            fila, self.tema, texto="Elegir", comando=lambda: self._elegir_excel(variable)
        )

    # -- Bitacora -----------------------------------------------------------

    def _area_bitacora(self) -> None:
        """Bitácora plegable y de alto fijo.

        Antes se llevaba una porción variable de la ventana (`weight=2`), que en pantallas
        chicas es justo el espacio que le hace falta a la vista. Ahora ocupa lo que mide y
        nada más, y se puede plegar hasta dejar solo su título: `row=5` no crece nunca, así
        que todo el alto sobrante va al área de vistas.
        """
        marco = ctk.CTkFrame(self, fg_color=self.tema("bg2"), corner_radius=0)
        marco.grid(row=5, column=0, sticky="nsew")
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(1, weight=1)

        cabecera = ctk.CTkFrame(marco, fg_color="transparent")
        cabecera.grid(row=0, column=0, sticky="ew", padx=16, pady=(6, 2))
        self.boton_bitacora = ctk.CTkButton(
            cabecera,
            text="",
            width=150,
            height=22,
            font=ctk.CTkFont(ui.FUENTE, 9, weight="bold"),
            fg_color="transparent",
            hover_color=self.tema("card"),
            text_color=self.tema("t2"),
            corner_radius=4,
            anchor="w",
            command=self._alternar_bitacora,
        )
        self.boton_bitacora.pack(side="left")
        ctk.CTkButton(
            cabecera,
            text="Limpiar",
            width=60,
            height=22,
            font=ctk.CTkFont(ui.FUENTE, 10),
            fg_color=self.tema("card2"),
            hover_color=self.tema("card"),
            text_color=self.tema("t2"),
            corner_radius=4,
            command=self._limpiar_bitacora,
        ).pack(side="right")

        self.bitacora = ctk.CTkTextbox(
            marco,
            height=ALTO_BITACORA,
            fg_color=self.tema("bg2"),
            text_color=self.tema("t1"),
            font=ctk.CTkFont("Consolas", 11),
            border_width=0,
            corner_radius=0,
        )
        self.bitacora.grid(row=1, column=0, sticky="nsew")
        self.bitacora.configure(state="disabled")

        texto = self.bitacora._textbox
        texto.tag_configure("ts", foreground=self.tema("t2"))
        texto.tag_configure("info", foreground=self.tema("t1"))
        texto.tag_configure("ok", foreground=self.tema("s_ok"))
        texto.tag_configure("error", foreground=self.tema("s_err"))
        self._aplicar_bitacora()

    def _alternar_bitacora(self) -> None:
        self._bitacora_abierta = not self._bitacora_abierta
        self._aplicar_bitacora()

    def _aplicar_bitacora(self) -> None:
        """Pliega o despliega. El estado sobrevive al cambio de tema porque vive en `self`."""
        if self._bitacora_abierta:
            self.bitacora.grid()
            self.boton_bitacora.configure(text="▾   BITÁCORA DE EJECUCIÓN")
        else:
            self.bitacora.grid_remove()
            self.boton_bitacora.configure(text="▸   BITÁCORA DE EJECUCIÓN")

    def _log(self, mensaje: str) -> None:
        self.mensajes.put(f"[{datetime.now():%H:%M:%S}]  {mensaje}\n")

    def _escribir(self, linea: str) -> None:
        texto = self.bitacora._textbox
        texto.configure(state="normal")
        if "]  " in linea:
            marca, cuerpo = linea.split("]  ", 1)
            minusculas = cuerpo.lower()
            etiqueta = (
                "error"
                if any(t in minusculas for t in _TOKENS_ERROR)
                else "ok"
                if any(t in minusculas for t in _TOKENS_OK)
                else "info"
            )
            texto.insert("end", marca + "]  ", "ts")
            texto.insert("end", cuerpo, etiqueta)
        else:
            texto.insert("end", linea, "info")
        texto.see("end")
        texto.configure(state="disabled")

    def _limpiar_bitacora(self) -> None:
        self.bitacora.configure(state="normal")
        self.bitacora.delete("1.0", "end")
        self.bitacora.configure(state="disabled")

    def _procesar_mensajes(self) -> None:
        """Unico punto donde los hilos de fondo llegan a tocar la interfaz."""
        try:
            while True:
                self._escribir(self.mensajes.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                funcion, args = self.acciones.get_nowait()
                try:
                    funcion(*args)
                except Exception as exc:  # noqa: BLE001 — una accion rota no frena la cola
                    self._escribir(f"[UI] no se pudo aplicar un cambio: {exc}\n")
        except queue.Empty:
            pass
        self.after(120, self._procesar_mensajes)

    # -- Tema ---------------------------------------------------------------

    def _alternar_tema(self) -> None:
        """Reconstruye la ventana con la paleta nueva.

        Se bloquea mientras algo corre: destruir la barra de estado a media operación
        dejaría al hilo de fondo publicando en widgets que ya no existen. Es una restricción
        barata — nadie cambia de tema en mitad de una descarga de dos horas.
        """
        if self._ocupado:
            self._log("Hay una operación en curso; espera a que termine para cambiar el tema.")
            return
        contenido = self.bitacora.get("1.0", "end-1c")
        self.estado.reposo()  # detiene el reloj antes de destruir su widget
        self.tema.alternar()
        for hijo in self.winfo_children():
            hijo.destroy()
        # Las vistas y los pasos apuntaban a widgets que acaban de morir.
        self._vistas.clear()
        self._pasos.clear()
        self.configure(fg_color=self.tema("bg1"))
        self._construir()
        if contenido.strip():
            self.bitacora.configure(state="normal")
            self.bitacora.insert("1.0", contenido + "\n")
            self.bitacora.configure(state="disabled")

    # -- Dialogos -----------------------------------------------------------

    def _elegir_salida(self) -> None:
        elegido = filedialog.askdirectory(initialdir=self.carpeta_salida.get() or str(config.OUTPUT_DIR))
        if elegido:
            self.carpeta_salida.set(elegido)

    def _elegir_parquet(self) -> None:
        elegido = filedialog.askdirectory(initialdir=self.carpeta_parquet.get())
        if elegido:
            self.carpeta_parquet.set(elegido)

    def _elegir_cpa(self) -> None:
        elegido = filedialog.askdirectory(initialdir=self.carpeta_cpa.get())
        if elegido:
            self.carpeta_cpa.set(elegido)

    def _elegir_excel(self, variable: ctk.StringVar) -> None:
        elegido = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xlsm")])
        if elegido:
            variable.set(elegido)

    # -- Acciones -----------------------------------------------------------

    def _limpiar_campos(self) -> None:
        """Refresca los campos que cambian por proveedor, para preparar la siguiente corrida.

        Limpia proveedor, RFC y los archivos seleccionados. **Conserva** las fechas, la carpeta
        de salida, el Parquet y las credenciales de CPA Vision (valores que suelen repetirse
        entre proveedores de una misma sesión).
        """
        self.proveedor.set("")
        self.rfc.set("")
        self.archivo_editado.set("")
        self.archivo_recalculado.set("")
        self.archivo_validacion.set("")
        self.estado.reposo()
        self._log("Campos limpiados (se conservan fechas, salida, Parquet y credenciales).")

    def _probar_conexion(self) -> None:
        def tarea() -> None:
            test_connection()
            self._log("Conexión correcta.")

        self._ejecutar("conexion", "Probando conexión a SQL Server...", tarea)

    def _extraer_compras(self) -> None:
        proveedor = self.proveedor.get().strip()
        inicio = self.fecha_inicial.get().strip()
        fin = self.fecha_final.get().strip()
        if not (proveedor and inicio and fin):
            messagebox.showerror("Datos incompletos", "Captura proveedor, fecha inicial y fecha final.")
            return

        def tarea() -> None:
            df = fetch_compras(proveedor, inicio, fin)
            salida = self._ruta_salida(_nombre_compras(df, proveedor))
            write_compras_workbook(df, salida, vendor=proveedor, start_date=inicio, end_date=fin)
            self._fijar_compras(str(salida))
            self._log(f"Compras preliminar generado: {salida}")
            self._log(f"Filas extraídas: {len(df):,}")

        self._ejecutar("extraer", "Consultando compras en SQL Server...", tarea)

    def _recalcular(self) -> None:
        entrada = self._pedir_archivo(self.archivo_editado)
        if not entrada:
            return

        def tarea() -> None:
            salida = self._ruta_salida(f"{entrada.stem}_Recalculado.xlsx")
            recalculate_compras_file(entrada, salida)
            self._fijar(self.archivo_recalculado, str(salida))
            self._log(f"Compras recalculado generado: {salida}")

        self._ejecutar("recalcular", "Recalculando archivo de compras...", tarea)

    def _validar(self) -> None:
        ruta = self._archivo_para_validar()
        if not ruta:
            self._elegir_excel(self.archivo_recalculado)
            ruta = self._archivo_para_validar()
        if not ruta:
            return
        entrada = Path(ruta)
        # Se deja escrito en la bitacora el archivo exacto que se validó: si mas tarde hay
        # dudas sobre un entregable, aqui esta de que Compras salio.
        self._log(f"Validando sobre: {entrada.name}")

        def tarea() -> None:
            salida = self._ruta_salida(f"{entrada.stem}_Validacion_Condiciones.xlsx")
            write_validation_workbook(entrada, salida)
            self._fijar(self.archivo_validacion, str(salida))
            self._log(f"Validación generada: {salida}")

        self._ejecutar("validar", "Generando Validación de Condiciones...", tarea)

    def _descargar_cpa(self) -> None:
        proveedor = self.proveedor.get().strip()
        inicio = self.fecha_inicial.get().strip()
        fin = self.fecha_final.get().strip()
        if not (proveedor and inicio and fin):
            messagebox.showerror("Datos incompletos", "Captura proveedor, fecha inicial y fecha final.")
            return
        usuario = self.cpa_usuario.get().strip()
        password = self.cpa_password.get()
        if not (usuario and password):
            messagebox.showerror(
                "Credenciales CPA Vision", "Captura el usuario y la contraseña de CPA Vision."
            )
            return
        parquet = Path(self.carpeta_parquet.get().strip())
        descargas = self.carpeta_cpa.get().strip() or None
        rfc_forzado = self.rfc.get().strip().upper()
        sin_ventana = bool(self.cpa_sin_ventana.get())

        def tarea() -> None:
            from automation_costos.cpa_descarga import descargar_cpa_proveedor

            rfc = rfc_forzado
            if not rfc:
                self._log("Resolviendo el RFC del proveedor desde SQL Server...")
                rfc = resolver_rfc(proveedor, inicio, fin)
                if not rfc:
                    self._log(
                        "ERROR: no se pudo resolver el RFC (¿el proveedor no tiene compras en el periodo?)."
                    )
                    return
                self._fijar(self.rfc, rfc)
            self._log(f"RFC del proveedor: {rfc}")

            resultado = descargar_cpa_proveedor(
                rfc, inicio, fin,
                parquet_root=parquet,
                username=usuario,
                password=password,
                download_dir=descargas,
                log=self._log,
                headless=sin_ventana,
                cancelado=self._cancelacion.is_set,
            )
            self._fijar(self.carpeta_parquet, str(resultado.parquet_root))
            self._log(
                f"✓ CPA Vision descargado: {resultado.filas:,} filas listas en el Parquet."
            )

        self._ejecutar("descarga", "Descargando de CPA Vision (abre el portal)...", tarea)

    def _generar_salida(self) -> None:
        proveedor = self.proveedor.get().strip()
        inicio = self.fecha_inicial.get().strip()
        fin = self.fecha_final.get().strip()
        if not (proveedor and inicio and fin):
            messagebox.showerror("Datos incompletos", "Captura proveedor, fecha inicial y fecha final.")
            return
        parquet = Path(self.carpeta_parquet.get().strip())
        if not parquet.exists():
            messagebox.showerror("Ruta inválida", f"No existe la carpeta Parquet:\n{parquet}")
            return

        def tarea() -> None:
            from automation_costos.pipeline import generar_salida_proveedor

            resultado = generar_salida_proveedor(
                proveedor, inicio, fin, parquet, self.carpeta_salida.get().strip() or config.OUTPUT_DIR,
                log=self._log,
            )
            self._fijar_compras(str(resultado.compras_path))
            self._fijar(self.archivo_validacion, str(resultado.validacion_path))
            self._log(f"✓ Validación lista: {resultado.validacion_path}")

        self._ejecutar("salida", "Generando salida completa...", tarea)

    def _cruzar_cpa(self) -> None:
        parquet = Path(self.carpeta_parquet.get().strip())
        if not parquet.exists():
            messagebox.showerror("Ruta inválida", f"No existe la carpeta Parquet:\n{parquet}")
            return
        entrada = self._pedir_archivo(self.archivo_editado)
        if not entrada:
            return

        rfc_forzado = self.rfc.get().strip().upper() or None

        def tarea() -> None:
            from automation_costos.cruce_cpa import cruzar_proveedor

            resultado, rfc = cruzar_proveedor(entrada, parquet, rfc=rfc_forzado)
            self._log(f"RFC del proveedor: {rfc}")
            if resultado.cruzados == 0:
                self._log("ERROR: no se cruzó ningún renglón (¿RFC sin datos en el Parquet?).")
                return
            for linea in resultado.resumen().splitlines():
                self._log(linea)

            # El resumen tambien queda por escrito: antes solo vivia en esta ventana y se
            # perdia al cerrarla. Se marca como "cruce manual" para distinguirlo de las
            # ejecuciones que sI produjeron un entregable completo.
            from automation_costos.metricas_cruce import fila_desde_resultado
            from automation_costos.metricas_cruce import registrar as registrar_metricas
            from automation_costos.utils import clean_code

            proveedor = ""
            nombre = ""
            if "vndnbr" in resultado.df.columns and resultado.df["vndnbr"].notna().any():
                proveedor = clean_code(resultado.df["vndnbr"].dropna().iloc[0])
            if "vndname" in resultado.df.columns and resultado.df["vndname"].notna().any():
                nombre = str(resultado.df["vndname"].dropna().iloc[0]).strip()
            registrar_metricas(
                fila_desde_resultado(
                    resultado, proveedor=proveedor, nombre=nombre, rfc=rfc,
                    origen="cruce manual (GUI)",
                ),
                log=self._log,
            )

            salida = self._ruta_salida(f"{entrada.stem}_EDI.xlsx")
            resultado.df.to_excel(salida, index=False)
            self._fijar_compras(str(salida))
            self._log(f"Salida: {salida}")

        self._ejecutar("cruce", "Cruzando CPA Vision...", tarea)

    # -- Infraestructura ----------------------------------------------------

    def _en_ui(self, funcion, *args) -> None:
        """Encola `funcion` para que la ejecute el hilo de la interfaz.

        Tkinter exige que TODO lo que toca la ventana ocurra en el hilo principal, y las
        tareas largas corren en un hilo aparte (`_ejecutar`). Un `StringVar.set()` no es
        una asignacion inocente: dispara la actualizacion del widget que lo muestra, o sea
        llamadas al interprete Tcl desde el hilo equivocado. El sintoma es un congelamiento
        o un `RuntimeError: main thread is not in main loop` intermitente e irreproducible.

        OJO: `self.after(...)` NO sirve para esto. `after` es a su vez una llamada a Tk
        (registra un comando en el interprete), asi que invocarla desde el hilo de fondo es
        exactamente el problema que se queria evitar; solo parece funcionar mientras el
        mainloop este corriendo. La unica via segura es una cola: `queue.Queue` si es
        thread-safe, y `_procesar_mensajes` —que ya corre en el hilo principal para la
        bitacora— la vacia. Ese es el mismo patron que usa el log desde el primer dia.
        """
        self.acciones.put((funcion, args))

    def _fijar(self, variable: ctk.StringVar, valor: str) -> None:
        """`variable.set(valor)` seguro desde un hilo de fondo."""
        self._en_ui(variable.set, valor)

    def _fijar_compras(self, ruta: str) -> None:
        """Registra un Compras nuevo y DESCARTA el recalculado anterior.

        Un Compras nuevo invalida cualquier recalculado previo: son de otro proveedor o de
        otra corrida. Si no se limpiara, `_validar` —que prefiere el recalculado— generaria
        la Validacion del proveedor ANTERIOR sin avisar. La unica pista seria el nombre del
        archivo de salida, y eso es un entregable incorrecto sostenido por que alguien se
        fije. Ver la etiqueta bajo el boton de Validacion, que muestra el archivo elegido.
        """
        self._fijar(self.archivo_editado, ruta)
        self._fijar(self.archivo_recalculado, "")
        self._fijar(self.archivo_validacion, "")

    def _archivo_para_validar(self) -> str:
        """El Compras que usaria 'Generar Validación': el recalculado si existe."""
        return self.archivo_recalculado.get().strip() or self.archivo_editado.get().strip()

    def _refrescar_aviso_validacion(self, *_) -> None:
        """Mantiene visible QUE archivo se validaria, para verlo antes de hacer clic."""
        etiqueta = self._widget("aviso_validacion")
        if etiqueta is None:
            return
        ruta = self._archivo_para_validar()
        if not ruta:
            etiqueta.configure(
                text="  Validará: (ningún archivo — se te pedirá al hacer clic)",
                text_color=self.tema("t2"),
            )
            return
        origen = "recalculado" if self.archivo_recalculado.get().strip() else "sin recalcular"
        etiqueta.configure(
            text=f"  Validará: {Path(ruta).name}  ·  {origen}",
            text_color=self.tema("t1"),
        )

    def _pedir_archivo(self, variable: ctk.StringVar) -> Path | None:
        ruta = variable.get().strip()
        if not ruta:
            self._elegir_excel(variable)
            ruta = variable.get().strip()
        return Path(ruta) if ruta else None

    def _ruta_salida(self, nombre: str) -> Path:
        carpeta = Path(self.carpeta_salida.get().strip() or config.OUTPUT_DIR)
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta / nombre

    def _detener(self) -> None:
        """Pide detener la operación en curso (cancelación cooperativa).

        No se mata el hilo: eso dejaría Excel a medio escribir y navegadores huérfanos. Se
        levanta la señal y el trabajo para en su siguiente punto seguro. En la descarga de
        CPA ese punto es entre dos sondeos del portal, así que responde en segundos; en un
        paso que ya está escribiendo un archivo, termina ese paso antes de parar.
        """
        if not self._ocupado:
            return
        self._cancelacion.set()
        self.estado.boton_detener.configure(state="disabled")
        self._log("Deteniendo... se cancelará en el siguiente punto seguro.")

    def _ejecutar(self, clave: str, mensaje: str, tarea) -> None:
        if self._ocupado:
            self._log("Hay una operación en curso; espera a que termine.")
            return
        self._ocupado = True
        self._cancelacion.clear()
        self._corriendo = clave
        self.estado.iniciar(mensaje)
        self._refrescar_pasos()
        self._log(mensaje)

        # `envoltura` corre en otro hilo: nada de lo que hay aqui puede tocar Tk
        # directamente. El log va por su cola y la barra de estado por `_en_ui`.
        def envoltura() -> None:
            try:
                tarea()
                self._en_ui(self._terminado, "ok", "Listo")
            except CancelacionSolicitada:
                # Parada pedida por el usuario: no es un fallo, se distingue en la bitácora.
                self._log("Operación detenida por el usuario.")
                self._en_ui(self._terminado, "cancelado", "Detenido por el usuario")
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._en_ui(self._terminado, "error", str(exc).splitlines()[0][:70])
            finally:
                self._ocupado = False

        threading.Thread(target=envoltura, daemon=True).start()

    def _terminado(self, resultado: str, texto: str) -> None:
        """Cierra la operación en la barra de estado. Solo desde el hilo de la interfaz."""
        self._corriendo = None
        if resultado == "cancelado":
            self.estado.reposo(texto)
        else:
            self.estado.terminar(resultado == "ok", texto)
        # Una descarga acaba de crear particiones nuevas: lo memorizado sobre el Parquet ya
        # no vale. Se tira entero —son un puñado de entradas— en vez de adivinar cuál caducó.
        self._cache_parquet.clear()
        # El paso que corría vuelve a su estado real: quizá quedó "hecho", quizá no.
        self._refrescar_pasos()


def _estado_visible(trabajo: cola_descarga.Trabajo) -> tuple[str, str]:
    """`(etiqueta de color, texto)` para la celda Estado de un renglón de la cola.

    Un trabajo puede tener DOS fases y la celda es una sola, así que se muestra la que
    manda: la primera que aún no termina, o la última si ya terminaron todas. Es lo que
    contesta "¿en qué va esto?" sin obligar a leer dos columnas.
    """
    fases = []
    if trabajo.plan.descarga:
        fases.append(("⬇", trabajo.estado, trabajo.segundos, trabajo.detalle))
    if trabajo.plan.genera:
        fases.append(("⚙", trabajo.estado_salida, trabajo.segundos_salida, trabajo.detalle_salida))

    icono, estado, segundos, detalle = next(
        (f for f in fases if f[1] not in cola_descarga.TERMINADOS), fases[-1]
    )
    color, texto = _ESTADO_COLA.get(estado, ("pendiente", "en espera"))
    texto = f"{icono}  {texto}"
    if segundos:
        texto += f"  ·  {segundos / 60:.1f} min"
    if detalle:
        texto += f"  ·  {detalle[:40]}"
    return color, texto


def run_app() -> None:
    CostosApp().mainloop()


def _nombre_compras(df, proveedor: str) -> str:
    codigo = clean_code(proveedor)
    nombre = ""
    if not df.empty:
        if not codigo and "vndnbr" in df.columns and df["vndnbr"].notna().any():
            codigo = clean_code(df["vndnbr"].dropna().iloc[0])
        if "vndname" in df.columns and df["vndname"].notna().any():
            nombre = str(df["vndname"].dropna().iloc[0]).strip()
    return f"{safe_filename(f'Compras_{codigo}_{nombre}'.strip('_')).rstrip(' .')}.xlsx"
