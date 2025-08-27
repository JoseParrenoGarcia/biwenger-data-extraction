from pathlib import Path
import tomllib as toml
from playwright.sync_api import sync_playwright
import re
from playwright.sync_api import TimeoutError as PWTimeout
import time

DEFAULT_ROOT_URL = "https://biwenger.as.com/"
DEFAULT_APP_URL = "https://biwenger.as.com/app"

def load_biwenger_credentials() -> dict:
    """
    Load Biwenger credentials from secrets/biwenger.toml.

    Returns:
        dict: {"email": str, "password": str}
    """
    # Resolve repo root relative to this file
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent  # one level up from scraping_biwenger/
    secrets_path = root_dir / "secrets" / "biwenger.toml"

    if not secrets_path.exists():
        raise FileNotFoundError(f"Secrets file not found: {secrets_path}")

    with open(secrets_path, "rb") as f:
        config = toml.load(f)

    email = config.get("biwenger", {}).get("biwenger_email")
    password = config.get("biwenger", {}).get("biwenger_password")

    if not email or not password:
        raise ValueError(f"Missing 'biwenger_email' or 'biwenger_password' in {secrets_path}")

    return {"email": email, "password": password}

def accept_cookies_if_present(page) -> bool:
    """
    Tries to accept the Didomi cookie banner if it appears.
    Returns True if we clicked/accepted, False otherwise.
    """
    # 1) Wait briefly to see if the popup mounts
    try:
        page.wait_for_selector("div.didomi-popup-container", timeout=2000, state="attached")
    except PWTimeout:
        pass  # it's okay if it never appears

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
            return True
        except Exception:
            pass

    return False

def start_browser_accept_cookies(headless: bool = True):
    """
    Start browser, accept cookies (if present), log in, land on app page.
    Returns (pw, browser, context, page).
    """
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless, args=["--disable-gpu", "--no-sandbox"])
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(20000)

    page.goto(DEFAULT_ROOT_URL)
    accept_cookies_if_present(page)
    return pw, browser, context, page

def click_play_now(page) -> None:
    # If the cookie popup is still around, give it a moment to detach
    try:
        page.wait_for_selector("div.didomi-popup-container", state="detached", timeout=3000)
    except PWTimeout:
        pass  # not a blocker

    candidates = [
        'a[routerlink="/login"]',
        'a[href="/login"]',
        'a.btn.primary.xl:has-text("Play now!")',
        'text=/^Play now!$/',
    ]

    for sel in candidates:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=2000)
            loc.scroll_into_view_if_needed()
            loc.click()
            page.wait_for_url("**/login", timeout=10000)
            return
        except Exception:
            continue

    # If we got here, surface a clear error
    raise RuntimeError("Could not find/click the 'Play now!' login link.")

def perform_login(page, email: str, password: str):
    click_play_now(page)

    page.get_by_role("button", name=re.compile("Already have an account|Ya tengo cuenta", re.I)).click()
    page.get_by_role("textbox", name=re.compile("Email|Correo", re.I)).fill(email)
    page.get_by_role("textbox", name=re.compile("Password|Contraseña", re.I)).fill(password)
    page.get_by_role("button", name=re.compile("Log in|Iniciar sesión", re.I)).click()

    # 1) Wait for any known post-login landing (login-success or /), then
    # 2) Navigate to the app explicitly.
    try:
        # allows either /login-success or /
        page.wait_for_url(re.compile(r"https://biwenger\.as\.com(/login-success|/)?$"), timeout=20000)
    except PWTimeout:
        # sometimes the route changes client-side quickly; a load-state guard is enough
        page.wait_for_load_state("domcontentloaded", timeout=20000)

    # Now go where we actually want to be
    page.goto(DEFAULT_APP_URL, wait_until="domcontentloaded")

def click_tab_in_horizontal_main_menu(page, tab_name: str):
    """
    Click a horizontal menu tab by name (case-insensitive).
    Examples: click_tab_in_horizontal_main_menu(page, "team")
    """
    target = tab_name.strip().lower()

    # Just click by href directly
    page.click(f'a[href="/{target}"]')

    # Wait for navigation to happen
    page.wait_for_url(f"**/{target}*", timeout=10000)

def scroll_into_view(page, selector, hold=0.2):
    page.locator(selector).first.scroll_into_view_if_needed(timeout=2000)
    time.sleep(hold)  # Let rendering catch up


if __name__ == "__main__":
    creds = load_biwenger_credentials()
    # print(creds["email"])  # your biwenger email
    # print(creds["password"])  # your biwenger password
