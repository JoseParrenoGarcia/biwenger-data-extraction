from scraping_biwenger.shared.auth import (
    accept_cookies_if_present,
    click_play_now,
    perform_login,
)
from scraping_biwenger.shared.browser_session import start_browser_accept_cookies
from scraping_biwenger.shared.config import (
    DEFAULT_APP_URL,
    DEFAULT_ROOT_URL,
    load_biwenger_credentials,
)
from scraping_biwenger.shared.navigation import (
    click_tab_in_horizontal_main_menu,
    scroll_into_view,
)
from scraping_biwenger.shared.timing import _log_timing


__all__ = [
    "DEFAULT_APP_URL",
    "DEFAULT_ROOT_URL",
    "_log_timing",
    "accept_cookies_if_present",
    "click_play_now",
    "click_tab_in_horizontal_main_menu",
    "load_biwenger_credentials",
    "perform_login",
    "scroll_into_view",
    "start_browser_accept_cookies",
]


if __name__ == "__main__":
    creds = load_biwenger_credentials()
    # print(creds["email"])  # your biwenger email
    # print(creds["password"])  # your biwenger password
