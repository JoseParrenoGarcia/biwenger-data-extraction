from pathlib import Path
import tomllib as toml
from playwright.sync_api import sync_playwright
import re
from playwright.sync_api import TimeoutError as PWTimeout
import time

DEFAULT_ROOT_URL = "https://biwenger.as.com/"
DEFAULT_APP_URL = "https://biwenger.as.com/app"


def _log_timing(logger, message: str, started_at: float) -> None:
    if logger:
        logger.info("%s in %.2fs", message, time.perf_counter() - started_at)


def load_biwenger_credentials(profile: str = "biwenger") -> dict:
    """
    Load Biwenger credentials from secrets/biwenger.toml.

    Args:
        profile: Which section to read. Usually:
                 - "biwenger" (your main account)
                 - "biwenger_player_scraper" (secondary account)

    Returns:
        dict: {"email": str, "password": str}

    Raises:
        FileNotFoundError: secrets file missing
        ValueError: requested profile missing or incomplete
    """
    # Resolve repo root relative to this file
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent  # one level up from scraping_biwenger/
    secrets_path = root_dir / "secrets" / "biwenger.toml"

    if not secrets_path.exists():
        raise FileNotFoundError(f"Secrets file not found: {secrets_path}")

    with open(secrets_path, "rb") as f:
        config = toml.load(f)

    if profile not in config:
        available = ", ".join(config.keys())
        raise ValueError(
            f"Profile [{profile}] not found in {secrets_path}. "
            f"Available sections: {available}"
        )

    section = config.get(profile, {})
    email = section.get("biwenger_email")
    password = section.get("biwenger_password")

    if not email or not password:
        raise ValueError(
            f"Missing 'biwenger_email' or 'biwenger_password' in section [{profile}] of {secrets_path}"
        )

    return {"email": email, "password": password}

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

def start_browser_accept_cookies(headless: bool = True, logger=None):
    """
    Start browser, accept cookies (if present), log in, land on app page.
    Returns (pw, browser, context, page).
    """
    started_at = time.perf_counter()
    if logger:
        logger.info("Starting Chromium browser. headless=%s", headless)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless, args=["--disable-gpu", "--no-sandbox"])
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(20000)
    _log_timing(logger, "Browser context ready", started_at)

    started_at = time.perf_counter()
    if logger:
        logger.info("Navigating to Biwenger main page: %s", DEFAULT_ROOT_URL)
    page.goto(DEFAULT_ROOT_URL)
    _log_timing(logger, "Landed on Biwenger main page", started_at)
    accept_cookies_if_present(page, logger=logger)
    return pw, browser, context, page

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
        'text=/^Play now!$/',
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
    _log_timing(logger, "Biwenger login flow completed", started_at)

def click_tab_in_horizontal_main_menu(page, tab_name: str, logger=None):
    """
    Click a horizontal menu tab by name (case-insensitive).
    Examples: click_tab_in_horizontal_main_menu(page, "team")
    """
    target = tab_name.strip().lower()
    started_at = time.perf_counter()
    if logger:
        logger.info("Navigating to Biwenger tab: %s from %s", target, page.url)

    try:
        tab_selector = f'a[href="/{target}"]'
        page.locator(tab_selector).first.wait_for(state="visible", timeout=5000)
        page.click(tab_selector)
    except Exception:
        if logger:
            logger.info("Tab link for '%s' was not visible; navigating directly.", target)
        page.goto(f"{DEFAULT_ROOT_URL}{target}", wait_until="domcontentloaded")

    page.wait_for_url(f"**/{target}*", timeout=10000)
    _log_timing(logger, f"Landed on Biwenger tab: {target}", started_at)

def scroll_into_view(page, selector, hold=0.2):
    page.locator(selector).first.scroll_into_view_if_needed(timeout=2000)
    time.sleep(hold)  # Let rendering catch up


if __name__ == "__main__":
    creds = load_biwenger_credentials()
    # print(creds["email"])  # your biwenger email
    # print(creds["password"])  # your biwenger password
