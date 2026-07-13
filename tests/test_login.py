"""
Sample Playwright tests for the SauceDemo login flow (REQ-1.1 - REQ-1.5).

These ship with the repo as a working baseline so the pipeline (and CI)
has something runnable even before the Automation Engineer agent generates
additional tests. Credentials are the standard ones SauceDemo publishes on
its own login page -- there is nothing secret here.
"""

from playwright.sync_api import Page, expect


def login(page: Page, base_url: str, username: str, password: str) -> None:
    page.goto(base_url)
    page.get_by_placeholder("Username").fill(username)
    page.get_by_placeholder("Password").fill(password)
    page.get_by_role("button", name="Login").click()


def test_standard_user_can_log_in(page: Page, base_url: str) -> None:
    """REQ-1.1: valid credentials land on the Products (inventory) page."""
    login(page, base_url, "standard_user", "secret_sauce")
    expect(page).to_have_url(f"{base_url}/inventory.html")
    expect(page.get_by_text("Products")).to_be_visible()


def test_locked_out_user_is_rejected(page: Page, base_url: str) -> None:
    """REQ-1.2: locked_out_user must see an explicit lockout error."""
    login(page, base_url, "locked_out_user", "secret_sauce")
    expect(page).to_have_url(f"{base_url}/")
    expect(page.locator("[data-test='error']")).to_contain_text("locked out")


def test_invalid_credentials_show_generic_error(page: Page, base_url: str) -> None:
    """REQ-1.3: bad credentials keep the user on the login page with an error."""
    login(page, base_url, "standard_user", "wrong_password")
    expect(page).to_have_url(f"{base_url}/")
    expect(page.locator("[data-test='error']")).to_contain_text(
        "Username and password do not match"
    )


def test_empty_credentials_show_field_required_error(page: Page, base_url: str) -> None:
    """REQ-1.4: submitting with no username/password shows a validation error."""
    page.goto(base_url)
    page.get_by_role("button", name="Login").click()
    expect(page.locator("[data-test='error']")).to_contain_text("Username is required")


def test_logout_returns_to_login_page_and_revokes_access(page: Page, base_url: str) -> None:
    """REQ-1.5: logout via the side menu returns to login and blocks
    protected pages afterwards."""
    login(page, base_url, "standard_user", "secret_sauce")
    expect(page).to_have_url(f"{base_url}/inventory.html")

    page.locator("#react-burger-menu-btn").click()
    page.get_by_text("Logout").click()
    expect(page).to_have_url(f"{base_url}/")

    # A logged-out user hitting a protected URL directly must be bounced
    # back to login, not shown the page.
    page.goto(f"{base_url}/inventory.html")
    expect(page).to_have_url(f"{base_url}/")
    expect(page.locator("[data-test='error']")).to_contain_text("logged in")


def test_performance_glitch_user_can_eventually_log_in(page: Page, base_url: str) -> None:
    """Non-functional note (requirements.md #5): performance_glitch_user
    simulates significant artificial delay; the flow should tolerate a
    longer wait rather than being treated as a failure."""
    page.set_default_timeout(30_000)
    login(page, base_url, "performance_glitch_user", "secret_sauce")
    expect(page).to_have_url(f"{base_url}/inventory.html", timeout=30_000)
