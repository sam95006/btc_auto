import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Overview page", () => {
  test("renders Simple View with NO_DATA funnel by default", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/overview");
    await expect(page.getByRole("heading", { name: "總覽", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Simple View" })).toBeVisible();
    await expect(page.locator('[aria-label="Decision funnel"] .w4-no-data, [aria-label="Decision funnel"]').getByText(/NO_DATA/i).first()).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });

  test("primary nav links to universe", async ({ page }) => {
    await gotoRoute(page, "/overview");
    await page.getByRole("link", { name: /全市場|市場/i }).first().click();
    await expect(page).toHaveURL(/\/universe/);
    await expect(page.getByRole("heading", { name: "全市場" })).toBeVisible();
  });
});
