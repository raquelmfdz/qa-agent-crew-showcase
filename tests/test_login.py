"""
Sample Playwright tests for the SauceDemo login flow (REQ-1.1 - REQ-1.3).

These ship with the repo as a working baseline so the pipeline (and CI)
has something runnable even before the Automation Engineer agent generates
additional tests. Credentials are the standard ones SauceDemo publishes on
its own login page -- there is nothing secret here.
"""

from playwright.sync_api import Page, expect

BASE_URL = "https://www.saucedemo.com"


def login(page: Page, username: str, password: str) -> None:
    page.goto(BASE_URL)
    page.get_by_placeholder("Username").fill(username)
    page.get_by_placeholder("Password").fill(password)
    page.get_by_role("button", name="Login").click()


def test_standard_user_can_log_in(page: Page) -> None:
    """REQ-1.1: valid credentials land on the Products (inventory) page."""
    login(page, "standard_user", "secret_sauce")
    expect(page).to_have_url(f"{BASE_URL}/inventory.html")
    expect(page.get_by_text("Products")).to_be_visible()


def test_locked_out_user_is_rejected(page: Page) -> None:
    """REQ-1.2: locked_out_user must see an explicit lockout error."""
    login(page, "locked_out_user", "secret_sauce")
    expect(page).to_have_url(f"{BASE_URL}/")
    expect(page.locator("[data-test='error']")).to_contain_text("locked out")


def test_invalid_credentials_show_generic_error(page: Page) -> None:
    """REQ-1.3: bad credentials keep the user on the login page with an error."""
    login(page, "standard_user", "wrong_password")
    expect(page).to_have_url(f"{BASE_URL}/")
    expect(page.locator("[data-test='error']")).to_contain_text(
        "Username and password do not match"
    )
