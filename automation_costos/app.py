"""GUI de Automation Costos — PRGX Soriana Audit Suite.

Dos etapas:

- **Etapa 1** — pipeline SQL Server → Excel: generar Compras, recalcular el editado por
  el auditor y producir la Validacion de Condiciones.
- **Etapa 2** — CPA Vision: llena las columnas EDI de Compras con los CFDI del dataset
  Parquet. Ver `docs/CRUCE_IMPLEMENTACION.md`.

La presentacion (paleta, tarjetas, indicadores) vive en `ui.py`.
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
from automation_costos import ui
from automation_costos.database import fetch_compras, resolver_rfc, test_connection
from automation_costos.excel_exporter import write_compras_workbook
from automation_costos.recalculate import recalculate_compras_file
from automation_costos.utils import clean_code, safe_filename
from automation_costos.validation_exporter import write_validation_workbook

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
        self.indicadores = ui.Indicadores(self, self.tema)
        self._ocupado = False

        hoy = date.today()
        self.proveedor = ctk.StringVar(value="")
        self.fecha_inicial = ctk.StringVar(value=f"{hoy.year - 6}-01-01")
        self.fecha_final = ctk.StringVar(value=f"{hoy.year - 1}-01-01")
        self.carpeta_salida = ctk.StringVar(value=str(config.OUTPUT_DIR))
        self.archivo_editado = ctk.StringVar(value="")
        self.archivo_recalculado = ctk.StringVar(value="")
        self.rfc = ctk.StringVar(value="")
        self.carpeta_parquet = ctk.StringVar(value=str(config.OUTPUT_DIR / "cpa_vision" / "parquet"))
        self.cpa_usuario = ctk.StringVar(value=config.CPA_VISION_USER)
        self.cpa_password = ctk.StringVar(value=config.CPA_VISION_PASSWORD)

        ctk.set_appearance_mode(self.tema.modo)
        ctk.set_default_color_theme("dark-blue")
        self._configurar_ventana()
        self._construir()
        self._procesar_mensajes()
        self._log("Listo. Etapa 1: generar Compras, editar en Excel, recalcular y validar.")

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
        self.grid_rowconfigure(2, weight=5)  # tarjetas
        self.grid_rowconfigure(3, weight=2)  # bitacora
        self.grid_columnconfigure(0, weight=1)
        self._encabezado()
        self._barra_configuracion()
        self._area_principal()
        self._area_bitacora()

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

        ctk.CTkFrame(hdr, fg_color=self.tema("border"), width=1, height=34).grid(
            row=1, column=3, padx=8, pady=10
        )

        ctk.CTkButton(
            hdr,
            text=self.tema.etiqueta_boton,
            width=96,
            height=30,
            font=ctk.CTkFont(ui.FUENTE, 11),
            fg_color=self.tema("card"),
            hover_color=self.tema("card2"),
            text_color=self.tema("t2"),
            corner_radius=15,
            border_width=1,
            border_color=self.tema("border"),
            command=self._alternar_tema,
        ).grid(row=1, column=4, padx=(0, 18), pady=10)

    def _barra_configuracion(self) -> None:
        barra = ctk.CTkFrame(self, fg_color=self.tema("card"), corner_radius=0, height=54)
        barra.grid(row=1, column=0, sticky="ew")
        barra.grid_propagate(False)

        ui.campo(barra, self.tema, etiqueta="Proveedor", variable=self.proveedor, ancho=110)
        ui.campo(barra, self.tema, etiqueta="Desde", variable=self.fecha_inicial, ancho=110)
        ui.campo(barra, self.tema, etiqueta="Hasta", variable=self.fecha_final, ancho=110)
        ui.campo(barra, self.tema, etiqueta="Salida", variable=self.carpeta_salida, ancho=300)
        ui.boton_secundario(barra, self.tema, texto="Elegir", comando=self._elegir_salida)
        ui.boton_secundario(barra, self.tema, texto="↺  Limpiar", comando=self._limpiar_campos)

    # -- Tarjetas -----------------------------------------------------------

    def _area_principal(self) -> None:
        area = ctk.CTkScrollableFrame(self, fg_color=self.tema("bg1"), corner_radius=0)
        area.grid(row=2, column=0, sticky="nsew", pady=(2, 0))
        area.grid_columnconfigure((0, 1), weight=1, uniform="col")
        self._tarjeta_compras(area)
        self._tarjeta_cpa(area)

    def _tarjeta_compras(self, parent: ctk.CTkFrame) -> None:
        card = ui.tarjeta(parent, self.tema, col=0)
        ui.titulo_seccion(
            card,
            self.tema,
            titulo="ETAPA 1",
            subtitulo="Pipeline de Compras · SQL Server → Excel",
            insignia="01",
        )
        ui.boton_principal(
            card, self.tema, self.indicadores,
            texto="▶  Generar Compras preliminar", clave="extraer",
            comando=self._extraer_compras,
        )
        ui.separador(card, self.tema)
        ui.pista(card, self.tema, "El auditor edita el archivo en Excel antes de continuar")
        ui.boton_paso(
            card, self.tema, self.indicadores,
            texto="  ⟳  Recalcular Compras editado", clave="recalcular",
            comando=self._recalcular,
        )
        ui.boton_paso(
            card, self.tema, self.indicadores,
            texto="  ✦  Generar Validación de Condiciones", clave="validar",
            comando=self._validar,
        )
        ui.separador(card, self.tema)
        ui.boton_paso(
            card, self.tema, self.indicadores,
            texto="  ⚡  Probar conexión a SQL Server", clave="conexion",
            comando=self._probar_conexion,
        )
        self._selector(card, "Compras editado", self.archivo_editado)
        self._selector(card, "Compras recalculado", self.archivo_recalculado)

    def _tarjeta_cpa(self, parent: ctk.CTkFrame) -> None:
        card = ui.tarjeta(parent, self.tema, col=1)
        ui.titulo_seccion(
            card,
            self.tema,
            titulo="ETAPA 2",
            subtitulo="CPA Vision · Descarga de CFDI y salida final",
            insignia="02",
        )

        # Credenciales del portal: las teclea el auditor, nunca se guardan en código.
        fila_user = ctk.CTkFrame(card, fg_color="transparent")
        fila_user.pack(fill="x", padx=14)
        ui.campo(fila_user, self.tema, etiqueta="Usuario CPA", variable=self.cpa_usuario, ancho=230)
        fila_pass = ctk.CTkFrame(card, fg_color="transparent")
        fila_pass.pack(fill="x", padx=14)
        ui.campo(
            fila_pass, self.tema, etiqueta="Contraseña", variable=self.cpa_password,
            ancho=230, show="*",
        )

        ui.boton_principal(
            card, self.tema, self.indicadores,
            texto="⬇  Descargar de CPA Vision", clave="descarga",
            comando=self._descargar_cpa,
        )
        ui.pista(card, self.tema, "Trae los CFDI del portal y arma el Parquet (RFC automático)")
        ui.separador(card, self.tema)

        ui.boton_principal(
            card, self.tema, self.indicadores,
            texto="▶  Generar salida completa (1 clic)", clave="salida",
            comando=self._generar_salida,
        )
        ui.pista(card, self.tema, "Compras → cruce → recálculo → Validación, de corrido")
        ui.separador(card, self.tema)
        ui.boton_paso(
            card, self.tema, self.indicadores,
            texto="  ⇄  Solo rellenar EDI (sobre un Compras)", clave="cruce",
            comando=self._cruzar_cpa,
        )
        ui.pista(card, self.tema, "El RFC se detecta solo del Compras; solo llénalo para forzar otro")

        fila_rfc = ctk.CTkFrame(card, fg_color="transparent")
        fila_rfc.pack(fill="x", padx=14)
        ui.campo(fila_rfc, self.tema, etiqueta="RFC (opcional)", variable=self.rfc, ancho=180)

        fila_pq = ctk.CTkFrame(card, fg_color="transparent")
        fila_pq.pack(fill="x", padx=14)
        ui.campo(fila_pq, self.tema, etiqueta="Parquet", variable=self.carpeta_parquet, ancho=250)
        ui.boton_secundario(fila_pq, self.tema, texto="Elegir", comando=self._elegir_parquet)

    def _selector(self, parent: ctk.CTkFrame, etiqueta: str, variable: ctk.StringVar) -> None:
        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.pack(fill="x", padx=14)
        ui.campo(fila, self.tema, etiqueta=etiqueta, variable=variable, ancho=250)
        ui.boton_secundario(
            fila, self.tema, texto="Elegir", comando=lambda: self._elegir_excel(variable)
        )

    # -- Bitacora -----------------------------------------------------------

    def _area_bitacora(self) -> None:
        marco = ctk.CTkFrame(self, fg_color=self.tema("bg2"), corner_radius=0)
        marco.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(1, weight=1)

        cabecera = ctk.CTkFrame(marco, fg_color="transparent")
        cabecera.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 2))
        ctk.CTkLabel(
            cabecera,
            text="BITÁCORA DE EJECUCIÓN",
            font=ctk.CTkFont(ui.FUENTE, 9, weight="bold"),
            text_color=self.tema("t2"),
        ).pack(side="left")
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
        try:
            while True:
                self._escribir(self.mensajes.get_nowait())
        except queue.Empty:
            pass
        self.after(120, self._procesar_mensajes)

    # -- Tema ---------------------------------------------------------------

    def _alternar_tema(self) -> None:
        contenido = self.bitacora.get("1.0", "end-1c")
        self.indicadores.limpiar()
        self.tema.alternar()
        for hijo in self.winfo_children():
            hijo.destroy()
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
        self.indicadores.limpiar_estados()
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
            self.archivo_editado.set(str(salida))
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
            self.archivo_recalculado.set(str(salida))
            self._log(f"Compras recalculado generado: {salida}")

        self._ejecutar("recalcular", "Recalculando archivo de compras...", tarea)

    def _validar(self) -> None:
        ruta = self.archivo_recalculado.get().strip() or self.archivo_editado.get().strip()
        if not ruta:
            self._elegir_excel(self.archivo_recalculado)
            ruta = self.archivo_recalculado.get().strip()
        if not ruta:
            return
        entrada = Path(ruta)

        def tarea() -> None:
            salida = self._ruta_salida(f"{entrada.stem}_Validacion_Condiciones.xlsx")
            write_validation_workbook(entrada, salida)
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
        rfc_forzado = self.rfc.get().strip().upper()

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
                self.rfc.set(rfc)
            self._log(f"RFC del proveedor: {rfc}")

            resultado = descargar_cpa_proveedor(
                rfc, inicio, fin,
                parquet_root=parquet,
                username=usuario,
                password=password,
                log=self._log,
            )
            self.carpeta_parquet.set(str(resultado.parquet_root))
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
            self.archivo_editado.set(str(resultado.compras_path))
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
            salida = self._ruta_salida(f"{entrada.stem}_EDI.xlsx")
            resultado.df.to_excel(salida, index=False)
            self.archivo_editado.set(str(salida))
            self._log(f"Salida: {salida}")

        self._ejecutar("cruce", "Cruzando CPA Vision...", tarea)

    # -- Infraestructura ----------------------------------------------------

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

    def _ejecutar(self, clave: str, mensaje: str, tarea) -> None:
        if self._ocupado:
            self._log("Hay una operación en curso; espera a que termine.")
            return
        self._ocupado = True
        self._log(mensaje)
        self.indicadores.estado(clave, "running")

        def envoltura() -> None:
            try:
                tarea()
                self.indicadores.estado(clave, "ok")
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self.indicadores.estado(clave, "error")
            finally:
                self._ocupado = False

        threading.Thread(target=envoltura, daemon=True).start()


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
