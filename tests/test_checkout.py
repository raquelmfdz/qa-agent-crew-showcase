"""
Sample Playwright tests for the SauceDemo catalog + cart + checkout flow
(REQ-2.1, REQ-2.2, REQ-2.3, REQ-3.1, REQ-4.1 - REQ-4.4).

Ships as a working baseline alongside test_login.py; the Automation
Engineer agent adds further generated tests covering the remaining risks
identified by the Risk Analyst / Test Designer agents.
"""

from playwright.sync_api import Page, expect

EXPECTED_PRODUCT_COUNT = 6


def login_as_standard_user(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.get_by_placeholder("Username").fill("standard_user")
    page.get_by_placeholder("Password").fill("secret_sauce")
    page.get_by_role("button", name="Login").click()
    expect(page).to_have_url(f"{base_url}/inventory.html")


def test_inventory_lists_all_seeded_products(page: Page, base_url: str) -> None:
    """REQ-2.1: the inventory page lists all 6 seeded products, each with
    a name, price, description, and an 'Add to cart' control."""
    login_as_standard_user(page, base_url)

    items = page.locator(".inventory_item")
    expect(items).to_have_count(EXPECTED_PRODUCT_COUNT)
    for i in range(EXPECTED_PRODUCT_COUNT):
        item = items.nth(i)
        expect(item.locator(".inventory_item_name")).to_be_visible()
        expect(item.locator(".inventory_item_price")).to_be_visible()
        expect(item.locator(".inventory_item_desc")).to_be_visible()
        expect(item.get_by_role("button", name="Add to cart")).to_be_visible()


def test_products_are_sortable_by_price_low_to_high(page: Page, base_url: str) -> None:
    """REQ-2.2: products can be sorted; spot-check price low-high."""
    login_as_standard_user(page, base_url)

    page.locator(".product_sort_container").select_option("lohi")
    prices = page.locator(".inventory_item_price").all_inner_texts()
    numeric_prices = [float(p.replace("$", "")) for p in prices]
    assert numeric_prices == sorted(numeric_prices)


def test_add_to_cart_updates_badge(page: Page, base_url: str) -> None:
    """REQ-2.3: adding a product updates the cart badge and button label."""
    login_as_standard_user(page, base_url)
    page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    expect(page.locator(".shopping_cart_badge")).to_have_text("1")
    expect(page.locator("[data-test='remove-sauce-labs-backpack']")).to_be_visible()


def test_cart_reflects_added_item(page: Page, base_url: str) -> None:
    """REQ-3.1: the cart page accurately lists items that were added."""
    login_as_standard_user(page, base_url)
    page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    page.locator(".shopping_cart_link").click()
    expect(page).to_have_url(f"{base_url}/cart.html")
    expect(page.get_by_text("Sauce Labs Backpack")).to_be_visible()


def test_checkout_requires_all_fields(page: Page, base_url: str) -> None:
    """REQ-4.1: checkout step one blocks progress if a field is missing."""
    login_as_standard_user(page, base_url)
    page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    page.locator(".shopping_cart_link").click()
    page.get_by_role("button", name="Checkout").click()
    page.get_by_role("button", name="Continue").click()
    expect(page.locator("[data-test='error']")).to_contain_text("First Name is required")


def test_full_checkout_flow_completes(page: Page, base_url: str) -> None:
    """REQ-4.2 - REQ-4.4: a full checkout ends on the confirmation page
    with an accurate summary and an emptied cart afterwards."""
    login_as_standard_user(page, base_url)
    page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    page.locator(".shopping_cart_link").click()
    page.get_by_role("button", name="Checkout").click()

    page.get_by_placeholder("First Name").fill("Ada")
    page.get_by_placeholder("Last Name").fill("Lovelace")
    page.get_by_placeholder("Zip/Postal Code").fill("94105")
    page.get_by_role("button", name="Continue").click()

    expect(page.locator(".summary_total_label")).to_be_visible()
    page.get_by_role("button", name="Finish").click()

    expect(page.get_by_text("Thank you for your order!")).to_be_visible()

    page.locator(".shopping_cart_link").click()
    expect(page.locator(".cart_item")).to_have_count(0)
