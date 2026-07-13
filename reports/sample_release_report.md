# QA Release Report — SauceDemo Login & Checkout (sample)

> This is a **sample** report checked into the repo so you can see the
> expected shape of the Release Reporter's output without running the
> pipeline first. Real runs overwrite `reports/release_report.md` and
> `docs/index.html` (both gitignored except this sample).

## Executive summary

The crew analyzed the login and checkout flow described in
`requirements.md`, designed 10 test scenarios covering the top risks,
automated 7 of them as Playwright tests, and ran the suite against
`https://www.saucedemo.com`. **6 passed, 1 failed.** The one failure is a
known, intentional SauceDemo defect (`error_user` checkout behavior), not
a defect in the automation.

**Recommendation: GO**, with a follow-up ticket to track the `error_user`
negative-path finding for documentation purposes (it is expected
platform behavior, not a regression).

## Coverage summary

| Risk area | Covered? |
|---|---|
| Standard login (REQ-1.1) | ✅ |
| Locked-out user (REQ-1.2) | ✅ |
| Invalid credentials (REQ-1.3) | ✅ |
| Add to cart / badge update (REQ-2.3) | ✅ |
| Cart accuracy (REQ-3.1) | ✅ |
| Checkout field validation (REQ-4.1) | ✅ |
| Full checkout completion (REQ-4.2–4.4) | ✅ |
| `error_user` checkout errors (REQ-4.5) | ⚠️ Automated, fails as expected |

**7 / 8 top risks covered by automation** (~88% of identified high-priority risks).

## Test results

- **Total:** 7
- **Passed:** 6
- **Failed:** 1
- **Duration:** ~42s

## Failure analysis

### `test_error_user_checkout_fails`
- **Root cause hypothesis:** SauceDemo's `error_user` account intentionally
  breaks checkout interactions (documented platform behavior, not a bug
  in the test or a real product regression).
- **Suggested next step:** Keep this test as a documented negative-path
  check; no fix required.

## GO / NO-GO Recommendation

**GO**

Core login and checkout flows are fully covered and passing. The single
failure is an intentional, documented platform behavior used for
negative testing, not a functional regression.

---
*Sample content, not from a live run.*
