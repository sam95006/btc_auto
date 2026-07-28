import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Alerts page", () => {
  test("renders composite alerts workspace", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/alerts");
    await expect(page.getByRole("heading", { name: "警報", level: 1 })).toBeVisible();
    await expect(page.locator('[aria-label="Alert summary"]')).toBeVisible();
    await expect(page.locator('[aria-label="Risk alerts"]')).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
