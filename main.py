from __future__ import annotations

import argparse
from pathlib import Path

from automation_cobros.database import fetch_compras
from automation_cobros.excel_exporter import write_compras_workbook
from automation_cobros.recalculate import recalculate_compras_file
from automation_cobros.validation_exporter import write_validation_workbook


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automation Cobros - fase 1")
    sub = parser.add_subparsers(dest="command")

    extract = sub.add_parser("extract", help="Consulta SQL y genera Compras preliminar")
    extract.add_argument("--vendor", required=True)
    extract.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD")
    extract.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD")
    extract.add_argument("--output", required=True)

    recalc = sub.add_parser("recalc", help="Recalcula un archivo Compras editado")
    recalc.add_argument("--input", required=True)
    recalc.add_argument("--output", required=True)

    validate = sub.add_parser("validate", help="Genera Validacion de Condiciones")
    validate.add_argument("--input", required=True, help="Compras recalculado")
    validate.add_argument("--output", required=True)

    cpa_session = sub.add_parser("cpa-session", help="Abre CPA Vision y captura descargas CSV")
    cpa_session.add_argument("--url", default=None, help="URL de CPA Vision")
    cpa_session.add_argument("--download-dir", default=None, help="Carpeta para guardar descargas")
    cpa_session.add_argument("--state", default=None, help="Archivo para guardar la sesion")
    cpa_session.add_argument("--browser-channel", default=None, help="Canal Playwright: msedge, chrome o chromium")
    cpa_session.add_argument("--headless", action="store_true", help="Ejecuta Chromium sin ventana")
    cpa_session.add_argument("--timeout-ms", type=int, default=None)
    cpa_session.add_argument("--slow-mo-ms", type=int, default=None)

    cpa_csvs = sub.add_parser("cpa-csvs", help="Lista CSV descargados desde CPA Vision")
    cpa_csvs.add_argument("--download-dir", default=None, help="Carpeta de descargas CPA Vision")

    cpa_downloads = sub.add_parser(
        "cpa-downloads-page",
        help="Inicia sesion en CPA Vision y abre Descarga masiva",
    )
    cpa_downloads.add_argument("--url", default=None, help="URL de CPA Vision")
    cpa_downloads.add_argument("--user", default=None, help="Usuario CPA Vision")
    cpa_downloads.add_argument("--rfc", default=None, help="RFC a capturar en recibidos")
    cpa_downloads.add_argument("--start-year", type=int, default=2020)
    cpa_downloads.add_argument("--end-year", type=int, default=2024)
    cpa_downloads.add_argument("--download-dir", default=None, help="Carpeta para guardar descargas")
    cpa_downloads.add_argument("--state", default=None, help="Archivo para guardar la sesion")
    cpa_downloads.add_argument("--browser-channel", default=None, help="Canal Playwright: msedge, chrome o chromium")
    cpa_downloads.add_argument("--headless", action="store_true", help="Ejecuta Chromium sin ventana")
    cpa_downloads.add_argument("--timeout-ms", type=int, default=None)
    cpa_downloads.add_argument("--slow-mo-ms", type=int, default=100)
    cpa_downloads.add_argument(
        "--close",
        action="store_true",
        help="Cierra el navegador al llegar a la pagina de descargas",
    )
    cpa_downloads.add_argument(
        "--skip-config",
        action="store_true",
        help="No marca opciones automaticamente en Descarga masiva",
    )

    cpa_request = sub.add_parser(
        "cpa-request-download",
        help="Solicita descarga en CPA Vision, espera el ZIP y lo descarga",
    )
    cpa_request.add_argument("--url", default=None, help="URL de CPA Vision")
    cpa_request.add_argument("--user", default=None, help="Usuario CPA Vision")
    cpa_request.add_argument("--rfc", default=None, help="RFC a capturar en recibidos")
    cpa_request.add_argument("--start-year", type=int, default=2020)
    cpa_request.add_argument("--end-year", type=int, default=2024)
    cpa_request.add_argument("--download-dir", default=None, help="Carpeta para guardar descargas")
    cpa_request.add_argument("--state", default=None, help="Archivo para guardar la sesion")
    cpa_request.add_argument("--browser-channel", default=None, help="Canal Playwright: msedge, chrome o chromium")
    cpa_request.add_argument("--headless", action="store_true", help="Ejecuta Chromium sin ventana")
    cpa_request.add_argument("--timeout-ms", type=int, default=None)
    cpa_request.add_argument("--slow-mo-ms", type=int, default=100)
    cpa_request.add_argument("--poll-seconds", type=int, default=20)
    cpa_request.add_argument("--max-wait-minutes", type=int, default=420)
    cpa_request.add_argument(
        "--keep-open",
        action="store_true",
        help="Deja el navegador abierto al terminar",
    )

    cpa_wait = sub.add_parser(
        "cpa-wait-download",
        help="Espera y descarga un ZIP de CPA Vision usando un ID existente",
    )
    cpa_wait.add_argument("--request-id", required=True, help="ID de solicitud CPA Vision")
    cpa_wait.add_argument("--url", default=None, help="URL de CPA Vision")
    cpa_wait.add_argument("--user", default=None, help="Usuario CPA Vision")
    cpa_wait.add_argument("--download-dir", default=None, help="Carpeta para guardar descargas")
    cpa_wait.add_argument("--state", default=None, help="Archivo para guardar la sesion")
    cpa_wait.add_argument("--browser-channel", default=None, help="Canal Playwright: msedge, chrome o chromium")
    cpa_wait.add_argument("--headless", action="store_true", help="Ejecuta Chromium sin ventana")
    cpa_wait.add_argument("--timeout-ms", type=int, default=None)
    cpa_wait.add_argument("--slow-mo-ms", type=int, default=100)
    cpa_wait.add_argument("--poll-seconds", type=int, default=20)
    cpa_wait.add_argument("--max-wait-minutes", type=int, default=420)
    cpa_wait.add_argument(
        "--keep-open",
        action="store_true",
        help="Deja el navegador abierto al terminar",
    )

    cpa_batch = sub.add_parser(
        "cpa-batch-vendors",
        help="Procesa proveedores de vendor_master_fechas.xlsx por lotes en CPA Vision",
    )
    cpa_batch.add_argument(
        "--input",
        default="vendor_master_fechas.xlsx",
        help="Excel con columnas RFC y FECHAS",
    )
    cpa_batch.add_argument("--url", default=None, help="URL de CPA Vision")
    cpa_batch.add_argument("--user", default=None, help="Usuario CPA Vision")
    cpa_batch.add_argument("--password", default=None, help="Password CPA Vision")
    cpa_batch.add_argument("--batch-size", type=int, default=50, help="Cantidad de proveedores a procesar")
    cpa_batch.add_argument("--start-index", type=int, default=0, help="Indice base 0 dentro del Excel")
    cpa_batch.add_argument("--download-dir", default=None, help="Carpeta para guardar descargas")
    cpa_batch.add_argument("--parquet-dir", default=None, help="Carpeta raiz para almacenar datasets Parquet")
    cpa_batch.add_argument("--metrics-output", default=None, help="CSV de metricas de salida")
    cpa_batch.add_argument("--state", default=None, help="Archivo para guardar la sesion")
    cpa_batch.add_argument("--browser-channel", default=None, help="Canal Playwright: msedge, chrome o chromium")
    cpa_batch.add_argument("--headless", action="store_true", help="Ejecuta Chromium sin ventana")
    cpa_batch.add_argument("--timeout-ms", type=int, default=None)
    cpa_batch.add_argument("--slow-mo-ms", type=int, default=100)
    cpa_batch.add_argument("--poll-seconds", type=int, default=20)
    cpa_batch.add_argument("--max-wait-minutes", type=int, default=420)
    cpa_batch.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Detiene el lote ante el primer proveedor con error",
    )
    cpa_batch.add_argument(
        "--keep-open",
        action="store_true",
        help="Deja el navegador abierto al terminar",
    )

    cpa_zip_to_parquet = sub.add_parser(
        "cpa-zip-to-parquet",
        help="Convierte ZIP ya descargados de CPA Vision a un dataset Parquet particionado",
    )
    cpa_zip_to_parquet.add_argument("--input", required=True, help="ZIP descargado o carpeta con ZIPs")
    cpa_zip_to_parquet.add_argument("--output", required=True, help="Carpeta raiz para almacenar Parquet")
    cpa_zip_to_parquet.add_argument("--rfc", default=None, help="RFC del proveedor para particionar el dataset")
    cpa_zip_to_parquet.add_argument("--request-id", default=None, help="ID de solicitud para particionar el dataset")

    cpa_consolidate = sub.add_parser(
        "cpa-consolidate",
        help="Consolida CSV de ZIP CPA Vision en un Excel",
    )
    cpa_consolidate.add_argument(
        "--input",
        required=True,
        help="ZIP descargado de CPA Vision o carpeta con ZIPs",
    )
    cpa_consolidate.add_argument("--output", required=True, help="Excel consolidado de salida")

    cpa_cruce = sub.add_parser(
        "cpa-cruce",
        help="Llena las columnas EDI de un Compras con los CFDI de CPA Vision",
    )
    cpa_cruce.add_argument("--compras", required=True, help="Excel de Compras a completar")
    cpa_cruce.add_argument("--parquet", required=True, help="Carpeta raiz del dataset Parquet")
    cpa_cruce.add_argument("--rfc", default=None, help="RFC del proveedor (por defecto se lee del Compras)")
    cpa_cruce.add_argument("--output", required=True, help="Excel de salida con las columnas llenas")

    cpa_salida = sub.add_parser(
        "cpa-salida",
        help="Genera la salida completa de un proveedor: compras -> cruce -> recalculo -> validacion",
    )
    cpa_salida.add_argument("--vendor", required=True, help="Numero de proveedor")
    cpa_salida.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD")
    cpa_salida.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD")
    cpa_salida.add_argument("--parquet", required=True, help="Carpeta raiz del dataset Parquet")
    cpa_salida.add_argument("--output-dir", default=None, help="Carpeta de salida")

    cpa_val = sub.add_parser(
        "cpa-validacion-grande",
        help="Solo la Validacion de un proveedor gigante (por trimestre, sin Compras)",
    )
    cpa_val.add_argument("--vendor", required=True, help="Numero de proveedor")
    cpa_val.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD")
    cpa_val.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD")
    cpa_val.add_argument("--parquet", required=True, help="Carpeta raiz del dataset Parquet")
    cpa_val.add_argument("--output-dir", default=None, help="Carpeta de salida")

    cpa_comp = sub.add_parser(
        "cpa-compras-grande",
        help="Solo los Compras de un proveedor gigante, por trimestre (o mes), resumible",
    )
    cpa_comp.add_argument("--vendor", required=True, help="Numero de proveedor")
    cpa_comp.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD")
    cpa_comp.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD")
    cpa_comp.add_argument("--parquet", required=True, help="Carpeta raiz del dataset Parquet")
    cpa_comp.add_argument("--output-dir", default=None, help="Carpeta de salida")
    cpa_comp.add_argument("--por-mes", action="store_true", help="Partir por mes en vez de trimestre")

    sub.add_parser("gui", help="Abre la interfaz grafica")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command in (None, "gui"):
        from automation_cobros.app import run_app

        run_app()
        return

    if args.command == "extract":
        df = fetch_compras(args.vendor, args.start, args.end)
        write_compras_workbook(df, Path(args.output), vendor=args.vendor, start_date=args.start, end_date=args.end)
        return

    if args.command == "recalc":
        recalculate_compras_file(Path(args.input), Path(args.output))
        return

    if args.command == "validate":
        write_validation_workbook(Path(args.input), Path(args.output))
        return

    if args.command == "cpa-salida":
        import config
        from automation_cobros.pipeline import generar_salida_proveedor

        salida_dir = Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR
        resultado = generar_salida_proveedor(
            args.vendor, args.start, args.end, args.parquet, salida_dir
        )
        print(f"\nRFC: {resultado.rfc}")
        print(f"Carpeta   : {resultado.proveedor_dir}")
        if len(resultado.compras_paths) == 1:
            print(f"Compras   : {resultado.compras_path}")
        else:
            print(f"Compras   : {len(resultado.compras_paths)} archivos por año:")
            for ruta in resultado.compras_paths:
                print(f"            {ruta}")
        print(f"Validacion: {resultado.validacion_path}")
        print(f"Soportes  : {len(resultado.soportes)} ZIP de CPA Vision")
        return

    if args.command == "cpa-validacion-grande":
        import config
        from automation_cobros.pipeline_streaming import generar_validacion_grande

        salida_dir = Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR
        resultado = generar_validacion_grande(
            args.vendor, args.start, args.end, args.parquet, salida_dir
        )
        print(f"\nRFC: {resultado.rfc}")
        print(f"Validacion: {resultado.validacion_path}")
        print(f"Soportes  : {len(resultado.soportes)} ZIP de CPA Vision")
        return

    if args.command == "cpa-compras-grande":
        import config
        from automation_cobros.pipeline_streaming import generar_compras_grande

        salida_dir = Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR
        rutas = generar_compras_grande(
            args.vendor, args.start, args.end, args.parquet, salida_dir, por_mes=args.por_mes
        )
        print(f"\n{len(rutas)} archivos de Compras generados/presentes.")
        return

    if args.command == "cpa-cruce":
        from automation_cobros.cruce_cpa import cruzar_proveedor

        resultado, rfc = cruzar_proveedor(args.compras, args.parquet, rfc=args.rfc)
        print(f"RFC del proveedor: {rfc}\n")
        print(resultado.resumen())
        resultado.df.to_excel(Path(args.output), index=False)
        print(f"\nSalida: {args.output}")
        return

    if args.command == "cpa-session":
        from automation_cobros.cpa_vision import CPAVisionSettings, run_manual_session

        settings = CPAVisionSettings.from_overrides(
            base_url=args.url,
            download_dir=args.download_dir,
            state_path=args.state,
            browser_channel=args.browser_channel,
            headless=True if args.headless else None,
            timeout_ms=args.timeout_ms,
            slow_mo_ms=args.slow_mo_ms,
        )
        run_manual_session(settings)
        return

    if args.command == "cpa-csvs":
        from automation_cobros.cpa_vision import list_downloaded_csvs

        for csv_path in list_downloaded_csvs(args.download_dir):
            print(csv_path)
        return

    if args.command == "cpa-downloads-page":
        from automation_cobros.cpa_vision import CPAVisionSettings, open_downloads_page

        settings = CPAVisionSettings.from_overrides(
            base_url=args.url,
            download_dir=args.download_dir,
            state_path=args.state,
            browser_channel=args.browser_channel,
            headless=True if args.headless else None,
            timeout_ms=args.timeout_ms,
            slow_mo_ms=args.slow_mo_ms,
        )
        open_downloads_page(
            settings,
            username=args.user,
            rfc=args.rfc,
            years=range(args.start_year, args.end_year + 1),
            configure_defaults=not args.skip_config,
            keep_open=not args.close,
        )
        return

    if args.command == "cpa-request-download":
        from automation_cobros.cpa_vision import CPAVisionSettings, request_download_and_wait

        settings = CPAVisionSettings.from_overrides(
            base_url=args.url,
            download_dir=args.download_dir,
            state_path=args.state,
            browser_channel=args.browser_channel,
            headless=True if args.headless else None,
            timeout_ms=args.timeout_ms,
            slow_mo_ms=args.slow_mo_ms,
        )
        request_download_and_wait(
            settings,
            username=args.user,
            rfc=args.rfc,
            years=range(args.start_year, args.end_year + 1),
            poll_seconds=args.poll_seconds,
            max_wait_minutes=args.max_wait_minutes,
            keep_open=args.keep_open,
        )
        return

    if args.command == "cpa-wait-download":
        from automation_cobros.cpa_vision import CPAVisionSettings, wait_for_existing_request_download

        settings = CPAVisionSettings.from_overrides(
            base_url=args.url,
            download_dir=args.download_dir,
            state_path=args.state,
            browser_channel=args.browser_channel,
            headless=True if args.headless else None,
            timeout_ms=args.timeout_ms,
            slow_mo_ms=args.slow_mo_ms,
        )
        wait_for_existing_request_download(
            settings,
            request_id=args.request_id,
            username=args.user,
            poll_seconds=args.poll_seconds,
            max_wait_minutes=args.max_wait_minutes,
            keep_open=args.keep_open,
        )
        return

    if args.command == "cpa-batch-vendors":
        from automation_cobros.cpa_vision import CPAVisionSettings, request_vendor_master_batch

        settings = CPAVisionSettings.from_overrides(
            base_url=args.url,
            download_dir=args.download_dir,
            state_path=args.state,
            browser_channel=args.browser_channel,
            headless=True if args.headless else None,
            timeout_ms=args.timeout_ms,
            slow_mo_ms=args.slow_mo_ms,
        )
        request_vendor_master_batch(
            settings,
            vendor_master_path=Path(args.input),
            username=args.user,
            password=args.password,
            batch_size=args.batch_size,
            start_index=args.start_index,
            poll_seconds=args.poll_seconds,
            max_wait_minutes=args.max_wait_minutes,
            metrics_path=Path(args.metrics_output) if args.metrics_output else None,
            parquet_dir=Path(args.parquet_dir) if args.parquet_dir else None,
            continue_on_error=not args.stop_on_error,
            keep_open=args.keep_open,
        )
        return

    if args.command == "cpa-zip-to-parquet":
        from automation_cobros.cpa_parquet import zip_to_parquet_dataset

        input_path = Path(args.input)
        if input_path.is_file() and input_path.suffix.lower() == ".zip":
            zip_paths = [input_path]
        else:
            zip_paths = sorted(input_path.glob("*.zip"), key=lambda path: path.stat().st_mtime)

        if not zip_paths:
            raise FileNotFoundError(f"No se encontraron archivos .zip en: {args.input}")

        output_root = Path(args.output)
        for zip_path in zip_paths:
            rfc = args.rfc or zip_path.stem
            request_id = args.request_id or zip_path.stem
            result = zip_to_parquet_dataset(zip_path, output_root, rfc=rfc, request_id=request_id)
            print(
                f"ZIP convertido: {zip_path} -> {result.output_root} "
                f"({result.files} archivos Parquet, {result.rows:,} filas)"
            )
        return

    if args.command == "cpa-consolidate":
        from automation_cobros.cpa_consolidator import consolidate_cpa_zip_to_excel

        result = consolidate_cpa_zip_to_excel(Path(args.input), Path(args.output))
        print(f"Excel consolidado: {result.output_path}")
        print(f"ZIP procesados: {result.zip_files}")
        print(f"CSV procesados: {result.source_files}")
        print(f"Filas consolidadas: {result.rows:,}")
        return

    parser.error("Comando no reconocido")


if __name__ == "__main__":
    main()
