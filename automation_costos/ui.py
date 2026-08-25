"""Tema visual y widgets de la interfaz — PRGX Soriana Audit Suite.

Replica el lenguaje visual de Conciliacion_Memo_Panoptic para que las herramientas de
la suite se vean como una sola familia: paleta PRGX, tarjetas con franja de acento,
barra de estado y bitacora con colores.

Aqui solo vive la presentacion. La logica de negocio esta en `app.py` y en los modulos
del paquete.

Presupuesto de recursos
-----------------------
Esto corre en equipos de **un solo nucleo**. Cada widget de customtkinter con esquinas
redondeadas es un `CTkCanvas`, y cada animacion continua es CPU que no vuelve. Por eso:

- **Una sola barra de estado** (`BarraEstado`) en vez de un indicador por boton.
- **El latido es un reloj de 1 Hz**, no una barra indeterminada a ~50 fps. Contesta
  "¿sigue vivo?" igual de bien por un redibujo de texto.
- **La barra de progreso solo sale cuando hay progreso real** que mostrar (3 de 12
  proveedores), nunca como decoracion.
- Iconos con caracteres, no imagenes.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import customtkinter as ctk

ASSETS = Path(__file__).parent / "assets"
ICONO_PRGX = ASSETS / "prgx-icon.png"
LOGO_SORIANA = ASSETS / "Soriana-Logo.png"

FUENTE = "Segoe UI"

_OSCURO: dict[str, str] = {
    "bg1": "#21212C",
    "bg2": "#191921",
    "card": "#2C2C3A",
    "card2": "#353545",
    "accent": "#611EEC",
    "blue": "#2E7FDB",
    "t1": "#E8EDF2",
    "t2": "#7A8490",
    "border": "#3B2D68",
    "sep": "#323244",
    "pbar_bg": "#21212C",
    "s_idle": "#383855",
    "s_run": "#2E7FDB",
    "s_ok": "#00C820",
    "s_err": "#E63350",
    "btn_h": "#1A5FB4",
    "cta_h": "#4A0FB0",
}

_CLARO: dict[str, str] = {
    "bg1": "#EEF2F7",
    "bg2": "#E0E7F0",
    "card": "#FFFFFF",
    "card2": "#F3F6FA",
    "accent": "#611EEC",
    "blue": "#1A5FB4",
    "t1": "#1C1C2E",
    "t2": "#6B7280",
    "border": "#C5BCE0",
    "sep": "#DDE2EA",
    "pbar_bg": "#E0E7F0",
    "s_idle": "#C8D0DA",
    "s_run": "#1A5FB4",
    "s_ok": "#008C1A",
    "s_err": "#DC2626",
    "btn_h": "#0D4A8A",
    "cta_h": "#4A0FB0",
}

PALETAS = {"light": _CLARO, "dark": _OSCURO}


class Tema:
    """Paleta activa. `alternar()` cambia entre claro y oscuro."""

    def __init__(self, modo: str = "light") -> None:
        self.modo = modo

    @property
    def paleta(self) -> dict[str, str]:
        return PALETAS[self.modo]

    def __call__(self, clave: str) -> str:
        return self.paleta[clave]

    def alternar(self) -> str:
        self.modo = "dark" if self.modo == "light" else "light"
        ctk.set_appearance_mode(self.modo)
        return self.modo

    @property
    def etiqueta_boton(self) -> str:
        """Texto del boton: describe el modo al que se cambiaria."""
        return "🌙  Oscuro" if self.modo == "light" else "☀  Claro"


class BarraEstado:
    """La UNICA barra de estado: que corre, desde cuando, cuanto lleva y como pararlo.

    Antes cada boton llevaba su punto y su barra de progreso: ocho barras animables para una
    aplicacion que solo hace una cosa a la vez. Ademas de sobrar siete, la barra
    indeterminada de customtkinter se redibuja de continuo — y estos equipos tienen un solo
    nucleo.

    Aqui hay una sola linea, y **el latido es el reloj**: avanza una vez por segundo, y eso
    contesta "¿sigue vivo?" igual de bien que una animacion por un redibujo de texto. La
    barra de progreso solo aparece cuando hay algo REAL que medir.

    Todos sus metodos **deben llamarse desde el hilo de la interfaz**. Quien orqueste los
    hilos es el que encola (ver `CostosApp._en_ui`); aqui solo vive la presentacion.
    """

    def __init__(self, parent: ctk.CTkBaseClass, tema: Tema, *, al_detener: Callable[[], None]):
        self.tema = tema
        self._tic: str | None = None
        self._t0 = 0.0
        self._encendido = True

        marco = ctk.CTkFrame(parent, fg_color=tema("card"), corner_radius=0, height=52)
        marco.pack(fill="x")
        marco.pack_propagate(False)
        self.marco = marco

        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(fill="x", padx=16, pady=(9, 0))

        self._punto = ctk.CTkLabel(
            fila, text="●", text_color=tema("s_idle"), font=ctk.CTkFont(FUENTE, 11), width=14
        )
        self._punto.pack(side="left", padx=(0, 7))
        self._texto = ctk.CTkLabel(
            fila, text="Listo", font=ctk.CTkFont(FUENTE, 12), text_color=tema("t1"), anchor="w"
        )
        self._texto.pack(side="left", fill="x", expand=True)

        self.boton_detener = ctk.CTkButton(
            fila, text="■  Detener", width=92, height=28,
            font=ctk.CTkFont(FUENTE, 11, weight="bold"),
            fg_color=tema("s_err"), hover_color=tema("s_err"), text_color="#FFFFFF",
            corner_radius=6, command=al_detener, state="disabled",
        )
        self.boton_detener.pack(side="right", padx=(10, 0))
        self._reloj = ctk.CTkLabel(
            fila, text="", font=ctk.CTkFont("Consolas", 11), text_color=tema("t2")
        )
        self._reloj.pack(side="right")

        # Nace en 0 y sin color: una barra vacia no distrae, y asi no hay que crearla y
        # destruirla cada vez que arranca algo.
        self._barra = ctk.CTkProgressBar(
            marco, height=3, corner_radius=0, fg_color=tema("pbar_bg"),
            progress_color=tema("accent"),
        )
        self._barra.set(0)
        self._barra.pack(fill="x", padx=16, pady=(6, 0))

    # -- ciclo de vida de una operacion ------------------------------------
    def iniciar(self, texto: str) -> None:
        self._t0 = time.monotonic()
        self._texto.configure(text=texto, text_color=self.tema("t1"))
        self._punto.configure(text_color=self.tema("s_run"))
        self.boton_detener.configure(state="normal")
        self._barra.configure(progress_color=self.tema("accent"))
        self._barra.set(0)
        self._latir()

    def progreso(self, hecho: int, total: int) -> None:
        """Avance real: llena la barra y lo dice en el texto. Ignora un total absurdo."""
        if total <= 0:
            return
        self._barra.set(min(max(hecho / total, 0.0), 1.0))

    def terminar(self, ok: bool, texto: str) -> None:
        self._parar_latido()
        color = self.tema("s_ok") if ok else self.tema("s_err")
        self._punto.configure(text_color=color)
        self._texto.configure(text=texto, text_color=self.tema("t1"))
        self._reloj.configure(text=self._transcurrido())
        self.boton_detener.configure(state="disabled")
        self._barra.configure(progress_color=color)
        self._barra.set(1.0 if ok else 0.0)

    def reposo(self, texto: str = "Listo") -> None:
        self._parar_latido()
        self._punto.configure(text_color=self.tema("s_idle"))
        self._texto.configure(text=texto, text_color=self.tema("t2"))
        self._reloj.configure(text="")
        self.boton_detener.configure(state="disabled")
        self._barra.set(0)

    def texto(self, texto: str) -> None:
        """Cambia la descripcion sin tocar el reloj: sirve para las fases de una tanda."""
        self._texto.configure(text=texto)

    # -- latido -------------------------------------------------------------
    def _latir(self) -> None:
        self._reloj.configure(text=self._transcurrido())
        self._encendido = not self._encendido
        self._punto.configure(
            text_color=self.tema("s_run") if self._encendido else self.tema("s_idle")
        )
        self._tic = self.marco.after(1000, self._latir)

    def _parar_latido(self) -> None:
        if self._tic:
            try:
                self.marco.after_cancel(self._tic)
            except Exception:
                pass
            self._tic = None

    def _transcurrido(self) -> str:
        seg = int(time.monotonic() - self._t0)
        return f"{seg // 60:02d}:{seg % 60:02d}" if seg < 3600 else f"{seg // 3600}h {seg % 3600 // 60:02d}m"


#: Como se pinta cada estado de un `Paso`: (icono, color de texto, color de fondo).
ESTADOS_PASO = {
    "hecho": ("✓", "s_ok", "card2"),
    "corriendo": ("⏳", None, "blue"),
    "siguiente": ("▶", None, "accent"),
    "pendiente": ("·", "t2", "card2"),
}


class Paso:
    """Un renglon de la lista de pasos: es a la vez el boton y el indicador de avance.

    Es el corazon de la vista de un proveedor. Una botonera no contesta "¿y ahora que?";
    una lista numerada donde cada renglon dice si ya se hizo, si es el siguiente o si
    todavia no toca, si. Por eso el estado NO sale de la ultima corrida sino de lo que hay
    en disco: reabrir la aplicacion a media faena muestra el mismo mapa.
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        tema: Tema,
        *,
        numero: int,
        titulo: str,
        comando: Callable[[], None],
    ) -> None:
        self.tema = tema
        self.numero = numero
        self.titulo = titulo

        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.pack(fill="x", padx=16, pady=2)
        self.detalle = ctk.CTkLabel(
            fila, text="", font=ctk.CTkFont(FUENTE, 10), text_color=tema("t2"),
            anchor="e", width=210,
        )
        self.detalle.pack(side="right", padx=(10, 0))
        self.boton = ctk.CTkButton(
            fila, text="", height=32, corner_radius=7, anchor="w",
            font=ctk.CTkFont(FUENTE, 12), command=comando,
        )
        self.boton.pack(side="left", fill="x", expand=True)
        self.estado("pendiente")

    def estado(self, nombre: str, detalle: str = "") -> None:
        icono, color_texto, fondo = ESTADOS_PASO.get(nombre, ESTADOS_PASO["pendiente"])
        self.boton.configure(
            text=f"{icono}   {self.numero}   {self.titulo}",
            fg_color=self.tema(fondo),
            hover_color=self.tema("card" if fondo == "card2" else "cta_h"),
            text_color="#FFFFFF" if color_texto is None else self.tema(color_texto),
        )
        self.detalle.configure(text=detalle)


# --- Fabricas de widgets ---------------------------------------------------


class Pestanas:
    """Navegacion entre vistas.

    Se arma con botones normales y NO con `CTkSegmentedButton`, que tiene un unico
    `text_color` para todos sus segmentos: la pestaña activa necesita texto blanco sobre el
    acento, y las inactivas texto oscuro sobre gris claro. Con un solo color, en modo claro
    las inactivas quedaban en blanco sobre `#F3F6FA` — invisibles. Lo reporto Oscar al
    abrirla. Aqui cada boton lleva su propio par de colores, que es el mismo patron que ya
    usa `Paso`.
    """

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        tema: Tema,
        *,
        variable: ctk.StringVar,
        valores: list[str],
        al_cambiar: Callable[[str], None],
    ) -> None:
        self.tema = tema
        self.variable = variable
        self.al_cambiar = al_cambiar
        self.botones: dict[str, ctk.CTkButton] = {}

        barra = ctk.CTkFrame(parent, fg_color="transparent")
        barra.pack(fill="x", padx=16, pady=(10, 2))
        for valor in valores:
            boton = ctk.CTkButton(
                barra,
                text=valor,
                height=34,
                width=140,
                font=ctk.CTkFont(FUENTE, 12, weight="bold"),
                corner_radius=8,
                border_width=1,
                command=lambda v=valor: self.seleccionar(v),
            )
            boton.pack(side="left", padx=(0, 6))
            self.botones[valor] = boton
        self.pintar()

    def seleccionar(self, nombre: str) -> None:
        self.variable.set(nombre)
        self.pintar()
        self.al_cambiar(nombre)

    def pintar(self) -> None:
        """Deja marcada la pestaña activa. Idempotente: se puede llamar de mas."""
        activo = self.variable.get()
        for nombre, boton in self.botones.items():
            if nombre == activo:
                boton.configure(
                    fg_color=self.tema("accent"), hover_color=self.tema("cta_h"),
                    text_color="#FFFFFF", border_color=self.tema("accent"),
                )
            else:
                boton.configure(
                    fg_color=self.tema("card2"), hover_color=self.tema("card"),
                    text_color=self.tema("t1"), border_color=self.tema("border"),
                )


def boton_cta(
    parent: ctk.CTkFrame,
    tema: Tema,
    *,
    texto: str,
    subtitulo: str = "",
    comando: Callable[[], None],
) -> ctk.CTkButton:
    """La accion principal de una vista: grande, de acento y sin adornos.

    Ya no lleva punto ni barra propios: el avance lo cuenta `BarraEstado`, una sola para
    toda la aplicacion.
    """
    boton = ctk.CTkButton(
        parent,
        text=texto,
        font=ctk.CTkFont(FUENTE, 13, weight="bold"),
        fg_color=tema("accent"),
        hover_color=tema("cta_h"),
        text_color="#FFFFFF",
        height=46,
        corner_radius=9,
        command=comando,
    )
    boton.pack(fill="x", padx=16, pady=(6, 0))
    if subtitulo:
        ctk.CTkLabel(
            parent, text=subtitulo, font=ctk.CTkFont(FUENTE, 10), text_color=tema("t2")
        ).pack(anchor="w", padx=18, pady=(3, 0))
    return boton


def grupo(parent: ctk.CTkFrame, tema: Tema, texto: str) -> None:
    """Encabezado de un grupo de ajustes. Mas ligero que una tarjeta entera."""
    ctk.CTkLabel(
        parent,
        text=texto.upper(),
        font=ctk.CTkFont(FUENTE, 9, weight="bold"),
        text_color=tema("accent"),
    ).pack(anchor="w", padx=16, pady=(14, 2))
    ctk.CTkFrame(parent, fg_color=tema("sep"), height=1, corner_radius=0).pack(
        fill="x", padx=16, pady=(0, 4)
    )


def bloque(parent: ctk.CTkBaseClass, tema: Tema) -> ctk.CTkFrame:
    """Contenedor con el aspecto de tarjeta, apilable con `pack` dentro de una vista."""
    marco = ctk.CTkFrame(
        parent, fg_color=tema("card"), corner_radius=12,
        border_width=1, border_color=tema("border"),
    )
    marco.pack(fill="x", padx=16, pady=(10, 0))
    return marco


def rotulo(parent: ctk.CTkFrame, tema: Tema, *, titulo: str, subtitulo: str = "") -> None:
    """Titulo de un bloque, sin insignia numerada: ya no hay 'etapas' que numerar."""
    ctk.CTkLabel(
        parent, text=titulo, font=ctk.CTkFont(FUENTE, 13, weight="bold"),
        text_color=tema("t1"),
    ).pack(anchor="w", padx=16, pady=(12, 0))
    if subtitulo:
        ctk.CTkLabel(
            parent, text=subtitulo, font=ctk.CTkFont(FUENTE, 10), text_color=tema("t2")
        ).pack(anchor="w", padx=16, pady=(2, 0))


def separador(parent: ctk.CTkFrame, tema: Tema) -> None:
    ctk.CTkFrame(parent, fg_color=tema("sep"), height=1, corner_radius=0).pack(
        fill="x", padx=14, pady=8
    )


def pista(parent: ctk.CTkFrame, tema: Tema, texto: str) -> ctk.CTkLabel:
    """Texto de ayuda, en gris y pequeño. Se devuelve por si hay que actualizarlo."""
    etiqueta = ctk.CTkLabel(
        parent,
        text=f"  {texto}",
        font=ctk.CTkFont(FUENTE, 10),
        text_color=tema("t2"),
    )
    etiqueta.pack(anchor="w", padx=14, pady=(2, 1))
    return etiqueta


def aviso(parent: ctk.CTkFrame, tema: Tema, texto: str = "") -> ctk.CTkLabel:
    """Linea informativa bajo un boton. A diferencia de `pista`, se actualiza en vivo."""
    etiqueta = ctk.CTkLabel(
        parent,
        text=texto,
        font=ctk.CTkFont(FUENTE, 10),
        text_color=tema("t2"),
        anchor="w",
        justify="left",
    )
    etiqueta.pack(anchor="w", fill="x", padx=14, pady=(1, 2))
    return etiqueta


def campo(
    parent: ctk.CTkFrame,
    tema: Tema,
    *,
    etiqueta: str,
    variable: ctk.StringVar,
    ancho: int = 130,
    show: str | None = None,
) -> ctk.CTkEntry:
    ctk.CTkLabel(
        parent,
        text=etiqueta,
        font=ctk.CTkFont(FUENTE, 11),
        text_color=tema("t2"),
    ).pack(side="left", padx=(10, 4), pady=12)
    entrada = ctk.CTkEntry(
        parent,
        textvariable=variable,
        width=ancho,
        height=30,
        font=ctk.CTkFont(FUENTE, 11),
        fg_color=tema("card2"),
        border_color=tema("border"),
        text_color=tema("t1"),
        corner_radius=6,
        show=show or "",
    )
    entrada.pack(side="left", pady=12)
    return entrada


def opciones(
    parent: ctk.CTkFrame,
    tema: Tema,
    *,
    etiqueta: str,
    variable: ctk.StringVar,
    valores: list[str],
    ancho: int = 180,
    al_cambiar: Callable[[str], None] | None = None,
) -> ctk.CTkOptionMenu:
    """Lista desplegable con el lenguaje visual del proyecto.

    Se usa donde el valor es **uno de un conjunto cerrado y corto**: un campo de texto
    invitaria a teclear algo que no existe y el error se descubriria al ejecutar.
    """
    ctk.CTkLabel(
        parent,
        text=etiqueta,
        font=ctk.CTkFont(FUENTE, 11),
        text_color=tema("t2"),
    ).pack(side="left", padx=(10, 4), pady=12)
    menu = ctk.CTkOptionMenu(
        parent,
        variable=variable,
        values=valores,
        command=al_cambiar,
        width=ancho,
        height=30,
        font=ctk.CTkFont(FUENTE, 11),
        dropdown_font=ctk.CTkFont(FUENTE, 11),
        fg_color=tema("card2"),
        button_color=tema("accent"),
        button_hover_color=tema("cta_h"),
        text_color=tema("t1"),
        dropdown_fg_color=tema("card2"),
        dropdown_text_color=tema("t1"),
        dropdown_hover_color=tema("card"),
        corner_radius=6,
    )
    menu.pack(side="left", pady=12)
    return menu


def casilla(
    parent: ctk.CTkFrame, tema: Tema, *, texto: str, variable: ctk.BooleanVar
) -> ctk.CTkCheckBox:
    """Casilla de opción con el lenguaje visual del proyecto."""
    control = ctk.CTkCheckBox(
        parent,
        text=texto,
        variable=variable,
        font=ctk.CTkFont(FUENTE, 11),
        text_color=tema("t2"),
        fg_color=tema("accent"),
        hover_color=tema("cta_h"),
        border_color=tema("border"),
        checkbox_width=18,
        checkbox_height=18,
        corner_radius=4,
    )
    control.pack(side="left", padx=(10, 4), pady=10)
    return control


#: Colores de estado para las filas de `tabla`, por nombre de etiqueta.
ETIQUETAS_TABLA = {
    "ok": "s_ok",
    "error": "s_err",
    "corriendo": "s_run",
    "aviso": "accent",
    "pendiente": "t2",
}


def tabla(
    parent: ctk.CTkFrame,
    tema: Tema,
    *,
    columnas: list[tuple[str, str, int]],
    alto: int = 8,
) -> "ttk.Treeview":
    """Tabla de datos con el lenguaje visual del proyecto.

    customtkinter no trae tabla, asi que se usa `ttk.Treeview` —que si sabe de columnas,
    seleccion multiple y miles de filas— y se le pinta encima la paleta PRGX. `columnas` es
    una lista de `(clave, titulo, ancho)`.

    El estilo se reconfigura en cada llamada a proposito: al alternar el tema, `app.py`
    destruye y reconstruye la ventana, y asi la tabla nace ya con la paleta nueva.
    """
    from tkinter import ttk

    estilo = ttk.Style()
    # `clam` es el unico tema de ttk que respeta los colores de fondo en Windows.
    if "clam" in estilo.theme_names():
        estilo.theme_use("clam")
    estilo.configure(
        "PRGX.Treeview",
        background=tema("card2"),
        fieldbackground=tema("card2"),
        foreground=tema("t1"),
        rowheight=26,
        borderwidth=0,
        font=(FUENTE, 10),
    )
    estilo.configure(
        "PRGX.Treeview.Heading",
        background=tema("card"),
        foreground=tema("t2"),
        relief="flat",
        font=(FUENTE, 10, "bold"),
    )
    estilo.map(
        "PRGX.Treeview",
        background=[("selected", tema("accent"))],
        foreground=[("selected", "#FFFFFF")],
    )
    estilo.map("PRGX.Treeview.Heading", background=[("active", tema("card2"))])

    marco = ctk.CTkFrame(parent, fg_color="transparent")
    marco.pack(fill="both", expand=True, padx=14, pady=(4, 2))

    vista = ttk.Treeview(
        marco,
        columns=[c[0] for c in columnas],
        show="headings",
        height=alto,
        style="PRGX.Treeview",
        selectmode="extended",
    )
    for clave, titulo, ancho in columnas:
        vista.heading(clave, text=titulo, anchor="w")
        vista.column(clave, width=ancho, anchor="w", stretch=(ancho >= 180))

    barra = ttk.Scrollbar(marco, orient="vertical", command=vista.yview)
    vista.configure(yscrollcommand=barra.set)
    vista.pack(side="left", fill="both", expand=True)
    barra.pack(side="right", fill="y")

    for etiqueta, color in ETIQUETAS_TABLA.items():
        vista.tag_configure(etiqueta, foreground=tema(color))
    return vista


def boton_secundario(
    parent: ctk.CTkFrame, tema: Tema, *, texto: str, comando: Callable[[], None], ancho: int = 80
) -> ctk.CTkButton:
    boton = ctk.CTkButton(
        parent,
        text=texto,
        width=ancho,
        height=30,
        font=ctk.CTkFont(FUENTE, 11),
        fg_color=tema("card2"),
        hover_color=tema("card"),
        text_color=tema("t2"),
        corner_radius=6,
        border_width=1,
        border_color=tema("border"),
        command=comando,
    )
    boton.pack(side="left", padx=6, pady=12)
    return boton
