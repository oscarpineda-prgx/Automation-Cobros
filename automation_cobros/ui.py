"""Tema visual y widgets de la interfaz — PRGX Soriana Audit Suite.

Replica el lenguaje visual de Conciliacion_Memo_Panoptic para que las herramientas de
la suite se vean como una sola familia: paleta PRGX, tarjetas con franja de acento,
indicadores de estado y bitacora con colores.

Aqui solo vive la presentacion. La logica de negocio esta en `app.py` y en los modulos
del paquete.
"""

from __future__ import annotations

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


class Indicadores:
    """Puntos de estado y barras de progreso, indexados por clave de accion."""

    ESTADOS = ("idle", "running", "ok", "error")

    def __init__(self, root: ctk.CTk, tema: Tema) -> None:
        self.root = root
        self.tema = tema
        self.puntos: dict[str, ctk.CTkLabel] = {}
        self.barras: dict[str, ctk.CTkProgressBar] = {}
        self._parpadeos: dict[str, str] = {}

    def registrar(self, clave: str, punto: ctk.CTkLabel, barra: ctk.CTkProgressBar) -> None:
        self.puntos[clave] = punto
        self.barras[clave] = barra

    def limpiar(self) -> None:
        for clave in list(self._parpadeos):
            self._detener_parpadeo(clave)
        self.puntos.clear()
        self.barras.clear()

    def estado(self, clave: str, estado: str) -> None:
        """Actualiza punto y barra. Seguro de llamar desde otro hilo."""
        self.root.after(0, lambda: self._aplicar(clave, estado))

    def _aplicar(self, clave: str, estado: str) -> None:
        color = {
            "idle": self.tema("s_idle"),
            "running": self.tema("s_run"),
            "ok": self.tema("s_ok"),
            "error": self.tema("s_err"),
        }.get(estado, self.tema("s_idle"))

        if clave in self.puntos:
            self.puntos[clave].configure(text_color=color)
        if clave not in self.barras:
            return

        barra = self.barras[clave]
        if estado == "running":
            barra.configure(mode="indeterminate", progress_color=color)
            barra.start()
            self._iniciar_parpadeo(clave)
            return

        barra.stop()
        barra.configure(mode="determinate", progress_color=color)
        barra.set(0.0 if estado == "idle" else 1.0)
        self._detener_parpadeo(clave)

    def _iniciar_parpadeo(self, clave: str) -> None:
        self._detener_parpadeo(clave)
        self._parpadear(clave, encendido=True)

    def _detener_parpadeo(self, clave: str) -> None:
        tarea = self._parpadeos.pop(clave, None)
        if tarea:
            try:
                self.root.after_cancel(tarea)
            except Exception:
                pass

    def _parpadear(self, clave: str, encendido: bool) -> None:
        if clave not in self.puntos:
            return
        color = self.tema("s_run") if encendido else self.tema("s_idle")
        self.puntos[clave].configure(text_color=color)
        self._parpadeos[clave] = self.root.after(
            500, lambda: self._parpadear(clave, not encendido)
        )


# --- Fabricas de widgets ---------------------------------------------------


def tarjeta(parent: ctk.CTkBaseClass, tema: Tema, *, col: int, row: int = 0) -> ctk.CTkFrame:
    izq, der = (16, 8) if col == 0 else (8, 16)
    marco = ctk.CTkFrame(
        parent,
        fg_color=tema("card"),
        corner_radius=12,
        border_width=1,
        border_color=tema("border"),
    )
    marco.grid(
        row=row,
        column=col,
        sticky="nsew",
        padx=(izq, der),
        pady=(14 if row == 0 else 6, 14),
    )
    return marco


def titulo_seccion(
    parent: ctk.CTkFrame, tema: Tema, *, titulo: str, subtitulo: str, insignia: str
) -> None:
    ctk.CTkFrame(parent, fg_color=tema("accent"), height=3, corner_radius=0).pack(fill="x")

    bloque = ctk.CTkFrame(parent, fg_color="transparent")
    bloque.pack(fill="x", padx=18, pady=(12, 6))

    fila = ctk.CTkFrame(bloque, fg_color="transparent")
    fila.pack(fill="x")
    ctk.CTkLabel(
        fila,
        text=insignia,
        font=ctk.CTkFont(FUENTE, 10, weight="bold"),
        text_color="#FFFFFF",
        fg_color=tema("accent"),
        width=26,
        height=20,
        corner_radius=6,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkLabel(
        fila,
        text=titulo,
        font=ctk.CTkFont(FUENTE, 14, weight="bold"),
        text_color=tema("t1"),
    ).pack(side="left", anchor="w")

    ctk.CTkLabel(
        bloque,
        text=subtitulo,
        font=ctk.CTkFont(FUENTE, 11),
        text_color=tema("t2"),
    ).pack(anchor="w", pady=(3, 0))


def _boton_con_indicador(
    parent: ctk.CTkFrame,
    tema: Tema,
    indicadores: Indicadores,
    *,
    texto: str,
    clave: str,
    comando: Callable[[], None],
    principal: bool,
) -> None:
    contenedor = ctk.CTkFrame(parent, fg_color="transparent")
    contenedor.pack(fill="x", padx=14, pady=(8, 2) if principal else 2)

    fila = ctk.CTkFrame(contenedor, fg_color="transparent")
    fila.pack(fill="x")
    punto = ctk.CTkLabel(
        fila,
        text="●",
        text_color=tema("s_idle"),
        font=ctk.CTkFont(FUENTE, 8 if principal else 7),
        width=12,
    )
    punto.pack(side="left", padx=(0, 5))

    ctk.CTkButton(
        fila,
        text=texto,
        font=ctk.CTkFont(FUENTE, 12, weight="bold" if principal else "normal"),
        fg_color=tema("accent") if principal else tema("blue"),
        hover_color=tema("cta_h") if principal else tema("btn_h"),
        text_color="#FFFFFF",
        height=38 if principal else 34,
        corner_radius=8 if principal else 7,
        anchor="center" if principal else "w",
        command=comando,
    ).pack(fill="x")

    barra = ctk.CTkProgressBar(
        contenedor,
        height=3 if principal else 2,
        corner_radius=2 if principal else 1,
        fg_color=tema("pbar_bg"),
        progress_color=tema("s_idle"),
        indeterminate_speed=2.0 if principal else 2.5,
    )
    barra.set(0)
    barra.pack(fill="x", padx=18, pady=(2, 0) if principal else (1, 0))

    indicadores.registrar(clave, punto, barra)


def boton_principal(
    parent: ctk.CTkFrame,
    tema: Tema,
    indicadores: Indicadores,
    *,
    texto: str,
    clave: str,
    comando: Callable[[], None],
) -> None:
    _boton_con_indicador(
        parent, tema, indicadores, texto=texto, clave=clave, comando=comando, principal=True
    )


def boton_paso(
    parent: ctk.CTkFrame,
    tema: Tema,
    indicadores: Indicadores,
    *,
    texto: str,
    clave: str,
    comando: Callable[[], None],
) -> None:
    _boton_con_indicador(
        parent, tema, indicadores, texto=texto, clave=clave, comando=comando, principal=False
    )


def separador(parent: ctk.CTkFrame, tema: Tema) -> None:
    ctk.CTkFrame(parent, fg_color=tema("sep"), height=1, corner_radius=0).pack(
        fill="x", padx=14, pady=8
    )


def pista(parent: ctk.CTkFrame, tema: Tema, texto: str) -> None:
    ctk.CTkLabel(
        parent,
        text=f"  {texto}",
        font=ctk.CTkFont(FUENTE, 10),
        text_color=tema("t2"),
    ).pack(anchor="w", padx=14, pady=(2, 1))


def campo(
    parent: ctk.CTkFrame,
    tema: Tema,
    *,
    etiqueta: str,
    variable: ctk.StringVar,
    ancho: int = 130,
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
    )
    entrada.pack(side="left", pady=12)
    return entrada


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
