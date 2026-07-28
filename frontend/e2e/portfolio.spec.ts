import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";
import { assertPortfolioLeveragePolicy } from "./helpers/safetyAssertions";

test.describe("Portfolio page", () => {
  test("shows fixed 25x shadow policy without live controls", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/portfolio");
    await expect(page.getByRole("heading", { name: "投資組合" })).toBeVisible();
    await assertPortfolioLeveragePolicy(page);
    await expect(page.getByText(/顯示槓桿一律\s*25/i)).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
