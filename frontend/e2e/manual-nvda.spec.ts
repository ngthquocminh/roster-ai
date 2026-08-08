/**
 * Manual NVDA screen-reader harness (Story 1.11, Task 6).
 *
 * Opens a real Chrome or Edge window on the Gate A surface with the same
 * deterministic API stubs Story 1.10's automated layer uses, then parks it so a
 * human can drive it with NVDA and fill in
 * `docs/ACCESSIBILITY-NVDA-CHECKLIST.md`.
 *
 * Why a harness rather than a plain `npm run preview` session: the application
 * session is established through OIDC against a fake issuer that is not
 * routable (`http://shiftmind.test/oidc`), and sessions are held in the API
 * process rather than in PostgreSQL — so there is no way to sign a browser in
 * by hand. `installApiStubs` supplies `/api/v1/auth/session` along with the
 * projection reads, which is exactly how the Story 1.10 accessibility evidence
 * was produced. The DOM and ARIA under test are the production build's.
 *
 * NOT COLLECTED BY DEFAULT. The test is only registered when NVDA_MANUAL is
 * set, so it never runs in `npm run test:e2e` and never contributes even a
 * skipped case to the Gate A report — a skip is "not proven" there.
 *
 *   # Chrome
 *   NVDA_MANUAL=1 npx playwright test e2e/manual-nvda.spec.ts \
 *     --project=chromium --headed
 *
 *   # Edge
 *   NVDA_MANUAL=1 npx playwright test e2e/manual-nvda.spec.ts \
 *     --project=msedge --headed
 *
 * Press Resume in the Playwright Inspector to close the window when finished.
 */
import { test } from "@playwright/test";

import { installApiStubs } from "./support/apiStubs";

if (process.env.NVDA_MANUAL) {
  test("park the Gate A surface for a manual NVDA pass", async ({ page }, testInfo) => {
    // `page.pause()` blocks until a human clicks Resume in the Playwright
    // Inspector, and `setTimeout(0)` removes the only thing that would ever
    // end the run. In a headless or CI context there is no Inspector to click,
    // so the pair would hang forever rather than fail. Refuse up front: this
    // harness is only meaningful with a real browser window and a human at it.
    if (process.env.CI) {
      throw new Error(
        "NVDA_MANUAL is set in a CI environment. This harness parks a browser " +
          "for a human driving NVDA and never terminates on its own; it must " +
          "not run unattended.",
      );
    }
    // `--headed` sets this to false; it is true or undefined otherwise.
    if (testInfo.project.use.headless !== false) {
      throw new Error(
        "The manual NVDA harness needs a real browser window. Re-run with " +
          "--headed (see docs/GATE-A-RUNBOOK.md § 3).",
      );
    }
    // A manual pass takes as long as it takes.
    test.setTimeout(0);
    await installApiStubs(page);
    await page.goto("/");
    // Hands control to the human. Everything from here is driven by keyboard
    // with NVDA's Speech Viewer open.
    await page.pause();
  });
}
