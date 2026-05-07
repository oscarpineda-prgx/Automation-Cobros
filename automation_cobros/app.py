from __future__ import annotations

import queue
import threading
from datetime import date
from pathlib import Path
from tkinter import END, LEFT, RIGHT, W, Button, Entry, Frame, Label, StringVar, Tk, filedialog, messagebox, scrolledtext

import config
from automation_cobros.database import fetch_compras, test_connection
from automation_cobros.excel_exporter import write_compras_workbook
from automation_cobros.recalculate import recalculate_compras_file
from automation_cobros.utils import clean_code, safe_filename
from automation_cobros.validation_exporter import write_validation_workbook


class CobrosApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Automation Cobros - Fase 1")
        self.root.geometry("860x620")
        self.root.minsize(780, 560)
        self.messages: queue.Queue[str] = queue.Queue()

        today = date.today()
        self.vendor = StringVar(value="")
        self.start_date = StringVar(value=f"{today.year - 6}-01-01")
        self.end_date = StringVar(value=f"{today.year - 1}-01-01")
        self.output_dir = StringVar(value=str(config.OUTPUT_DIR))
        self.edited_file = StringVar(value="")
        self.recalculated_file = StringVar(value="")

        self._build_ui()
        self._poll_messages()

    def _build_ui(self) -> None:
        container = Frame(self.root, padx=16, pady=14)
        container.pack(fill="both", expand=True)

        title = Label(container, text="Automation Cobros - Fase 1", font=("Segoe UI", 16, "bold"))
        title.pack(anchor=W, pady=(0, 12))

        form = Frame(container)
        form.pack(fill="x")
        self._field(form, "Proveedor", self.vendor, 0, 0, width=16)
        self._field(form, "Fecha inicial", self.start_date, 0, 2, width=16)
        self._field(form, "Fecha final", self.end_date, 0, 4, width=16)

        out_frame = Frame(container, pady=8)
        out_frame.pack(fill="x")
        Label(out_frame, text="Carpeta salida", width=14, anchor=W).pack(side=LEFT)
        Entry(out_frame, textvariable=self.output_dir).pack(side=LEFT, fill="x", expand=True, padx=(0, 8))
        Button(out_frame, text="Elegir", command=self._choose_output_dir).pack(side=RIGHT)

        actions = Frame(container, pady=8)
        actions.pack(fill="x")
        Button(actions, text="Probar conexion BD", command=self._test_connection).pack(side=LEFT, padx=(0, 8))
        Button(actions, text="1. Generar Compras preliminar", command=self._extract_compras).pack(side=LEFT, padx=(0, 8))
        Button(actions, text="2. Recalcular Compras editado", command=self._recalculate_file).pack(side=LEFT, padx=(0, 8))
        Button(actions, text="3. Generar Validacion", command=self._generate_validation).pack(side=LEFT)

        files = Frame(container, pady=8)
        files.pack(fill="x")
        Label(files, text="Compras editado", width=14, anchor=W).grid(row=0, column=0, sticky=W, pady=3)
        Entry(files, textvariable=self.edited_file).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        Button(files, text="Elegir", command=self._choose_edited_file).grid(row=0, column=2, sticky=W)
        Label(files, text="Compras recalculado", width=14, anchor=W).grid(row=1, column=0, sticky=W, pady=3)
        Entry(files, textvariable=self.recalculated_file).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        Button(files, text="Elegir", command=self._choose_recalculated_file).grid(row=1, column=2, sticky=W)
        files.columnconfigure(1, weight=1)

        Label(container, text="Bitacora", font=("Segoe UI", 10, "bold")).pack(anchor=W, pady=(10, 4))
        self.log = scrolledtext.ScrolledText(container, height=18, wrap="word")
        self.log.pack(fill="both", expand=True)
        self._log("Listo. Flujo recomendado: generar Compras, editar en Excel, recalcular, generar Validacion.")

    def _field(self, parent: Frame, label: str, variable: StringVar, row: int, col: int, width: int) -> None:
        Label(parent, text=label, anchor=W).grid(row=row, column=col, sticky=W, padx=(0, 4))
        Entry(parent, textvariable=variable, width=width).grid(row=row, column=col + 1, sticky=W, padx=(0, 16))

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir.get() or str(config.OUTPUT_DIR))
        if selected:
            self.output_dir.set(selected)

    def _choose_edited_file(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if selected:
            self.edited_file.set(selected)

    def _choose_recalculated_file(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if selected:
            self.recalculated_file.set(selected)

    def _test_connection(self) -> None:
        self._run_background("Probando conexion a SQL Server...", self._test_connection_worker)

    def _test_connection_worker(self) -> None:
        test_connection()
        self._log("Conexion correcta.")

    def _extract_compras(self) -> None:
        vendor = self.vendor.get().strip()
        start = self.start_date.get().strip()
        end = self.end_date.get().strip()
        if not vendor or not start or not end:
            messagebox.showerror("Datos incompletos", "Captura proveedor, fecha inicial y fecha final.")
            return
        self._run_background("Consultando compras en SQL Server...", lambda: self._extract_worker(vendor, start, end))

    def _extract_worker(self, vendor: str, start: str, end: str) -> None:
        df = fetch_compras(vendor, start, end)
        output = self._output_path(_compras_filename(df, vendor))
        write_compras_workbook(df, output, vendor=vendor, start_date=start, end_date=end)
        self.edited_file.set(str(output))
        self._log(f"Compras preliminar generado: {output}")
        self._log(f"Filas extraidas: {len(df):,}")

    def _recalculate_file(self) -> None:
        input_path = self.edited_file.get().strip()
        if not input_path:
            self._choose_edited_file()
            input_path = self.edited_file.get().strip()
        if not input_path:
            return
        self._run_background("Recalculando archivo de compras...", lambda: self._recalculate_worker(Path(input_path)))

    def _recalculate_worker(self, input_path: Path) -> None:
        output = self._output_path(f"{input_path.stem}_Recalculado.xlsx")
        recalculate_compras_file(input_path, output)
        self.recalculated_file.set(str(output))
        self._log(f"Compras recalculado generado: {output}")

    def _generate_validation(self) -> None:
        input_path = self.recalculated_file.get().strip() or self.edited_file.get().strip()
        if not input_path:
            self._choose_recalculated_file()
            input_path = self.recalculated_file.get().strip()
        if not input_path:
            return
        self._run_background("Generando Validacion de Condiciones...", lambda: self._validation_worker(Path(input_path)))

    def _validation_worker(self, input_path: Path) -> None:
        output = self._output_path(f"{input_path.stem}_Validacion_Condiciones.xlsx")
        write_validation_workbook(input_path, output)
        self._log(f"Validacion generada: {output}")

    def _output_path(self, filename: str) -> Path:
        folder = Path(self.output_dir.get().strip() or config.OUTPUT_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / filename

    def _run_background(self, start_message: str, worker) -> None:
        self._log(start_message)

        def target() -> None:
            try:
                worker()
            except Exception as exc:
                self._log(f"ERROR: {exc}")

        threading.Thread(target=target, daemon=True).start()

    def _log(self, message: str) -> None:
        self.messages.put(message)

    def _poll_messages(self) -> None:
        while True:
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                break
            self.log.insert(END, message + "\n")
            self.log.see(END)
        self.root.after(200, self._poll_messages)


def run_app() -> None:
    root = Tk()
    CobrosApp(root)
    root.mainloop()


def _compras_filename(df, vendor: str) -> str:
    vendor_code = clean_code(vendor)
    vendor_name = ""
    if not df.empty:
        if not vendor_code and "vndnbr" in df.columns and df["vndnbr"].notna().any():
            vendor_code = clean_code(df["vndnbr"].dropna().iloc[0])
        if "vndname" in df.columns and df["vndname"].notna().any():
            vendor_name = str(df["vndname"].dropna().iloc[0]).strip()

    filename = safe_filename(f"Compras_{vendor_code}_{vendor_name}".strip("_")).rstrip(" .")
    return f"{filename}.xlsx"
