from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import getpass
from pathlib import Path
import re
import time
from typing import Any

import pandas as pd

import config
from automation_costos.cpa_parquet import zip_to_parquet_dataset
from automation_costos.utils import ensure_parent, safe_filename

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - handled at runtime with a clear message.
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


_CFDI_FILTER_OPTIONS = (
    "Todos",
    "Vigentes",
    "Cancelados",
    "Ingreso",
    "Egreso",
    "Complementos de pago",
    "Traslado",
)
_RECEIVED_CFDI_FILTERS = frozenset({"Vigentes", "Ingreso"})
_CPA_DOWNLOAD_FILE_OPTION = "Hoja de cálculo con detalle de conceptos y Tasas (.csv)"
_CPA_DOWNLOAD_EXTRA_OPTIONS = ("Generar acumulado",)
_BROWSER_LOCALE = "es-MX"
_DISABLE_TRANSLATE_ARGS = (
    "--disable-translate",
    "--disable-features=Translate,TranslateUI",
    f"--lang={_BROWSER_LOCALE}",
)


@dataclass(slots=True)
class CPAVisionSettings:
    base_url: str = config.CPA_VISION_URL
    download_dir: Path = config.CPA_VISION_DOWNLOAD_DIR
    state_path: Path = config.CPA_VISION_STATE_PATH
    headless: bool = config.CPA_VISION_HEADLESS
    browser_channel: str | None = config.CPA_VISION_BROWSER_CHANNEL
    timeout_ms: int = 60_000
    slow_mo_ms: int = 0

    @classmethod
    def from_overrides(
        cls,
        *,
        base_url: str | None = None,
        download_dir: Path | str | None = None,
        state_path: Path | str | None = None,
        headless: bool | None = None,
        browser_channel: str | None = None,
        timeout_ms: int | None = None,
        slow_mo_ms: int | None = None,
    ) -> "CPAVisionSettings":
        return cls(
            base_url=base_url or config.CPA_VISION_URL,
            download_dir=Path(download_dir) if download_dir else config.CPA_VISION_DOWNLOAD_DIR,
            state_path=Path(state_path) if state_path else config.CPA_VISION_STATE_PATH,
            headless=config.CPA_VISION_HEADLESS if headless is None else headless,
            browser_channel=browser_channel if browser_channel is not None else config.CPA_VISION_BROWSER_CHANNEL,
            timeout_ms=timeout_ms or 60_000,
            slow_mo_ms=slow_mo_ms or 0,
        )


@dataclass(slots=True)
class CPAVisionBatchJob:
    source_index: int
    rfc: str
    fechas: str
    years: tuple[int, ...]


def run_manual_session(settings: CPAVisionSettings | None = None) -> list[Path]:
    """Open CPA Vision and let the user navigate/download files manually.

    This is the first phase: it verifies access, stores session state, and captures
    downloads without hardcoding site selectors.
    """
    _require_playwright()
    settings = settings or CPAVisionSettings()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    ensure_parent(settings.state_path)

    downloaded_files: list[Path] = []
    attached_pages: set[int] = set()
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, settings)
        context_kwargs: dict[str, Any] = {"accept_downloads": True, "locale": _BROWSER_LOCALE}
        if settings.state_path.exists():
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)

        def attach_handlers(page) -> None:
            page_id = id(page)
            if page_id in attached_pages:
                return
            attached_pages.add(page_id)
            page.on(
                "download",
                lambda download: _save_download(download, settings.download_dir, downloaded_files),
            )

        context.on("page", attach_handlers)
        page = context.new_page()
        attach_handlers(page)
        page.goto(settings.base_url, wait_until="domcontentloaded")
        _dismiss_transient_overlays(page)

        print("CPA Vision abierto.")
        print(f"Carpeta de descargas: {settings.download_dir}")
        print("Inicia sesion, selecciona las opciones y descarga los CSV.")
        input("Cuando termines, presiona Enter aqui para guardar la sesion y cerrar el navegador...")

        context.storage_state(path=str(settings.state_path))
        browser.close()

    print(f"Sesion guardada en: {settings.state_path}")
    if downloaded_files:
        print("Archivos descargados:")
        for file_path in downloaded_files:
            print(f"  {file_path}")
    return downloaded_files


def open_downloads_page(
    settings: CPAVisionSettings | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
    rfc: str | None = None,
    years: range | None = None,
    configure_defaults: bool = True,
    keep_open: bool = True,
) -> None:
    """Log in to CPA Vision and stop at the massive downloads screen."""
    _require_playwright()
    settings = settings or CPAVisionSettings()
    username = username or config.CPA_VISION_USER
    password = password or config.CPA_VISION_PASSWORD

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    ensure_parent(settings.state_path)

    with sync_playwright() as playwright:
        _log_step(f"Abriendo navegador: {settings.browser_channel or 'chromium'}")
        browser = _launch_browser(playwright, settings)
        context_kwargs: dict[str, Any] = {"accept_downloads": True, "locale": _BROWSER_LOCALE}
        if settings.state_path.exists():
            _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()

        try:
            _log_step(f"Abriendo CPA Vision: {settings.base_url}")
            page.goto(settings.base_url, wait_until="domcontentloaded")
            _dismiss_transient_overlays(page)
            if not _is_empresa_or_downloads_page(page):
                if not username:
                    username = input("Usuario CPA Vision: ").strip()
                if not password:
                    password = getpass.getpass("Password CPA Vision: ")
                if not username or not password:
                    raise ValueError("Usuario y password son requeridos para iniciar sesion en CPA Vision.")
                _login(page, username, password, settings.timeout_ms)
            else:
                _log_step("La sesion guardada ya esta activa")

            _open_descargas(page, settings.timeout_ms)
            if configure_defaults:
                _configure_default_download_options(page, rfc=rfc, years=years)
            context.storage_state(path=str(settings.state_path))

            print("CPA Vision quedo abierto en la pantalla de descarga masiva.", flush=True)
            print(f"Sesion guardada en: {settings.state_path}", flush=True)
            if keep_open and not settings.headless:
                input("Presiona Enter para cerrar el navegador...")
        except Exception:
            _save_debug_artifacts(page, "cpavision_error")
            raise
        finally:
            browser.close()


def request_download_and_wait(
    settings: CPAVisionSettings | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
    rfc: str | None = None,
    years: range | None = None,
    poll_seconds: int = 20,
    max_wait_minutes: int = 420,
    keep_open: bool = False,
) -> Path:
    """Create the CPA Vision CSV request and download the resulting ZIP."""
    _require_playwright()
    settings = settings or CPAVisionSettings()
    username = username or config.CPA_VISION_USER
    password = password or config.CPA_VISION_PASSWORD
    rfc = (rfc or config.CPA_VISION_RFC).strip()
    if not rfc:
        rfc = input("RFC proveedor: ").strip()
    if not rfc:
        raise ValueError("RFC es requerido para solicitar la descarga en CPA Vision.")

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    ensure_parent(settings.state_path)

    with sync_playwright() as playwright:
        _log_step(f"Abriendo navegador: {settings.browser_channel or 'chromium'}")
        browser = _launch_browser(playwright, settings)
        context_kwargs: dict[str, Any] = {"accept_downloads": True, "locale": _BROWSER_LOCALE}
        if settings.state_path.exists():
            _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()

        try:
            _log_step(f"Abriendo CPA Vision: {settings.base_url}")
            page.goto(settings.base_url, wait_until="domcontentloaded")
            _dismiss_transient_overlays(page)
            if not _is_empresa_or_downloads_page(page):
                if not username:
                    username = input("Usuario CPA Vision: ").strip()
                if not password:
                    password = getpass.getpass("Password CPA Vision: ")
                if not username or not password:
                    raise ValueError("Usuario y password son requeridos para iniciar sesion en CPA Vision.")
                _login(page, username, password, settings.timeout_ms)

            _open_descargas(page, settings.timeout_ms)
            _configure_default_download_options(page, rfc=rfc, years=years)
            request_id = _submit_download_request(page, settings.timeout_ms)
            context.storage_state(path=str(settings.state_path))
            output_path = _wait_for_request_zip(
                page,
                request_id,
                settings.download_dir,
                poll_seconds=poll_seconds,
                max_wait_minutes=max_wait_minutes,
                    settings=settings,
                    username=username,
                    password=password,
            )
            print(f"ZIP descargado: {output_path}", flush=True)
            if keep_open and not settings.headless:
                input("Presiona Enter para cerrar el navegador...")
            return output_path
        except Exception:
            _save_debug_artifacts(page, "cpavision_error")
            raise
        finally:
            browser.close()


def request_vendor_master_batch(
    settings: CPAVisionSettings | None = None,
    *,
    vendor_master_path: Path | str,
    username: str | None = None,
    password: str | None = None,
    batch_size: int = 50,
    start_index: int = 0,
    poll_seconds: int = 20,
    max_wait_minutes: int = 420,
    metrics_path: Path | str | None = None,
    parquet_dir: Path | str | None = None,
    continue_on_error: bool = True,
    keep_open: bool = False,
) -> Path:
    """Process a vendor master Excel in sequential CPA Vision download batches."""
    _require_playwright()
    settings = settings or CPAVisionSettings()
    username = username or config.CPA_VISION_USER
    password = password or config.CPA_VISION_PASSWORD
    if batch_size <= 0:
        raise ValueError("batch_size debe ser mayor que cero.")
    if start_index < 0:
        raise ValueError("start_index no puede ser negativo.")
    jobs = _load_vendor_master_jobs(vendor_master_path)
    selected_jobs = jobs[start_index : start_index + batch_size]
    if not selected_jobs:
        raise ValueError("No hay proveedores para procesar con los parametros indicados.")

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    ensure_parent(settings.state_path)
    metrics_file = Path(metrics_path) if metrics_path else _default_batch_metrics_path(settings.download_dir)
    parquet_root = Path(parquet_dir) if parquet_dir else settings.download_dir / "parquet"

    with sync_playwright() as playwright:
        browser = None
        context = None
        page = None

        try:
            if not username:
                username = input("Usuario CPA Vision: ").strip()
            if not password:
                password = getpass.getpass("Password CPA Vision: ")
            if not username or not password:
                raise ValueError("Usuario y password son requeridos para iniciar sesion en CPA Vision.")

            browser, context, page = _start_authenticated_downloads_session(
                playwright,
                settings,
                username,
                password,
            )
            context.storage_state(path=str(settings.state_path))

            total = len(selected_jobs)
            for position, job in enumerate(selected_jobs, start=1):
                started_at = datetime.now()
                started_monotonic = time.monotonic()
                request_id = ""
                output_path: Path | None = None
                parquet_rows = 0
                parquet_files = 0
                status = "downloaded"
                error = ""
                recovered = False

                _log_step(
                    f"Lote CPA {position}/{total}: RFC {job.rfc}, anos {', '.join(map(str, job.years))}"
                )

                for attempt in range(1, 3):
                    try:
                        if request_id:
                            recovered = True
                            _log_step(f"Recuperando solicitud ya creada {request_id}")
                            browser, context, page = _restart_authenticated_downloads_session(
                                playwright,
                                settings,
                                username,
                                password,
                                browser,
                            )
                            output_path = _wait_for_request_zip(
                                page,
                                request_id,
                                settings.download_dir,
                                poll_seconds=poll_seconds,
                                max_wait_minutes=max_wait_minutes,
                                settings=settings,
                                username=username,
                                password=password,
                                rfc=job.rfc,
                                years=job.years,
                            )
                            # Si la solicitud se regeneró durante la espera, el ZIP trae el
                            # request_id nuevo; se usa ese para particionar el Parquet.
                            request_id = _request_id_from_zip(output_path) or request_id
                            parquet_result = zip_to_parquet_dataset(
                                output_path,
                                parquet_root,
                                rfc=job.rfc,
                                request_id=request_id,
                            )
                            parquet_rows = parquet_result.rows
                            parquet_files = parquet_result.files
                            _return_to_downloads_form(page, settings.timeout_ms)
                            status = "downloaded_after_recovery"
                            error = ""
                            break

                        if attempt > 1:
                            recovered = True
                            _log_step(f"Reintentando proveedor {job.rfc} desde cero")
                            browser, context, page = _restart_authenticated_downloads_session(
                                playwright,
                                settings,
                                username,
                                password,
                                browser,
                            )

                        _return_to_downloads_form(page, settings.timeout_ms)
                        _configure_default_download_options(page, rfc=job.rfc, years=job.years)
                        request_id = _submit_download_request(page, settings.timeout_ms)
                        context.storage_state(path=str(settings.state_path))
                        output_path = _wait_for_request_zip(
                            page,
                            request_id,
                            settings.download_dir,
                            poll_seconds=poll_seconds,
                            max_wait_minutes=max_wait_minutes,
                            settings=settings,
                            username=username,
                            password=password,
                            rfc=job.rfc,
                            years=job.years,
                        )
                        # Si la solicitud se regeneró durante la espera, el ZIP trae el
                        # request_id nuevo; se usa ese para particionar el Parquet.
                        request_id = _request_id_from_zip(output_path) or request_id
                        parquet_result = zip_to_parquet_dataset(
                            output_path,
                            parquet_root,
                            rfc=job.rfc,
                            request_id=request_id,
                        )
                        parquet_rows = parquet_result.rows
                        parquet_files = parquet_result.files
                        _return_to_downloads_form(page, settings.timeout_ms)
                        status = "downloaded_after_recovery" if recovered else "downloaded"
                        error = ""
                        break
                    except Exception as exc:
                        error = str(exc)
                        _save_debug_artifacts(page, f"cpavision_batch_error_{job.source_index}_{job.rfc}")
                        if attempt < 2:
                            if request_id:
                                _log_step(
                                    f"Fallo despues de crear solicitud {request_id}. "
                                    "Se reabrira CPA Vision para descargarla."
                                )
                            else:
                                _log_step(
                                    f"Fallo antes de crear solicitud para {job.rfc}. "
                                    "Se reabrira CPA Vision y se reintentara desde cero."
                                )
                            continue
                        status = "error"
                        if not continue_on_error:
                            _append_batch_metric(
                                metrics_file,
                                _build_batch_metric(
                                    job,
                                    position,
                                    started_at,
                                    started_monotonic,
                                    request_id=request_id,
                                    output_path=output_path,
                                    parquet_root=parquet_root,
                                    parquet_rows=parquet_rows,
                                    parquet_files=parquet_files,
                                    status=status,
                                    error=error,
                                ),
                            )
                            raise
                        try:
                            browser, context, page = _restart_authenticated_downloads_session(
                                playwright,
                                settings,
                                username,
                                password,
                                browser,
                            )
                        except Exception as restart_exc:
                            _log_step(f"No se pudo reabrir CPA Vision despues del error: {restart_exc}")

                _append_batch_metric(
                    metrics_file,
                    _build_batch_metric(
                        job,
                        position,
                        started_at,
                        started_monotonic,
                        request_id=request_id,
                        output_path=output_path,
                        parquet_root=parquet_root,
                        parquet_rows=parquet_rows,
                        parquet_files=parquet_files,
                        status=status,
                        error=error,
                    ),
                )

            _resumen_batch(metrics_file)
            actualizar_metricas_totales(settings.download_dir)
            # El inventario que consultan los auditores se regenera solo al cerrar el lote,
            # para que nadie tenga que copiarlo a mano. No lanza: ver actualizar_inventario.
            from automation_costos.inventario_cpa import actualizar_inventario

            actualizar_inventario(parquet_root)
            # Segundo proceso, INDEPENDIENTE del anterior: la carpeta de complemento se
            # queda solo con los proveedor-año de cobertura EDI < 90% y lleva su propio
            # inventario. Va aparte a proposito — si el complemento falla, el inventario
            # general ya quedo escrito, y al reves igual. Ninguno de los dos tumba el lote.
            from automation_costos.complemento_cpa import actualizar_complemento

            actualizar_complemento(settings.download_dir)
            print(f"Metricas CPA Vision: {metrics_file}", flush=True)
            if keep_open and not settings.headless:
                input("Presiona Enter para cerrar el navegador...")
            return metrics_file
        except Exception:
            if page is not None:
                _save_debug_artifacts(page, "cpavision_batch_error")
            raise
        finally:
            _close_browser_quietly(browser)


def _start_authenticated_downloads_session(
    playwright,
    settings: CPAVisionSettings,
    username: str,
    password: str,
):
    _log_step(f"Abriendo navegador: {settings.browser_channel or 'chromium'}")
    browser = _launch_browser(playwright, settings)
    context_kwargs: dict[str, Any] = {"accept_downloads": True, "locale": _BROWSER_LOCALE}
    if settings.state_path.exists():
        _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
        context_kwargs["storage_state"] = str(settings.state_path)
    context = browser.new_context(**context_kwargs)
    context.set_default_timeout(settings.timeout_ms)
    page = context.new_page()

    _log_step(f"Abriendo CPA Vision: {settings.base_url}")
    page.goto(settings.base_url, wait_until="domcontentloaded")
    _dismiss_transient_overlays(page)
    if not _is_empresa_or_downloads_page(page):
        _login(page, username, password, settings.timeout_ms)
    _open_descargas(page, settings.timeout_ms)
    context.storage_state(path=str(settings.state_path))
    return browser, context, page


def _restart_authenticated_downloads_session(
    playwright,
    settings: CPAVisionSettings,
    username: str,
    password: str,
    browser,
):
    _log_step("Reabriendo CPA Vision para continuar el lote")
    _close_browser_quietly(browser)
    return _start_authenticated_downloads_session(playwright, settings, username, password)


def _close_browser_quietly(browser) -> None:
    if browser is None:
        return
    try:
        browser.close()
    except Exception:
        return


def wait_for_existing_request_download(
    settings: CPAVisionSettings | None = None,
    *,
    request_id: str,
    username: str | None = None,
    password: str | None = None,
    poll_seconds: int = 20,
    max_wait_minutes: int = 420,
    keep_open: bool = False,
) -> Path:
    """Open CPA Vision requests and download a previously created request."""
    _require_playwright()
    settings = settings or CPAVisionSettings()
    username = username or config.CPA_VISION_USER
    password = password or config.CPA_VISION_PASSWORD
    request_id = str(request_id).strip()
    if not request_id:
        raise ValueError("request_id es requerido.")

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    ensure_parent(settings.state_path)

    with sync_playwright() as playwright:
        _log_step(f"Abriendo navegador: {settings.browser_channel or 'chromium'}")
        browser = _launch_browser(playwright, settings)
        context_kwargs: dict[str, Any] = {"accept_downloads": True, "locale": _BROWSER_LOCALE}
        if settings.state_path.exists():
            _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()

        try:
            _log_step(f"Abriendo CPA Vision: {settings.base_url}")
            page.goto(settings.base_url, wait_until="domcontentloaded")
            _dismiss_transient_overlays(page)
            if not _is_empresa_or_downloads_page(page):
                if not username:
                    username = input("Usuario CPA Vision: ").strip()
                if not password:
                    password = getpass.getpass("Password CPA Vision: ")
                if not username or not password:
                    raise ValueError("Usuario y password son requeridos para iniciar sesion en CPA Vision.")
                _login(page, username, password, settings.timeout_ms)
            _open_descargas(page, settings.timeout_ms)
            output_path = _wait_for_request_zip(
                page,
                request_id,
                settings.download_dir,
                poll_seconds=poll_seconds,
                max_wait_minutes=max_wait_minutes,
                    settings=settings,
                    username=username,
                    password=password,
            )
            print(f"ZIP descargado: {output_path}", flush=True)
            if keep_open and not settings.headless:
                input("Presiona Enter para cerrar el navegador...")
            return output_path
        except Exception:
            _save_debug_artifacts(page, "cpavision_error")
            raise
        finally:
            browser.close()


def _login(page, username: str, password: str, timeout_ms: int) -> None:
    if _is_empresa_or_downloads_page(page):
        return

    _log_step("Llenando usuario")
    _fill_first_visible(
        page,
        [
            lambda: page.get_by_label(re.compile("correo", re.IGNORECASE)),
            lambda: page.locator("input[type='email']"),
            lambda: page.locator("input[name*='mail' i]"),
            lambda: page.locator("input").nth(0),
        ],
        username,
        "usuario/correo",
    )
    _log_step("Llenando password")
    _fill_first_visible(
        page,
        [
            lambda: page.get_by_label(re.compile("contrase|password", re.IGNORECASE)),
            lambda: page.locator("input[type='password']"),
        ],
        password,
        "password",
    )
    _log_step("Seleccionando FacReview si aparece")
    _select_facreview_if_present(page)
    _log_step("Dando clic en Iniciar sesion")
    _click_first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile("iniciar", re.IGNORECASE)),
            lambda: page.get_by_text(re.compile("iniciar sesi", re.IGNORECASE)),
        ],
        "Iniciar sesion",
    )

    _log_step("Esperando pantalla de empresas")
    try:
        page.wait_for_url(re.compile(r".*(okta/empresas|descarga-masiva/descargas).*"), timeout=timeout_ms)
    except Exception:
        page.get_by_text(re.compile("seleccionar empresa|descarga masiva", re.IGNORECASE)).wait_for(
            timeout=timeout_ms
        )
    _dismiss_transient_overlays(page)


def _launch_browser(playwright, settings: CPAVisionSettings):
    launch_kwargs: dict[str, Any] = {
        "headless": settings.headless,
        "slow_mo": settings.slow_mo_ms,
        "args": list(_DISABLE_TRANSLATE_ARGS),
    }
    if settings.browser_channel:
        launch_kwargs["channel"] = settings.browser_channel
    return playwright.chromium.launch(**launch_kwargs)


def _open_descargas(page, timeout_ms: int) -> None:
    if re.search(r"descarga-masiva/descargas", page.url, re.IGNORECASE):
        _log_step("Ya estas en Descarga masiva")
        _acknowledge_download_notices(page)
        _dismiss_transient_overlays(page)
        return

    _log_step("Esperando empresa SORIANA")
    try:
        page.get_by_text(re.compile(r"1873\s*-\s*SORIANA", re.IGNORECASE)).wait_for(timeout=timeout_ms)
    except Exception:
        page.get_by_text(re.compile("seleccionar empresa", re.IGNORECASE)).wait_for(timeout=timeout_ms)

    _log_step("Dando clic en Descargas")
    _click_first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile("descargas", re.IGNORECASE)),
            lambda: page.get_by_text("Descargas", exact=True),
            lambda: page.locator("text=Descargas"),
        ],
        "Descargas",
    )

    _log_step("Esperando pantalla Descarga masiva")
    try:
        page.wait_for_url(re.compile(r".*descarga-masiva/descargas.*"), timeout=timeout_ms)
    except Exception:
        page.get_by_text(re.compile("descarga masiva de archivos", re.IGNORECASE)).wait_for(
            timeout=timeout_ms
        )
    _acknowledge_download_notices(page)
    _dismiss_transient_overlays(page)


def _acknowledge_download_notices(page) -> None:
    notices = [
        ("Aviso Importante", re.compile(r"aviso\s+importante", re.IGNORECASE)),
        (
            "Disponibilidad limitada de descargas",
            re.compile(r"disponibilidad\s+limitada(?:\s+de\s+descargas)?", re.IGNORECASE),
        ),
    ]

    for _ in range(4):
        clicked = False
        for description, pattern in notices:
            if not _is_visible_text(page, pattern, timeout_ms=1_500):
                continue
            _log_step(f"Aviso detectado: {description}. Dando clic en Enterado")
            if not _click_enterado_button(page):
                raise RuntimeError(f"Se detecto el aviso '{description}', pero no se encontro el boton Enterado.")
            page.wait_for_timeout(500)
            clicked = True
            break
        if not clicked:
            return


def _dismiss_transient_overlays(page) -> None:
    """Close optional browser/page overlays that are not part of the audit flow."""
    dismissed = False
    for handler in (_dismiss_dom_translate_prompt, _dismiss_in_progress_request_dialog):
        try:
            dismissed = handler(page) or dismissed
        except Exception as exc:
            _log_step(f"No se pudo cerrar overlay opcional: {exc}")
    if dismissed:
        page.wait_for_timeout(300)


def _dismiss_dom_translate_prompt(page) -> bool:
    # The Edge/Chrome translation bubble is browser UI and is disabled at launch.
    # This fallback handles any equivalent in-page prompt if the site injects one.
    patterns = (
        re.compile(r"^\s*not\s+now\s*$", re.IGNORECASE),
        re.compile(r"^\s*ahora\s+no\s*$", re.IGNORECASE),
    )
    for pattern in patterns:
        locators = [
            lambda pattern=pattern: page.get_by_role("button", name=pattern),
            lambda pattern=pattern: page.locator("button").filter(has_text=pattern),
            lambda pattern=pattern: page.get_by_text(pattern),
        ]
        for factory in locators:
            try:
                locator = factory().first
                locator.wait_for(state="visible", timeout=800)
                locator.click(timeout=800)
                _log_step("Cuadro de traduccion cerrado: Not now")
                return True
            except Exception:
                continue
    return False


def _dismiss_in_progress_request_dialog(page) -> bool:
    result = page.evaluate(
        """
        () => {
            const normalize = (value) => String(value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.visibility === "hidden" || style.display === "none") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const textOf = (el) => normalize(el.innerText || el.textContent || "");
            const elements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text);

            const title = elements
                .filter((item) => item.text.includes("solicitud en proceso") && item.text.length <= 80)
                .sort((a, b) => a.rect.top - b.rect.top)[0];
            if (!title) {
                return { found: false, closed: false };
            }

            let container = title.el;
            for (let i = 0; i < 8 && container.parentElement; i += 1) {
                const parent = container.parentElement;
                const rect = parent.getBoundingClientRect();
                const parentText = textOf(parent);
                const area = rect.width * rect.height;
                const viewportArea = window.innerWidth * window.innerHeight;
                if (
                    rect.width >= 300
                    && rect.height >= 80
                    && rect.width <= window.innerWidth * 0.98
                    && rect.height <= window.innerHeight * 0.85
                    && area <= viewportArea * 0.75
                    && parentText.includes("solicitud en proceso")
                    && parentText.includes("esta siendo procesada")
                ) {
                    container = parent;
                }
            }

            const containerRect = container.getBoundingClientRect();
            const closeTerms = /(cerrar|close|dismiss|arrow|flecha|chevron|angle|right|up|times|remove|cancel|x)/i;
            const candidates = Array.from(container.querySelectorAll("button, a, [role='button'], i, span, div"))
                .filter(isVisible)
                .map((el) => {
                    const rect = el.getBoundingClientRect();
                    const attrs = [
                        el.innerText,
                        el.textContent,
                        el.getAttribute("aria-label"),
                        el.getAttribute("title"),
                        el.getAttribute("class"),
                        el.id,
                    ].join(" ");
                    const nearTopRight = rect.top <= containerRect.top + 80
                        && rect.right >= containerRect.right - 120;
                    const keyword = closeTerms.test(attrs);
                    const hasPointer = window.getComputedStyle(el).cursor === "pointer";
                    return {
                        el,
                        nearTopRight,
                        keyword,
                        hasPointer,
                        score: (nearTopRight ? 0 : 1000)
                            + (keyword ? 0 : 200)
                            + (hasPointer ? 0 : 50)
                            + Math.abs(rect.right - containerRect.right)
                            + Math.abs(rect.top - containerRect.top),
                    };
                })
                .filter((item) => item.nearTopRight && (item.keyword || item.hasPointer))
                .sort((a, b) => a.score - b.score);

            if (candidates[0]) {
                candidates[0].el.click();
                return { found: true, closed: true, method: "candidate" };
            }

            const fallbackX = containerRect.right - 24;
            const fallbackY = containerRect.top + 24;
            const fallback = document.elementFromPoint(fallbackX, fallbackY);
            if (fallback && container.contains(fallback) && fallback !== container) {
                fallback.click();
                return { found: true, closed: true, method: "top-right" };
            }

            return { found: true, closed: false };
        }
        """
    )
    if result.get("closed"):
        _log_step("Cuadro 'Solicitud en proceso' cerrado")
        return True
    if result.get("found"):
        _log_step("Cuadro 'Solicitud en proceso' detectado, pero no se pudo cerrar automaticamente")
    return False


def _is_visible_text(page, pattern: re.Pattern[str], *, timeout_ms: int) -> bool:
    try:
        page.get_by_text(pattern).first.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


def _click_enterado_button(page) -> bool:
    enterado = re.compile(r"^\s*enterado\s*$", re.IGNORECASE)
    locators = [
        lambda: page.get_by_role("button", name=enterado),
        lambda: page.locator("button").filter(has_text=enterado),
        lambda: page.get_by_text(enterado),
    ]
    for factory in locators:
        try:
            locator = factory().first
            locator.wait_for(state="visible", timeout=1_500)
            locator.click(timeout=1_500)
            return True
        except Exception:
            continue
    return bool(
        page.evaluate(
            """
            () => {
                const normalize = (value) => String(value || "")
                    .normalize("NFD")
                    .replace(/[\\u0300-\\u036f]/g, "")
                    .replace(/\\s+/g, " ")
                    .trim()
                    .toLowerCase();

                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (style.visibility === "hidden" || style.display === "none") return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };

                const candidates = Array.from(document.querySelectorAll("button, a, input, div, span"))
                    .filter(isVisible)
                    .filter((el) => normalize(el.innerText || el.value || el.textContent) === "enterado");
                const preferred = candidates.find((el) => ["BUTTON", "A", "INPUT"].includes(el.tagName))
                    || candidates[0];
                if (!preferred) return false;
                preferred.click();
                return true;
            }
            """
        )
    )


def _configure_default_download_options(
    page,
    *,
    rfc: str | None = None,
    years: range | None = None,
) -> None:
    years = years or range(2020, 2025)
    selected_years = set(years)

    # Margen de la auditoría: las facturas de 2025 subidas tarde se emiten hasta enero 2026.
    # Por eso, cuando el periodo incluye 2025, además de los años completos se marca SOLO el
    # mes de enero 2026 (celda del mes, no el año 2026 entero). Reunión con Mónica 2026-08-05.
    meses_extra = {_MES_MARGEN} if 2025 in selected_years else set()

    _log_step("Limpiando filtros EMITIDOS")
    _set_left_filter_options(page, section="EMITIDOS", enabled_options=frozenset())

    _log_step("Configurando filtros RECIBIDOS")
    _set_left_filter_options(page, section="RECIBIDOS", enabled_options=_RECEIVED_CFDI_FILTERS)

    _log_step("Seleccionando empresa 11810 - TIENDAS SORIANA")
    _set_checkbox_by_text(page, "Todas", False, scope_text="EMPRESAS", max_x=650)
    _set_checkbox_by_text(page, "11810 - TIENDAS SORIANA", True, scope_text="EMPRESAS", max_x=650)

    _log_step("Limpiando periodos emitidos")
    _set_period_years(page, section="EMITIDOS", selected_years=set())

    _log_step("Seleccionando periodos recibidos")
    if meses_extra:
        _log_step(f"Margen: agregando mes {'/'.join(f'{a}-{m:02d}' for a, m in sorted(meses_extra))}")
    _set_period_years(page, section="RECIBIDOS", selected_years=selected_years, meses=meses_extra)

    _log_step("Limpiando RFC en emitidos")
    _clear_rfc_fields(page, section="EMITIDOS")

    if rfc:
        _log_step("Llenando RFC en recibidos")
        _fill_rfc_fields(page, rfc, section="RECIBIDOS")

    _log_step(f"Seleccionando archivo {_CPA_DOWNLOAD_FILE_OPTION}")
    _select_only_download_file_options(page, (_CPA_DOWNLOAD_FILE_OPTION, *_CPA_DOWNLOAD_EXTRA_OPTIONS))


def _set_left_filter_options(page, *, section: str, enabled_options: frozenset[str]) -> None:
    for option in _CFDI_FILTER_OPTIONS:
        _set_checkbox_by_text(
            page,
            option,
            option in enabled_options,
            scope_text=section,
            max_x=500,
        )


# Abreviaturas de los meses en la malla de CPA Vision (columna ENE..DIC).
_MESES_ABBR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
# Mes de margen: enero 2026 (para facturas de 2025 emitidas/subidas tarde).
_MES_MARGEN: tuple[int, int] = (2026, 1)


def _set_period_years(
    page, *, section: str, selected_years: set[int], meses: set[tuple[int, int]] = frozenset()
) -> None:
    """Marca los AÑOS completos de `selected_years` y, adicional, celdas de MES sueltas.

    `meses` es un conjunto de `(año, mes)` (mes 1-12) que se marcan a nivel celda, sin marcar
    el año completo. Sirve para el margen (solo enero 2026) sin bajar febrero/marzo.
    """
    for year in range(2014, 2027):
        _set_checkbox_by_text(
            page,
            str(year),
            year in selected_years,
            scope_text=section,
            min_x=250,
            exact=True,
            required=False,
        )
    for year, mes in sorted(meses):
        _set_month_checkbox(page, section=section, year=year, mes=mes, checked=True)


def _set_month_checkbox(page, *, section: str, year: int, mes: int, checked: bool, required: bool = False) -> bool:
    """Marca/desmarca la casilla de UN mes (celda año×mes) en la malla de periodos.

    Ubica la celda geométricamente: cruza la X del encabezado del mes (ENE..DIC) con la Y de
    la etiqueta del año, dentro de la sección (RECIBIDOS/EMITIDOS). No hay texto por celda, por
    eso se hace por posición. Verificar en una corrida real (la malla puede variar de layout)."""
    abbr = _MESES_ABBR[mes - 1]
    result = page.evaluate(
        """
        ({ section, abbr, year, checked }) => {
            const norm = (v) => String(v || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ").trim().toLowerCase();
            const isVisible = (el) => { if (!el) return false; const s = getComputedStyle(el);
                if (s.visibility === "hidden" || s.display === "none") return false;
                const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
            const textOf = (el) => norm(el.innerText || el.textContent || "");
            const wantScope = norm(section), wantAbbr = norm(abbr), wantYear = String(year);

            const texts = Array.from(document.body.querySelectorAll("*")).filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), t: textOf(el) }))
                .filter((it) => it.t && it.t.length <= 60);

            const scopes = texts.filter((it) => it.t.includes(wantScope));
            if (!scopes.length) return { ok: false, message: "No se encontro la seccion " + section };
            const scopeOK = (rect) => scopes.some((s) =>
                s.rect.top <= rect.top + 5 && Math.abs(s.rect.left - rect.left) < 700 && (rect.top - s.rect.top) < 500);

            const monthHdr = texts.filter((it) => it.t === wantAbbr && scopeOK(it.rect))
                .sort((a, b) => a.rect.top - b.rect.top)[0];
            const yearLbl = texts.filter((it) => it.t === wantYear && scopeOK(it.rect))
                .sort((a, b) => a.rect.left - b.rect.left)[0];
            if (!monthHdr || !yearLbl) return { ok: false, message: "No se ubico " + abbr + "/" + year + " en " + section };

            const targetX = monthHdr.rect.left + monthHdr.rect.width / 2;
            const targetY = yearLbl.rect.top + yearLbl.rect.height / 2;

            const boxes = Array.from(document.querySelectorAll("input[type='checkbox']"))
                .filter((i) => !i.disabled && isVisible(i) && scopeOK(i.getBoundingClientRect()));
            let best = null;
            for (const b of boxes) {
                const r = b.getBoundingClientRect();
                const dx = Math.abs(r.left + r.width / 2 - targetX);
                const dy = Math.abs(r.top + r.height / 2 - targetY);
                if (dx > 22 || dy > 14) continue;  // debe caer en la celda mes x año
                const d = dx + dy;
                if (!best || d < best.d) best = { el: b, d };
            }
            if (!best) return { ok: false, message: "No se encontro casilla " + abbr + " " + year + " en " + section };
            best.el.scrollIntoView({ block: "center", inline: "center" });
            if (best.el.checked !== checked) { best.el.click();
                return { ok: true, changed: true, message: "Mes " + abbr + " " + year + " (" + section + ") -> " + checked }; }
            return { ok: true, changed: false, message: "Mes " + abbr + " " + year + " ya estaba en " + checked };
        }
        """,
        {"section": section, "abbr": abbr, "year": year, "checked": checked},
    )
    if not result.get("ok") and required:
        raise RuntimeError(result.get("message") or f"No se encontro el mes {abbr} {year}")
    _log_step(result.get("message", f"mes {abbr} {year}"))
    page.wait_for_timeout(150)
    return bool(result.get("ok"))


def _select_only_download_file_options(page, option_texts: tuple[str, ...]) -> None:
    # The site keeps all file options in a custom checkbox list, so clear the
    # visible download block first and then mark the current requirements.
    result = page.evaluate(
        """
        ({ optionTexts }) => {
            const normalize = (value) => String(value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            const wanted = optionTexts.map(normalize);

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.visibility === "hidden" || style.display === "none") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const textOf = (el) => normalize(el.innerText || el.textContent || "");
            const elements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text);

            const header = elements
                .filter((item) => item.text.includes("archivos a descargar"))
                .sort((a, b) => b.rect.left - a.rect.left)[0];
            if (!header) {
                return { ok: false, message: "No se encontro la seccion ARCHIVOS A DESCARGAR." };
            }

            const nextHeader = elements
                .filter((item) => item.rect.top > header.rect.bottom + 5)
                .filter((item) => ["columnas", "notificacion", "alias"].some((text) => item.text.includes(text)))
                .sort((a, b) => a.rect.top - b.rect.top)[0];

            const sectionTop = header.rect.bottom;
            const sectionBottom = nextHeader ? nextHeader.rect.top : sectionTop + 650;
            const sectionLeft = Math.max(header.rect.left - 20, 850);

            const labelText = (input) => {
                const parts = [];
                if (input.id) {
                    const label = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
                    if (label) parts.push(textOf(label));
                }
                const wrappingLabel = input.closest("label");
                if (wrappingLabel) parts.push(textOf(wrappingLabel));

                const rect = input.getBoundingClientRect();
                const centerY = rect.top + rect.height / 2;
                for (const item of elements) {
                    const itemCenterY = item.rect.top + item.rect.height / 2;
                    const vertical = Math.abs(itemCenterY - centerY);
                    const isNearRight = item.rect.left >= rect.left - 8 && item.rect.left <= rect.left + 520;
                    if (vertical <= 24 && isNearRight && item.text.length <= 260) {
                        parts.push(item.text);
                    }
                }
                return parts.join(" ");
            };

            const checkboxes = Array.from(document.querySelectorAll("input[type='checkbox']"))
                .filter((input) => !input.disabled && isVisible(input))
                .filter((input) => {
                    const rect = input.getBoundingClientRect();
                    return rect.left >= sectionLeft && rect.top > sectionTop && rect.top < sectionBottom;
                });

            let found = false;
            let cleared = 0;
            for (const input of checkboxes) {
                const label = labelText(input);
                const isWanted = wanted.some((text) => label.includes(text));
                found = found || isWanted;
                if (!isWanted && input.checked) {
                    input.scrollIntoView({ block: "center", inline: "center" });
                    input.click();
                    cleared += 1;
                }
            }

            return { ok: true, found, cleared };
        }
        """,
        {"optionTexts": list(option_texts)},
    )
    if not result.get("ok"):
        raise RuntimeError(result.get("message") or "No se encontro la seccion ARCHIVOS A DESCARGAR.")
    if result.get("cleared"):
        _log_step(f"Opciones anteriores de archivos desmarcadas: {result['cleared']}")

    for option_text in option_texts:
        _set_checkbox_by_text(
            page,
            option_text,
            True,
            scope_text="ARCHIVOS A DESCARGAR",
            min_x=900,
        )


def _clear_rfc_fields(page, *, section: str) -> None:
    direct_selector = "#cxp-rfcs" if section.strip().upper() == "RECIBIDOS" else "#cxc-rfcs"
    try:
        field = page.locator(direct_selector).first
        field.wait_for(state="visible", timeout=2_000)
        field.fill("")
        field.evaluate("""(input) => input.dispatchEvent(new Event("change", { bubbles: true }))""")
        _log_step(f"RFC limpiado en {section.lower()} ({direct_selector})")
        return
    except Exception:
        pass

    result = page.evaluate(
        """
        ({ section }) => {
            const normalize = (value) => String(value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            const wantedSection = normalize(section);

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.visibility === "hidden" || style.display === "none") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const textOf = (el) => normalize(el.innerText || el.textContent || "");
            const textElements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text && item.text.length <= 120);

            const sectionScore = (input) => {
                if (!wantedSection) return 0;
                const rect = input.getBoundingClientRect();
                let bestDistance = null;
                for (const item of textElements) {
                    if (!item.text.includes(wantedSection)) continue;
                    if (item.rect.left < 600) continue;
                    if (item.rect.top > rect.top + 5) continue;
                    const horizontalGap = Math.max(item.rect.left - rect.right, rect.left - item.rect.right, 0);
                    if (horizontalGap > 700) continue;
                    const verticalGap = rect.top - item.rect.top;
                    if (verticalGap > 500) continue;
                    const distance = verticalGap + horizontalGap / 4;
                    if (bestDistance === null || distance < bestDistance) {
                        bestDistance = distance;
                    }
                }
                return bestDistance;
            };

            const inputs = Array.from(document.querySelectorAll("input"))
                .filter((input) => !input.disabled && isVisible(input))
                .filter((input) => {
                    const type = normalize(input.getAttribute("type") || "text");
                    return ["", "text", "search"].includes(type);
                });

            let cleared = 0;
            for (const input of inputs) {
                const attrs = normalize([
                    input.name,
                    input.id,
                    input.getAttribute("aria-label"),
                    input.getAttribute("placeholder"),
                ].join(" "));
                if (!attrs.includes("rfc")) continue;
                const scope = sectionScore(input);
                if (wantedSection && scope === null) continue;
                input.scrollIntoView({ block: "center", inline: "center" });
                input.focus();
                input.value = "";
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                cleared += 1;
            }
            return cleared;
        }
        """,
        {"section": section},
    )
    _log_step(f"RFC limpiado en {result} casilla(s) de {section.lower()}")


def _fill_rfc_fields(page, rfc: str, *, section: str = "RECIBIDOS") -> None:
    direct_selector = "#cxp-rfcs" if section.strip().upper() == "RECIBIDOS" else "#cxc-rfcs"
    try:
        field = page.locator(direct_selector).first
        field.wait_for(state="visible", timeout=5_000)
        field.fill(rfc)
        field.evaluate("""(input) => input.dispatchEvent(new Event("change", { bubbles: true }))""")
        _log_step(f"RFC capturado en {section.lower()} ({direct_selector})")
        return
    except Exception:
        pass

    result = page.evaluate(
        """
        ({ rfc, section }) => {
            const normalize = (value) => String(value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            const wantedSection = normalize(section);

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.visibility === "hidden" || style.display === "none") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const textOf = (el) => normalize(el.innerText || el.textContent || "");
            const textElements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text && item.text.length <= 120);

            const sectionScore = (input) => {
                if (!wantedSection) return 0;
                const rect = input.getBoundingClientRect();
                let bestDistance = null;
                for (const item of textElements) {
                    if (!item.text.includes(wantedSection)) continue;
                    if (item.rect.left < 600) continue;
                    if (item.rect.top > rect.top + 5) continue;
                    const horizontalGap = Math.max(item.rect.left - rect.right, rect.left - item.rect.right, 0);
                    if (horizontalGap > 700) continue;
                    const verticalGap = rect.top - item.rect.top;
                    if (verticalGap > 500) continue;
                    const distance = verticalGap + horizontalGap / 4;
                    if (bestDistance === null || distance < bestDistance) {
                        bestDistance = distance;
                    }
                }
                return bestDistance;
            };

            const inputs = Array.from(document.querySelectorAll("input"))
                .filter((input) => !input.disabled && isVisible(input))
                .filter((input) => {
                    const type = normalize(input.getAttribute("type") || "text");
                    return ["", "text", "search"].includes(type);
                });

            const matches = [];
            for (const input of inputs) {
                const rect = input.getBoundingClientRect();
                const attrs = normalize([
                    input.name,
                    input.id,
                    input.getAttribute("aria-label"),
                    input.getAttribute("placeholder"),
                ].join(" "));
                let isRfc = attrs.includes("rfc");
                if (!isRfc) {
                    for (const item of textElements) {
                        if (!item.text.includes("rfc")) continue;
                        const vertical = Math.abs((item.rect.top + item.rect.height / 2) - (rect.top + rect.height / 2));
                        const isLeftLabel = item.rect.right <= rect.left + 4 && rect.left - item.rect.right <= 90;
                        if (vertical <= 24 && isLeftLabel) {
                            isRfc = true;
                            break;
                        }
                    }
                }
                if (!isRfc) continue;
                const scope = sectionScore(input);
                if (wantedSection && scope === null) continue;
                matches.push({ input, score: scope || 0 });
            }

            matches.sort((a, b) => a.score - b.score);
            for (const { input } of matches) {
                input.scrollIntoView({ block: "center", inline: "center" });
                input.focus();
                input.value = rfc;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
            }
            return matches.length;
        }
        """,
        {"rfc": rfc, "section": section},
    )
    if result < 1:
        raise RuntimeError(f"No se lleno la casilla RFC de {section}. Casillas encontradas: {result}.")
    _log_step(f"RFC capturado en {result} casilla(s) de {section.lower()}")


def _submit_download_request(page, timeout_ms: int) -> str:
    _log_step("Dando clic en Solicitar descarga")
    _click_first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile("solicitar descarga", re.IGNORECASE)),
            lambda: page.get_by_text(re.compile("solicitar descarga", re.IGNORECASE)),
        ],
        "Solicitar descarga",
    )

    _log_step("Esperando confirmacion de solicitud")
    _wait_for_request_confirmation(page, timeout_ms)
    request_id = _extract_request_id(page)
    _log_step(f"Solicitud creada: {request_id}")

    _set_request_reason_and_frequency(page)

    _log_step("Confirmando motivo y frecuencia")
    _click_first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile("aceptar", re.IGNORECASE)),
            lambda: page.get_by_text(re.compile("aceptar", re.IGNORECASE)),
        ],
        "Aceptar",
    )
    page.wait_for_timeout(1_000)
    return request_id


def _set_request_reason_and_frequency(page) -> None:
    _log_step("Seleccionando Motivo: Conciliacion")
    _set_input_checked_by_selector(page, "#requerimiento", False, "Motivo Requerimiento")
    _set_input_checked_by_selector(page, "#conciliacion", True, "Motivo Conciliacion")
    _set_input_checked_by_selector(page, "#baseDeDatos", False, "Motivo Base de datos")
    _set_input_checked_by_selector(page, "#dashboard", False, "Motivo Dashboard")
    _set_input_checked_by_selector(page, "#reportesInternos", False, "Motivo Reportes internos")

    _log_step("Seleccionando Frecuencia: Unica vez")
    _set_input_checked_by_selector(page, "#unicaVez", True, "Frecuencia Unica vez")


def _set_input_checked_by_selector(page, selector: str, checked: bool, description: str) -> None:
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=5_000)
    if checked:
        locator.check(force=True, timeout=5_000)
    elif locator.is_checked():
        locator.uncheck(force=True, timeout=5_000)
    page.wait_for_timeout(150)
    if locator.is_checked() != checked:
        raise RuntimeError(f"La opcion no quedo en el estado requerido: {description}.")
    _log_step(f"Verificado: {description}")


def _wait_for_request_confirmation(page, timeout_ms: int) -> None:
    page.wait_for_function(
        """
        () => {
            const text = document.body.innerText || "";
            return /ID:\\s*\\d+/i.test(text)
                && /motivo/i.test(text)
                && /frecuencia/i.test(text);
        }
        """,
        timeout=timeout_ms,
    )


def _extract_request_id(page) -> str:
    body_text = page.locator("body").inner_text(timeout=10_000)
    match = re.search(r"ID:\s*(\d+)", body_text, re.IGNORECASE)
    if not match:
        raise RuntimeError("No se pudo leer el ID de la solicitud realizada.")
    return match.group(1)


def _reauth_solicitudes(page, settings: CPAVisionSettings, username: str, password: str) -> None:
    """Cierra la sesión lógica (navega a login), vuelve a iniciar sesión y reabre solicitudes.

    Se usa tanto para recuperación reactiva (redirección/logout) como para el refresco
    preventivo cada N intentos. No cierra el navegador para no invalidar el `page` que el
    llamador sigue usando después de descargar; el efecto es una sesión fresca sobre la
    misma página.

    Reproduce el mismo orden que el arranque de sesión: login → seleccionar empresa SORIANA
    y entrar a "Descargas" (`_open_descargas`) → abrir "Solicitudes". Saltarse
    `_open_descargas` dejaba la sesión atascada en la pantalla "SELECCIONAR EMPRESA", donde
    el botón "Solicitudes" no existe y la tabla nunca cargaba.
    """
    page.goto(settings.base_url, wait_until="domcontentloaded")
    _dismiss_transient_overlays(page)
    if not _is_empresa_or_downloads_page(page):
        _login(page, username, password, settings.timeout_ms)
    _open_descargas(page, settings.timeout_ms)
    _open_solicitudes(page)


def _en_area_descargas(page) -> bool:
    """True si la URL está dentro de Descarga masiva (descargas o solicitudes).

    A diferencia de `_is_empresa_or_downloads_page`, la pantalla "SELECCIONAR EMPRESA"
    (okta/empresas) NO cuenta como "dentro": desde ahí no se ve la tabla de solicitudes y
    hay que volver a entrar a la empresa.
    """
    try:
        return bool(re.search(r"descarga-masiva", page.url, re.IGNORECASE))
    except Exception:
        return False


def _regenerar_solicitud(page, settings: CPAVisionSettings, rfc: str, years) -> str:
    """Crea una solicitud nueva para el mismo RFC cuando la anterior nunca apareció.

    Vuelve al formulario de Descarga masiva, reconfigura RFC/años y solicita de nuevo.
    Devuelve el nuevo request_id. La deduplicación por `request_id` del dataset Parquet
    (ver `cruce_cpa.request_id_principal`) se encarga de que, si por algún motivo llegaran
    a existir dos descargas del mismo RFC, solo se use la más completa.
    """
    _return_to_downloads_form(page, settings.timeout_ms)
    _configure_default_download_options(page, rfc=rfc, years=years)
    return _submit_download_request(page, settings.timeout_ms)


def _request_id_from_zip(path) -> str:
    """request_id a partir del nombre del ZIP descargado (p. ej. `645989_1873_...zip`)."""
    try:
        return Path(path).name.split("_", 1)[0].strip()
    except Exception:
        return ""


def _wait_for_request_zip(
    page,
    request_id: str,
    download_dir: Path,
    *,
    poll_seconds: int,
    max_wait_minutes: int,
    settings: CPAVisionSettings | None = None,
    username: str | None = None,
    password: str | None = None,
    reauth_every_attempts: int = 60,
    rfc: str | None = None,
    years: Any = None,
    regenerate_after_missing: int = 30,
) -> Path:
    _open_solicitudes(page)
    deadline = time.monotonic() + max_wait_minutes * 60
    puede_reautenticar = bool(username and password and settings)
    # Solo se puede regenerar si sabemos el RFC y los años (los trae el lote, no el flujo
    # de "esperar una solicitud existente").
    puede_regenerar = bool(rfc and years is not None and settings and regenerate_after_missing > 0)
    missing_streak = 0
    attempt = 1
    while True:
        # Refresco preventivo: aunque todo vaya bien, cada `reauth_every_attempts` intentos
        # reiniciamos la sesión (login de nuevo) y volvemos a solicitudes. Evita sesiones
        # de horas que el portal pueda invalidar silenciosamente sin redirigir.
        if (
            puede_reautenticar
            and reauth_every_attempts > 0
            and attempt > 1
            and (attempt - 1) % reauth_every_attempts == 0
        ):
            _log_step(
                f"Intento {attempt}: refresco preventivo de sesion "
                f"(cada {reauth_every_attempts} intentos). Reiniciando sesion..."
            )
            try:
                _reauth_solicitudes(page, settings, username, password)
            except Exception as e:
                _log_step(f"Fallo el refresco preventivo de sesion: {e}")
                # No lanzamos error: el reload() normal más abajo hará otro intento.

        # Validación proactiva de sesión activa.
        # Si ya NO estamos dentro de Descarga masiva (nos regresó a "SELECCIONAR EMPRESA" o
        # a login/okta), hay que re-entrar: _reauth_solicitudes reinicia sesión, selecciona
        # la empresa y abre Solicitudes. Antes se usaba _is_empresa_or_downloads_page, que
        # tomaba la pantalla de empresas como válida y dejaba el flujo atascado ahí.
        if puede_reautenticar and not _en_area_descargas(page):
            _log_step("Fuera del área de descargas (empresas/logout) durante la espera. Recuperando sesion...")
            try:
                _reauth_solicitudes(page, settings, username, password)
            except Exception as e:
                _log_step(f"Fallo el intento de recuperacion de sesion: {e}")
                # No lanzamos error aquí para permitir que el flujo normal intente el reload()

        _log_step(f"Validando solicitud {request_id}. Intento {attempt}")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1_000)
        _dismiss_transient_overlays(page)
        row = _find_request_row(page, request_id, timeout_ms=30_000)
        if row is None:
            missing_streak += 1
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"No se encontro la solicitud {request_id} en {max_wait_minutes} minutos."
                )
            # La solicitud nunca apareció en la tabla tras muchos intentos: lo más probable
            # es que el envío se haya perdido del lado del portal. Se regenera una solicitud
            # nueva para el mismo RFC y se sigue esperando con ese nuevo id (idea de Óscar).
            if puede_regenerar and missing_streak >= regenerate_after_missing:
                _log_step(
                    f"La solicitud {request_id} no aparece tras {missing_streak} intentos. "
                    f"Regenerando solicitud para {rfc}..."
                )
                try:
                    request_id = _regenerar_solicitud(page, settings, rfc, years)
                    _log_step(f"Nueva solicitud creada: {request_id}. Reiniciando espera.")
                    missing_streak = 0
                    _open_solicitudes(page)
                except Exception as regen_exc:
                    _log_step(f"No se pudo regenerar la solicitud: {regen_exc}")
            else:
                _log_step(
                    f"La solicitud {request_id} aun no aparece en la tabla "
                    f"({missing_streak} intento(s)). Esperando {poll_seconds} segundos"
                )
            page.wait_for_timeout(poll_seconds * 1_000)
            attempt += 1
            continue

        # La solicitud apareció: reiniciamos el contador de "no aparece".
        missing_streak = 0

        ready_link = _first_ready_request_link(row)
        if ready_link is not None:
            _log_step("Solicitud lista. Abriendo enlaces")
            return _download_from_request_link(page, ready_link, download_dir, request_id)

        status = _request_row_status(row)
        if status:
            _log_step(f"Solicitud {request_id} aun sin link. Estado actual: {status}")

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"La solicitud {request_id} no estuvo lista en {max_wait_minutes} minutos."
            )

        _log_step(f"Aun no esta lista. Esperando {poll_seconds} segundos")
        page.wait_for_timeout(poll_seconds * 1_000)
        attempt += 1


def _load_vendor_master_jobs(vendor_master_path: Path | str) -> list[CPAVisionBatchJob]:
    path = Path(vendor_master_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo vendor master: {path}")

    df = pd.read_excel(path, dtype=str).fillna("")
    normalized_columns = {str(column).strip().upper(): column for column in df.columns}
    if "RFC" not in normalized_columns or "FECHAS" not in normalized_columns:
        raise ValueError("El Excel debe tener las columnas RFC y FECHAS.")

    rfc_column = normalized_columns["RFC"]
    fechas_column = normalized_columns["FECHAS"]
    jobs: list[CPAVisionBatchJob] = []
    for row_index, row in df.iterrows():
        rfc = str(row[rfc_column]).strip().upper()
        fechas = str(row[fechas_column]).strip()
        if not rfc and not fechas:
            continue
        if not rfc:
            raise ValueError(f"Fila {row_index + 2}: RFC vacio.")
        years = _parse_years(fechas)
        jobs.append(
            CPAVisionBatchJob(
                source_index=row_index + 2,
                rfc=rfc,
                fechas=fechas,
                years=years,
            )
        )
    return jobs


def _parse_years(value: str) -> tuple[int, ...]:
    text = str(value).strip()
    if not text:
        raise ValueError("FECHAS esta vacio.")

    compact = re.sub(r"\s+", "", text)
    range_match = re.fullmatch(r"(\d{4})-(\d{4})", compact)
    if range_match:
        start_year = int(range_match.group(1))
        end_year = int(range_match.group(2))
        if start_year > end_year:
            raise ValueError(f"Rango de FECHAS invalido: {text}")
        return _validate_years(range(start_year, end_year + 1), text)

    years = [int(match) for match in re.findall(r"\d{4}", compact)]
    if years:
        return _validate_years(years, text)
    raise ValueError(f"No se pudo interpretar FECHAS: {text}")


def _validate_years(years: Any, source: str) -> tuple[int, ...]:
    unique_years = tuple(sorted(set(int(year) for year in years)))
    unsupported = [year for year in unique_years if year < 2014 or year > 2026]
    if unsupported:
        raise ValueError(f"FECHAS contiene anos fuera de CPA Vision ({source}): {unsupported}")
    return unique_years


def _resumen_batch(metrics_path: Path) -> None:
    """Imprime un resumen de tiempos al final del lote (lee el CSV de metricas)."""
    import csv as _csv
    if not metrics_path.exists():
        return
    with metrics_path.open(encoding="utf-8-sig") as _h:
        filas = list(_csv.DictReader(_h))
    if not filas:
        return
    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    ok = [r for r in filas if r.get("status") == "downloaded"]
    err = [r for r in filas if r.get("status") != "downloaded"]
    total_seg = sum(_num(r.get("elapsed_seconds")) for r in filas)
    total_filas = sum(int(_num(r.get("parquet_rows"))) for r in filas)
    prom = total_seg / len(filas) if filas else 0.0
    def _fmt(seg):
        seg = int(seg); h, resto = divmod(seg, 3600); m, s = divmod(resto, 60)
        return f"{h}h {m}m {s}s"
    print("", flush=True)
    print("==================== RESUMEN DE LA EJECUCION ====================", flush=True)
    print(f"  Proveedores procesados : {len(filas)}  (OK: {len(ok)}  |  con error: {len(err)})", flush=True)
    print(f"  Tiempo total           : {_fmt(total_seg)}  ({total_seg:,.0f} s)", flush=True)
    print(f"  Promedio por proveedor : {_fmt(prom)}", flush=True)
    print(f"  Filas descargadas      : {total_filas:,}", flush=True)
    if err:
        print(f"  Con error (revisar)    : {', '.join(r.get('rfc','?') for r in err)}", flush=True)
    print("================================================================", flush=True)


def _default_batch_metrics_path(download_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return download_dir / f"cpa_batch_metrics_{timestamp}.csv"


def _build_batch_metric(
    job: CPAVisionBatchJob,
    batch_position: int,
    started_at: datetime,
    started_monotonic: float,
    *,
    request_id: str,
    output_path: Path | None,
    parquet_root: Path,
    parquet_rows: int,
    parquet_files: int,
    status: str,
    error: str,
) -> dict[str, str]:
    finished_at = datetime.now()
    elapsed_seconds = time.monotonic() - started_monotonic
    return {
        "batch_position": str(batch_position),
        "excel_row": str(job.source_index),
        "rfc": job.rfc,
        "fechas": job.fechas,
        "years": ",".join(str(year) for year in job.years),
        "request_id": request_id,
        "status": status,
        "zip_path": str(output_path or ""),
        "parquet_root": str(parquet_root),
        "parquet_files": str(parquet_files),
        "parquet_rows": str(parquet_rows),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "elapsed_seconds": f"{elapsed_seconds:.2f}",
        "error": error,
    }


def _append_batch_metric(metrics_path: Path, row: dict[str, str]) -> None:
    ensure_parent(metrics_path)
    fieldnames = [
        "batch_position",
        "excel_row",
        "rfc",
        "fechas",
        "years",
        "request_id",
        "status",
        "zip_path",
        "parquet_root",
        "parquet_files",
        "parquet_rows",
        "started_at",
        "finished_at",
        "elapsed_seconds",
        "error",
    ]
    write_header = not metrics_path.exists()
    with metrics_path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _find_request_row(page, request_id: str, timeout_ms: int):
    deadline = time.monotonic() + timeout_ms / 1_000
    xpath = f"//table[@id='myTableSolicitudes']//tbody/tr[normalize-space(td[1])='{request_id}']"
    fallback_xpath = f"//tr[normalize-space(td[1])='{request_id}']"

    while time.monotonic() < deadline:
        try:
            page.locator("#myTableSolicitudes").wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(500)
            continue

        for selector in (f"xpath={xpath}", f"xpath={fallback_xpath}"):
            row = page.locator(selector).first
            try:
                row.wait_for(state="visible", timeout=1_500)
                _log_step(f"Solicitud {request_id} encontrada en la tabla")
                return row
            except PlaywrightTimeoutError:
                continue

        visible_ids = _visible_request_ids(page)
        if visible_ids:
            _log_step(f"IDs visibles en tabla: {', '.join(visible_ids[:8])}")
        page.wait_for_timeout(1_000)
    return None


def _visible_request_ids(page) -> list[str]:
    try:
        ids = page.locator("#myTableSolicitudes tbody tr td:first-child").all_inner_texts()
    except Exception:
        return []
    return [item.strip() for item in ids if item.strip()]


def _request_row_status(row) -> str:
    try:
        cells = [cell.inner_text(timeout=1_000).strip() for cell in row.locator("td").all()]
    except Exception:
        return ""
    if len(cells) >= 6:
        return cells[5]
    return " | ".join(cells)


def _open_solicitudes(page) -> None:
    _log_step("Abriendo Solicitudes")
    _click_first_visible(
        page,
        [
            lambda: page.get_by_role("button", name=re.compile("solicitudes", re.IGNORECASE)),
            lambda: page.get_by_text(re.compile("solicitudes", re.IGNORECASE)),
        ],
        "Solicitudes",
    )
    try:
        page.get_by_text(re.compile("estatus de descargas", re.IGNORECASE)).wait_for(timeout=20_000)
    except Exception:
        page.locator("table").first.wait_for(timeout=20_000)
    _dismiss_transient_overlays(page)


def _return_to_downloads_form(page, timeout_ms: int) -> None:
    _dismiss_transient_overlays(page)
    _close_visible_modal(page)
    if re.search(r"descarga-masiva/descargas", page.url, re.IGNORECASE):
        page.get_by_text(re.compile("descarga masiva de archivos", re.IGNORECASE)).wait_for(timeout=timeout_ms)
        _dismiss_transient_overlays(page)
        return

    _log_step("Regresando al formulario de Descarga masiva")
    try:
        _click_first_visible(
            page,
            [
                lambda: page.get_by_role("button", name=re.compile("regresar", re.IGNORECASE)),
                lambda: page.locator("button").filter(has_text=re.compile("regresar", re.IGNORECASE)),
                lambda: page.get_by_text(re.compile(r"^\s*regresar\s*$", re.IGNORECASE)),
            ],
            "Regresar",
        )
        page.wait_for_url(re.compile(r".*descarga-masiva/descargas.*"), timeout=timeout_ms)
    except Exception:
        page.goto(_downloads_url_from_current_page(page), wait_until="domcontentloaded")
    page.get_by_text(re.compile("descarga masiva de archivos", re.IGNORECASE)).wait_for(timeout=timeout_ms)
    _dismiss_transient_overlays(page)


def _downloads_url_from_current_page(page) -> str:
    match = re.match(r"^(https?://[^/]+)", page.url)
    if not match:
        return "https://facreview.cpavision.mx/descarga-masiva/descargas"
    return f"{match.group(1)}/descarga-masiva/descargas"


def _close_visible_modal(page) -> bool:
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass

    result = page.evaluate(
        """
        () => {
            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.visibility === "hidden" || style.display === "none") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const closeTerms = /(cerrar|close|dismiss|times|remove|cancel|x)/i;
            const modalCandidates = Array.from(document.querySelectorAll(
                ".modal, .modal-dialog, [role='dialog'], .swal2-popup, .mat-dialog-container"
            )).filter(isVisible);
            if (!modalCandidates[0]) return false;
            const root = modalCandidates[0];
            const buttons = Array.from(root.querySelectorAll("button, a, [role='button'], span, i"))
                .filter(isVisible)
                .map((el) => {
                    const rect = el.getBoundingClientRect();
                    const attrs = [
                        el.innerText,
                        el.textContent,
                        el.getAttribute("aria-label"),
                        el.getAttribute("title"),
                        el.getAttribute("class"),
                        el.id,
                    ].join(" ");
                    return { el, rect, attrs };
                })
                .filter((item) => closeTerms.test(item.attrs) || String(item.attrs || "").includes("×"))
                .sort((a, b) => (a.rect.top - b.rect.top) || (b.rect.right - a.rect.right));
            if (!buttons[0]) return false;
            buttons[0].el.click();
            return true;
        }
        """
    )
    if result:
        _log_step("Modal visible cerrado")
        page.wait_for_timeout(300)
    return bool(result)


def _first_ready_request_link(row):
    links = row.locator("a")
    for idx in range(links.count()):
        link = links.nth(idx)
        try:
            text = link.inner_text(timeout=1_000).strip()
        except Exception:
            continue
        if text and text != "-" and re.search(r"ver links|\.zip|zip", text, re.IGNORECASE):
            return link
    return None


def _download_from_request_link(page, link, download_dir: Path, request_id: str) -> Path:
    link_text = ""
    try:
        link_text = link.inner_text(timeout=1_000).strip()
    except Exception:
        pass

    if re.search(r"\.zip|zip", link_text, re.IGNORECASE):
        with page.expect_download(timeout=60_000) as download_info:
            link.click()
        return _save_download_object(download_info.value, download_dir)

    link.click()
    _log_step("Esperando link ZIP en modal de solicitud")
    zip_link = page.locator(
        f"xpath=//a[contains(normalize-space(.), '.zip') and contains(normalize-space(.), '{request_id}')]"
    ).first
    try:
        zip_link.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeoutError:
        zip_link = page.locator("a").filter(has_text=re.compile(r"\.zip|zip", re.IGNORECASE)).first
    zip_link.wait_for(state="visible", timeout=30_000)
    with page.expect_download(timeout=60_000) as download_info:
        zip_link.click()
    return _save_download_object(download_info.value, download_dir)


def _set_checkbox_by_text(
    page,
    text: str,
    checked: bool,
    *,
    scope_text: str | None = None,
    min_x: int | None = None,
    max_x: int | None = None,
    exact: bool = False,
    required: bool = True,
) -> bool:
    result = page.evaluate(
        """
        ({ text, checked, scopeText, minX, maxX, exact }) => {
            const normalize = (value) => String(value || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            const wanted = normalize(text);
            const wantedScope = scopeText ? normalize(scopeText) : "";

            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.visibility === "hidden" || style.display === "none") return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const textOf = (el) => normalize(el.innerText || el.textContent || "");
            const bodyElements = Array.from(document.body.querySelectorAll("*")).filter(isVisible);
            const textElements = bodyElements
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text && item.text.length <= 220);

            const matchesText = (value) => exact ? value === wanted : value.includes(wanted);

            const labelText = (input) => {
                const parts = [];
                if (input.id) {
                    const label = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
                    if (label) parts.push(textOf(label));
                }
                const wrappingLabel = input.closest("label");
                if (wrappingLabel) parts.push(textOf(wrappingLabel));
                return parts.join(" ");
            };

            const nearbyTargetScore = (input) => {
                const rect = input.getBoundingClientRect();
                const centerY = rect.top + rect.height / 2;
                const centerX = rect.left + rect.width / 2;
                let best = null;

                const associated = labelText(input);
                if (associated && matchesText(associated)) {
                    best = { distance: 0, source: associated };
                }

                for (const item of textElements) {
                    if (!matchesText(item.text)) continue;
                    const itemCenterY = item.rect.top + item.rect.height / 2;
                    const vertical = Math.abs(itemCenterY - centerY);
                    const horizontal = Math.abs(item.rect.left - centerX);
                    const isSameRow = vertical <= 24;
                    const isNearRight = item.rect.left >= rect.left - 8 && item.rect.left <= rect.left + 320;
                    const isNearLeft = item.rect.right >= rect.left - 80 && item.rect.right <= rect.right + 12;
                    if (!isSameRow || (!isNearRight && !isNearLeft)) continue;
                    const distance = vertical + horizontal / 25;
                    if (!best || distance < best.distance) {
                        best = { distance, source: item.text };
                    }
                }
                return best;
            };

            const scopeScore = (input) => {
                if (!wantedScope) return 0;
                const rect = input.getBoundingClientRect();
                let bestDistance = null;
                for (const item of textElements) {
                    if (!item.text.includes(wantedScope)) continue;
                    if (item.rect.top > rect.top + 5) continue;
                    const horizontalGap = Math.max(item.rect.left - rect.right, rect.left - item.rect.right, 0);
                    if (horizontalGap > 450) continue;
                    const distance = (rect.top - item.rect.top) + horizontalGap / 4;
                    if (bestDistance === null || distance < bestDistance) {
                        bestDistance = distance;
                    }
                }
                return bestDistance;
            };

            const inputs = Array.from(document.querySelectorAll("input[type='checkbox']"))
                .filter((input) => !input.disabled && isVisible(input));

            const candidates = [];
            for (const input of inputs) {
                const rect = input.getBoundingClientRect();
                if (minX !== null && minX !== undefined && rect.left < minX) continue;
                if (maxX !== null && maxX !== undefined && rect.left > maxX) continue;

                const target = nearbyTargetScore(input);
                if (!target) continue;
                const scope = scopeScore(input);
                if (wantedScope && scope === null) continue;

                candidates.push({
                    input,
                    score: target.distance + (scope || 0) / 100,
                    rect,
                    targetText: target.source,
                });
            }

            candidates.sort((a, b) => a.score - b.score);
            const selected = candidates[0];
            if (!selected) {
                return { ok: false, changed: false, message: `No se encontro checkbox: ${text}` };
            }

            selected.input.scrollIntoView({ block: "center", inline: "center" });
            if (selected.input.checked !== checked) {
                selected.input.click();
                return {
                    ok: true,
                    changed: true,
                    checked: selected.input.checked,
                    message: `Checkbox actualizado: ${text}`,
                };
            }
            return {
                ok: true,
                changed: false,
                checked: selected.input.checked,
                message: `Checkbox ya estaba en el estado requerido: ${text}`,
            };
        }
        """,
        {
            "text": text,
            "checked": checked,
            "scopeText": scope_text,
            "minX": min_x,
            "maxX": max_x,
            "exact": exact,
        },
    )
    if not result.get("ok") and required:
        raise RuntimeError(result.get("message") or f"No se encontro checkbox: {text}")
    if result.get("ok"):
        _log_step(result.get("message", text))
        page.wait_for_timeout(150)
    elif not required:
        _log_step(f"Omitido: {result.get('message', text)}")
    return bool(result.get("ok"))


def _select_facreview_if_present(page) -> None:
    selects = page.locator("select")
    if selects.count() == 0:
        return
    try:
        selects.first.select_option(label="FacReview")
    except Exception:
        return


def _fill_first_visible(page, locator_factories, value: str, description: str) -> None:
    for factory in locator_factories:
        try:
            locator = factory().first
            locator.wait_for(state="visible", timeout=5_000)
            locator.fill(value)
            return
        except Exception:
            continue
    raise RuntimeError(f"No se encontro el campo requerido en CPA Vision: {description}.")


def _click_first_visible(page, locator_factories, description: str) -> None:
    for factory in locator_factories:
        try:
            locator = factory().first
            locator.wait_for(state="visible", timeout=5_000)
            locator.click()
            return
        except Exception:
            continue
    raise RuntimeError(f"No se encontro el boton/opcion requerida en CPA Vision: {description}.")


def _is_empresa_or_downloads_page(page) -> bool:
    current_url = page.url.lower()
    return "okta/empresas" in current_url or "descarga-masiva" in current_url


def _log_step(message: str) -> None:
    print(f"[CPA Vision] {message}", flush=True)


def _save_debug_artifacts(page, name: str) -> None:
    try:
        screenshot_path = config.LOG_DIR / f"{name}.png"
        html_path = config.LOG_DIR / f"{name}.html"
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        print(f"[CPA Vision] Captura de error: {screenshot_path}", flush=True)
        print(f"[CPA Vision] HTML de error: {html_path}", flush=True)
    except Exception:
        return


def list_downloaded_csvs(download_dir: Path | str | None = None) -> list[Path]:
    folder = Path(download_dir) if download_dir else config.CPA_VISION_DOWNLOAD_DIR
    if not folder.exists():
        return []
    return sorted(folder.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)


def _save_download(download, download_dir: Path, downloaded_files: list[Path]) -> None:
    target = _save_download_object(download, download_dir)
    downloaded_files.append(target)
    print(f"Descarga guardada: {target}")


def _save_download_object(download, download_dir: Path) -> Path:
    filename = safe_filename(download.suggested_filename or "descarga.zip")
    target = _unique_path(download_dir / filename)
    download.save_as(target)
    return target


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _require_playwright() -> None:
    if sync_playwright is None:
        raise RuntimeError(
            "Playwright no esta instalado. Ejecuta: python -m pip install -r requirements.txt "
            "y luego: python -m playwright install chromium"
        )


def actualizar_metricas_totales(download_dir: Path) -> Path:
    """Consolida TODOS los cpa_batch_metrics_*.csv y actualiza METRICAS_TOTALES.txt/.csv.

    Se llama solo al terminar cada lote: junta lo nuevo con lo previo y reescribe la metrica
    acumulada (proveedores unicos OK, tiempo total, promedio por proveedor, filas).
    """
    import csv as _csv
    import glob as _glob

    download_dir = Path(download_dir)
    archivos = sorted(_glob.glob(str(download_dir / "cpa_batch_metrics_*.csv")))
    filas = []
    for a in archivos:
        with open(a, encoding="utf-8-sig") as h:
            filas.extend(_csv.DictReader(h))

    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0

    def _fmt(seg):
        seg = int(seg)
        h, resto = divmod(seg, 3600)
        m, s = divmod(resto, 60)
        return f"{h}h {m}m {s}s"

    ok = [r for r in filas if r.get("status") == "downloaded"]
    err = [r for r in filas if r.get("status") != "downloaded"]
    unicos = {r.get("rfc"): r for r in ok}
    total_seg = sum(_num(r.get("elapsed_seconds")) for r in filas)
    seg_u = sum(_num(r.get("elapsed_seconds")) for r in unicos.values())
    total_filas = sum(int(_num(r.get("parquet_rows"))) for r in unicos.values())
    prom = seg_u / len(unicos) if unicos else 0.0

    cols = ["rfc", "fechas", "years", "request_id", "status", "parquet_rows",
            "elapsed_seconds", "finished_at"]
    csv_out = download_dir / "METRICAS_TOTALES.csv"
    with csv_out.open("w", newline="", encoding="utf-8-sig") as h:
        w = _csv.DictWriter(h, fieldnames=cols)
        w.writeheader()
        for r in unicos.values():
            w.writerow({c: r.get(c, "") for c in cols})

    lineas = [
        "METRICA TOTAL DE DESCARGAS (CPA Vision)",
        f"Actualizado          : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Archivos de metricas : {len(archivos)}",
        f"Intentos totales     : {len(filas)}  (OK: {len(ok)} | error: {len(err)})",
        f"Proveedores unicos OK: {len(unicos)}",
        f"Tiempo total (todo)  : {_fmt(total_seg)}  ({total_seg:,.0f} s)",
        f"Promedio x proveedor : {_fmt(prom)}",
        f"Filas descargadas    : {total_filas:,}",
    ]
    txt_out = download_dir / "METRICAS_TOTALES.txt"
    txt_out.write_text(chr(10).join(lineas) + chr(10), encoding="utf-8")
    print("", flush=True)
    for l in lineas:
        print("  " + l, flush=True)
    print(f"  Metricas acumuladas  -> {txt_out}", flush=True)
    return txt_out
