import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Symbol workbench", () => {
  test("renders BTCUSDT workbench tabs", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/market/BTCUSDT");
    await expect(page.locator('[aria-label="Symbol workbench"]')).toBeVisible();
    await expect(page.getByText(/BTC/i).first()).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
