# Requirements: SauceDemo Login & Checkout Flow

**Target system:** [https://www.saucedemo.com](https://www.saucedemo.com)
**Scope:** User authentication and the end-to-end purchase flow (cart → checkout → order confirmation).

## 1. Authentication

SauceDemo provides several pre-seeded accounts (all with password `secret_sauce`),
listed on the login page itself:

| Username | Behavior |
|---|---|
| `standard_user` | Normal, fully-functional user. Use this as the primary test account. |
| `locked_out_user` | Login is rejected with an explicit "locked out" error. |
| `problem_user` | Logs in, but product images are broken/mismatched throughout the site. |
| `performance_glitch_user` | Logs in, but with significant artificial delay. |
| `error_user` | Logs in, but triggers errors during checkout-related actions. |
| `visual_user` | Logs in, but has visual/layout regressions (misaligned elements). |

**Functional requirements:**
- REQ-1.1: A user submitting valid credentials (`standard_user` / `secret_sauce`) must be
  taken to the Products (inventory) page.
- REQ-1.2: A user submitting `locked_out_user` / `secret_sauce` must see an error message
  indicating the account is locked, and must NOT be granted access.
- REQ-1.3: A user submitting an invalid username/password combination must see a generic
  authentication error and remain on the login page.
- REQ-1.4: Submitting the login form with an empty username and/or password must show a
  field-required validation error.
- REQ-1.5: A logged-in user must be able to log out via the side menu and be returned to
  the login page, with protected pages no longer accessible.

## 2. Product Catalog

- REQ-2.1: The inventory page must list all 6 seeded products with name, price, description,
  and an "Add to cart" control.
- REQ-2.2: Products must be sortable by name (A-Z, Z-A) and price (low-high, high-low).
- REQ-2.3: Adding a product to the cart must update the cart badge count and change the
  product's button to "Remove".

## 3. Cart

- REQ-3.1: The cart page must accurately reflect every item added, with correct quantity
  and price.
- REQ-3.2: Users must be able to remove items from the cart, both from the cart page and
  from the inventory page.
- REQ-3.3: The cart must persist its contents across navigation within the session.

## 4. Checkout

- REQ-4.1: Checkout step one must require First Name, Last Name, and Zip/Postal Code;
  submitting with any field empty must show a validation error and block progress.
- REQ-4.2: Checkout step two (overview) must show an accurate summary: item list, item
  total, tax, and final total.
- REQ-4.3: Completing checkout must show a confirmation ("Thank you for your order") page.
- REQ-4.4: After order completion, the cart must be emptied.
- REQ-4.5: Using `error_user`, checkout actions (e.g. removing an item during checkout)
  may trigger unexpected errors — this is a known-risk account and should be exercised
  specifically for negative testing.

## 5. Non-functional notes (for risk triage, not strict pass/fail gates)

- Performance: `performance_glitch_user` intentionally simulates slow responses; flows
  involving this account should tolerate longer waits rather than being treated as
  failures.
- Visual integrity: `visual_user` and `problem_user` are intended for visual-regression
  style checks; broken images/misaligned CSS are the expected "bug" to detect, not an
  automation defect.
- These accounts make SauceDemo a convenient, free, public target for demonstrating
  both happy-path and deliberately-broken-path QA automation without needing a private
  staging environment.
