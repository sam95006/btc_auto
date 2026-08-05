import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Founder runtime page", () => {
  test("redirects to Founder Private Operator (auth-gated)", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/founder/runtime");
    await expect(page).toHaveURL(/\/founder\/operator/);
    await expect(
      page.getByText(/Founder Authorization Required|Operator Access Denied|驗證 Founder|Founder Private Operator/i).first()
    ).toBeVisible({ timeout: 15000 });
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
