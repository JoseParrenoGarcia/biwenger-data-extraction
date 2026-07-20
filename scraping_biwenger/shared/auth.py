import re
import time

from playwright.sync_api import TimeoutError as PWTimeout

from scraping_biwenger.shared.config import DEFAULT_APP_URL
from scraping_biwenger.shared.timing import _log_timing


def accept_cookies_if_present(page, logger=None) -> bool:
    """
    Tries to accept the Didomi cookie banner if it appears.
    Returns True if we clicked/accepted, False otherwise.
    """
    started_at = time.perf_counter()
    if logger:
        logger.info("Checking for cookie banner on main page.")

    # 1) Wait briefly to see if the popup mounts
    try:
        page.wait_for_selector("div.didomi-popup-container", timeout=2000, state="attached")
    except PWTimeout:
        _log_timing(logger, "No cookie banner detected", started_at)
        return False

    # 2) Try the most specific selectors first (fast, explicit)
    for sel in (
        "#didomi-notice-agree-button",
        "button.didomi-components-button.didomi-dismiss-button.didomi-button-highlight",
        "button[aria-label='Agree']",
        "button:has-text('Agree')",
        "button:has-text('Aceptar')",
        "button:has-text('Accept all')",
    ):
        try:
            page.locator(sel).first.click(timeout=1200)
            _log_timing(logger, f"Accepted cookie banner with selector {sel}", started_at)
            return True
        except Exception:
            pass

    _log_timing(logger, "Cookie banner was present but no accept selector matched", started_at)
    return False


def dismiss_app_popups_if_present(page, logger=None, timeout_ms: int = 800) -> bool:
    """
    Best-effort dismissal for Biwenger app-level marketing dialogs.

    These pop-ups are intermittent and can block app table controls after login.
    Returns True only when a visible dialog was closed.
    """
    dialog_selector = "ng-component[role='dialog'][aria-modal='true']"
    close_selectors = [
        f"{dialog_selector} button.close-button",
        f"{dialog_selector} button[aria-label='Close']",
        f"{dialog_selector} button[title='Close']",
    ]

    try:
        page.wait_for_selector(dialog_selector, timeout=timeout_ms, state="visible")
    except PWTimeout:
        if logger:
            logger.debug("No Biwenger app pop-up detected.")
        return False
    except Exception:
        if logger:
            logger.debug("Biwenger app pop-up check failed before detecting a dialog.")
        return False

    for selector in close_selectors:
        try:
            page.locator(selector).first.click(timeout=1200)
            try:
                page.wait_for_selector(dialog_selector, timeout=1500, state="detached")
            except Exception:
                pass
            if logger:
                logger.info("Dismissed Biwenger app pop-up with selector %s.", selector)
            return True
        except Exception:
            continue

    if logger:
        logger.warning("Biwenger app pop-up was visible but no close selector worked.")
    return False


def click_play_now(page, logger=None) -> None:
    started_at = time.perf_counter()
    if logger:
        logger.info("Attempting to click Play now from main page.")

    # If the cookie popup is still around, give it a moment to detach
    try:
        page.wait_for_selector("div.didomi-popup-container", state="detached", timeout=3000)
    except PWTimeout:
        pass  # not a blocker

    candidates = [
        'a.btn.primary.xl:has-text("Play now!")',
        'a[routerlink="/login"]',
        'a[href="/login"]',
        "text=/^Play now!$/",
    ]

    for sel in candidates:
        selector_started_at = time.perf_counter()
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=2000)
            loc.scroll_into_view_if_needed(timeout=1000)
            loc.click(timeout=1000)
            page.wait_for_url("**/login", timeout=10000)
            _log_timing(logger, f"Clicked Play now with selector {sel}", selector_started_at)
            _log_timing(logger, "Landed on login page", started_at)
            return
        except Exception:
            _log_timing(logger, f"Play now selector did not match: {sel}", selector_started_at)
            continue

    # If we got here, surface a clear error
    raise RuntimeError("Could not find/click the 'Play now!' login link.")


def perform_login(page, email: str, password: str, logger=None):
    started_at = time.perf_counter()
    if logger:
        logger.info("Starting Biwenger login flow.")

    click_play_now(page, logger=logger)

    login_choice_selectors = [
        "app-login button.login",
        "button.btn.login",
        "button:has-text('Log in')",
        "button:has-text('Iniciar sesión')",
    ]
    for sel in login_choice_selectors:
        selector_started_at = time.perf_counter()
        try:
            page.locator(sel).first.click(timeout=3000)
            _log_timing(logger, f"Clicked login form selector {sel}", selector_started_at)
            break
        except Exception:
            _log_timing(logger, f"Login form selector did not match: {sel}", selector_started_at)
            pass
    else:
        if logger:
            logger.info("Trying legacy login choice button selector.")
        page.get_by_role(
            "button",
            name=re.compile("Already have an account|Ya tengo cuenta", re.I),
        ).click()

    form_started_at = time.perf_counter()
    if logger:
        logger.info("Filling Biwenger login form fields.")
    page.get_by_role("textbox", name=re.compile("Email|Correo", re.I)).fill(email)
    page.get_by_role("textbox", name=re.compile("Password|Contraseña", re.I)).fill(password)
    _log_timing(logger, "Filled login form fields", form_started_at)

    submit_started_at = time.perf_counter()
    if logger:
        logger.info("Submitting Biwenger login form.")
    page.get_by_role("button", name=re.compile("Log in|Iniciar sesión", re.I)).click()

    # 1) Wait for any known post-login landing (login-success or /), then
    # 2) Navigate to the app explicitly.
    try:
        # allows either /login-success or /
        page.wait_for_url(re.compile(r"https://biwenger\.as\.com(/login-success|/)?$"), timeout=20000)
    except PWTimeout:
        # sometimes the route changes client-side quickly; a load-state guard is enough
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    _log_timing(logger, "Login submission completed", submit_started_at)

    # Now go where we actually want to be
    app_started_at = time.perf_counter()
    if logger:
        logger.info("Navigating directly to Biwenger app page: %s", DEFAULT_APP_URL)
    page.goto(DEFAULT_APP_URL, wait_until="domcontentloaded")
    _log_timing(logger, "Landed on Biwenger app page", app_started_at)
    dismiss_app_popups_if_present(page, logger=logger)
    _log_timing(logger, "Biwenger login flow completed", started_at)
