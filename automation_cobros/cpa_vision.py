from __future__ import annotations

from dataclasses import dataclass
import getpass
from pathlib import Path
import re
import time
from typing import Any

import pandas as pd

import config
from automation_cobros.utils import ensure_parent, safe_filename

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - handled at runtime with a clear message.
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


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
        context_kwargs: dict[str, Any] = {"accept_downloads": True}
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
        context_kwargs: dict[str, Any] = {"accept_downloads": True}
        if settings.state_path.exists():
            _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()

        try:
            _log_step(f"Abriendo CPA Vision: {settings.base_url}")
            page.goto(settings.base_url, wait_until="domcontentloaded")
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
    max_wait_minutes: int = 30,
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
        context_kwargs: dict[str, Any] = {"accept_downloads": True}
        if settings.state_path.exists():
            _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()

        try:
            _log_step(f"Abriendo CPA Vision: {settings.base_url}")
            page.goto(settings.base_url, wait_until="domcontentloaded")
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


def wait_for_existing_request_download(
    settings: CPAVisionSettings | None = None,
    *,
    request_id: str,
    username: str | None = None,
    password: str | None = None,
    poll_seconds: int = 20,
    max_wait_minutes: int = 30,
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
        context_kwargs: dict[str, Any] = {"accept_downloads": True}
        if settings.state_path.exists():
            _log_step(f"Reutilizando sesion guardada: {settings.state_path}")
            context_kwargs["storage_state"] = str(settings.state_path)
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()

        try:
            _log_step(f"Abriendo CPA Vision: {settings.base_url}")
            page.goto(settings.base_url, wait_until="domcontentloaded")
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


def _launch_browser(playwright, settings: CPAVisionSettings):
    launch_kwargs: dict[str, Any] = {
        "headless": settings.headless,
        "slow_mo": settings.slow_mo_ms,
    }
    if settings.browser_channel:
        launch_kwargs["channel"] = settings.browser_channel
    return playwright.chromium.launch(**launch_kwargs)


def _open_descargas(page, timeout_ms: int) -> None:
    if re.search(r"descarga-masiva/descargas", page.url, re.IGNORECASE):
        _log_step("Ya estas en Descarga masiva")
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


def _configure_default_download_options(
    page,
    *,
    rfc: str | None = None,
    years: range | None = None,
) -> None:
    years = years or range(2020, 2025)
    selected_years = set(years)

    _log_step("Configurando filtros EMITIDOS")
    _set_left_filter_options(page, section="EMITIDOS")

    _log_step("Configurando filtros RECIBIDOS")
    _set_left_filter_options(page, section="RECIBIDOS")

    _log_step("Seleccionando empresa 11810 - TIENDAS SORIANA")
    _set_checkbox_by_text(page, "Todas", False, scope_text="EMPRESAS", max_x=650)
    _set_checkbox_by_text(page, "11810 - TIENDAS SORIANA", True, scope_text="EMPRESAS", max_x=650)

    _log_step("Seleccionando periodos emitidos")
    _set_period_years(page, section="EMITIDOS", selected_years=selected_years)

    _log_step("Seleccionando periodos recibidos")
    _set_period_years(page, section="RECIBIDOS", selected_years=selected_years)

    if rfc:
        _log_step("Llenando RFC en emitidos y recibidos")
        _fill_rfc_fields(page, rfc)

    _log_step("Seleccionando archivo Hoja de calculo bases y tasas (.csv)")
    _set_checkbox_by_text(
        page,
        "Hoja de calculo bases y tasas (.csv)",
        True,
        scope_text="ARCHIVOS A DESCARGAR",
        min_x=900,
    )
    _set_checkbox_by_text(
        page,
        "Generar acumulado",
        True,
        scope_text="ARCHIVOS A DESCARGAR",
        min_x=900,
    )


def _set_left_filter_options(page, *, section: str) -> None:
    _set_checkbox_by_text(page, "Todos", False, scope_text=section, max_x=500)
    _set_checkbox_by_text(page, "Vigentes", True, scope_text=section, max_x=500)
    _set_checkbox_by_text(page, "Cancelados", False, scope_text=section, max_x=500)
    _set_checkbox_by_text(page, "Ingreso", True, scope_text=section, max_x=500)
    _set_checkbox_by_text(page, "Egreso", False, scope_text=section, max_x=500)
    _set_checkbox_by_text(page, "Complementos de pago", False, scope_text=section, max_x=500)
    _set_checkbox_by_text(page, "Traslado", False, scope_text=section, max_x=500)


def _set_period_years(page, *, section: str, selected_years: set[int]) -> None:
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


def _fill_rfc_fields(page, rfc: str) -> None:
    result = page.evaluate(
        """
        ({ rfc }) => {
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
            const textElements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text && item.text.length <= 120);

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
                if (isRfc) matches.push(input);
            }

            for (const input of matches) {
                input.scrollIntoView({ block: "center", inline: "center" });
                input.focus();
                input.value = rfc;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
            }
            return matches.length;
        }
        """,
        {"rfc": rfc},
    )
    if result < 2:
        raise RuntimeError(f"No se llenaron las dos casillas RFC. Casillas encontradas: {result}.")
    _log_step(f"RFC capturado en {result} casillas")


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
    _set_checkbox_by_text(page, "Requerimiento", False, scope_text="Motivo")
    _set_checkbox_by_text(page, "Conciliacion", True, scope_text="Motivo")
    _set_checkbox_by_text(page, "Base de datos", False, scope_text="Motivo")
    _set_checkbox_by_text(page, "Dashboard", False, scope_text="Motivo")
    _set_checkbox_by_text(page, "Reportes Internos", False, scope_text="Motivo")
    _assert_choice_checked(page, "checkbox", "Conciliacion", "Motivo")

    _log_step("Seleccionando Frecuencia: Unica vez")
    _set_radio_by_text(page, "Unica vez", True, scope_text="Frecuencia")
    _assert_choice_checked(page, "radio", "Unica vez", "Frecuencia")


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


def _wait_for_request_zip(
    page,
    request_id: str,
    download_dir: Path,
    *,
    poll_seconds: int,
    max_wait_minutes: int,
) -> Path:
    _open_solicitudes(page)
    deadline = time.monotonic() + max_wait_minutes * 60
    attempt = 1
    while True:
        _log_step(f"Validando solicitud {request_id}. Intento {attempt}")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1_000)
        row = _find_request_row(page, request_id, timeout_ms=30_000)
        if row is None:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"No se encontro la solicitud {request_id} en {max_wait_minutes} minutos."
                )
            _log_step(f"La solicitud {request_id} aun no aparece en la tabla. Esperando {poll_seconds} segundos")
            page.wait_for_timeout(poll_seconds * 1_000)
            attempt += 1
            continue

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


def _set_radio_by_text(
    page,
    text: str,
    checked: bool,
    *,
    scope_text: str | None = None,
    required: bool = True,
) -> bool:
    return _set_choice_by_text(
        page,
        "radio",
        text,
        checked,
        scope_text=scope_text,
        required=required,
    )


def _assert_choice_checked(page, input_type: str, text: str, scope_text: str | None = None) -> None:
    result = page.evaluate(
        """
        ({ inputType, text, scopeText }) => {
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
            const textElements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text && item.text.length <= 220);

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

            const hasNearbyLabel = (input) => {
                const associated = labelText(input);
                if (associated && associated.includes(wanted)) return true;
                const rect = input.getBoundingClientRect();
                const centerY = rect.top + rect.height / 2;
                for (const item of textElements) {
                    if (!item.text.includes(wanted)) continue;
                    const itemCenterY = item.rect.top + item.rect.height / 2;
                    const vertical = Math.abs(itemCenterY - centerY);
                    const isNearRight = item.rect.left >= rect.left - 8 && item.rect.left <= rect.left + 340;
                    const isNearLeft = item.rect.right >= rect.left - 80 && item.rect.right <= rect.right + 12;
                    if (vertical <= 24 && (isNearRight || isNearLeft)) return true;
                }
                return false;
            };

            const inScope = (input) => {
                if (!wantedScope) return true;
                const rect = input.getBoundingClientRect();
                return textElements.some((item) => {
                    if (!item.text.includes(wantedScope)) return false;
                    if (item.rect.top > rect.top + 5) return false;
                    const horizontalGap = Math.max(item.rect.left - rect.right, rect.left - item.rect.right, 0);
                    return horizontalGap <= 650 && (rect.top - item.rect.top) <= 260;
                });
            };

            const inputs = Array.from(document.querySelectorAll(`input[type='${inputType}']`))
                .filter((input) => !input.disabled && isVisible(input));
            const selected = inputs.find((input) => hasNearbyLabel(input) && inScope(input));
            return {
                found: Boolean(selected),
                checked: Boolean(selected && selected.checked),
            };
        }
        """,
        {"inputType": input_type, "text": text, "scopeText": scope_text},
    )
    if not result.get("found"):
        raise RuntimeError(f"No se encontro la opcion para verificar: {scope_text or ''} {text}".strip())
    if not result.get("checked"):
        raise RuntimeError(f"La opcion no quedo seleccionada: {scope_text or ''} {text}".strip())
    _log_step(f"Verificado: {scope_text or ''} {text}".strip())


def _set_choice_by_text(
    page,
    input_type: str,
    text: str,
    checked: bool,
    *,
    scope_text: str | None = None,
    required: bool = True,
) -> bool:
    result = page.evaluate(
        """
        ({ inputType, text, checked, scopeText }) => {
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
            const textElements = Array.from(document.body.querySelectorAll("*"))
                .filter(isVisible)
                .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                .filter((item) => item.text && item.text.length <= 220);

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
                if (associated && associated.includes(wanted)) {
                    best = { distance: 0, source: associated };
                }

                for (const item of textElements) {
                    if (!item.text.includes(wanted)) continue;
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
                    if (horizontalGap > 650) continue;
                    const distance = (rect.top - item.rect.top) + horizontalGap / 4;
                    if (bestDistance === null || distance < bestDistance) {
                        bestDistance = distance;
                    }
                }
                return bestDistance;
            };

            const inputs = Array.from(document.querySelectorAll(`input[type='${inputType}']`))
                .filter((input) => !input.disabled && isVisible(input));

            const candidates = [];
            for (const input of inputs) {
                const target = nearbyTargetScore(input);
                if (!target) continue;
                const scope = scopeScore(input);
                if (wantedScope && scope === null) continue;
                candidates.push({ input, score: target.distance + (scope || 0) / 100 });
            }

            candidates.sort((a, b) => a.score - b.score);
            const selected = candidates[0];
            if (!selected) {
                return { ok: false, changed: false, message: `No se encontro opcion: ${text}` };
            }

            selected.input.scrollIntoView({ block: "center", inline: "center" });
            if (selected.input.checked !== checked) {
                selected.input.click();
                return { ok: true, changed: true, checked: selected.input.checked };
            }
            return { ok: true, changed: false, checked: selected.input.checked };
        }
        """,
        {
            "inputType": input_type,
            "text": text,
            "checked": checked,
            "scopeText": scope_text,
        },
    )
    if not result.get("ok") and required:
        raise RuntimeError(result.get("message") or f"No se encontro opcion: {text}")
    if result.get("ok"):
        _log_step(f"Opcion actualizada: {text}")
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
    return "okta/empresas" in current_url or "descarga-masiva/descargas" in current_url


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


def read_downloaded_csv(path: Path | str) -> pd.DataFrame:
    csv_path = Path(path)
    for encoding in ("utf-8-sig", "latin1"):
        try:
            return pd.read_csv(csv_path, sep=None, engine="python", encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(csv_path, sep=None, engine="python")


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
