import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Universe page", () => {
  test("renders universe workspace with funnel NO_DATA", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/universe");
    await expect(page.getByRole("heading", { name: "全市場" })).toBeVisible();
    await expect(page.getByText(/Universe/i)).toBeVisible();
    await expect(page.getByText(/NO_DATA/i).first()).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });

  test("column preset controls visible", async ({ page }) => {
    await gotoRoute(page, "/universe");
    await expect(page.locator('[aria-label="Column preset"]')).toBeVisible();
  });
});
