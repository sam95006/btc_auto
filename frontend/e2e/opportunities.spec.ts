import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Opportunities page", () => {
  test("renders long and short sections", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/opportunities");
    await expect(page.getByRole("heading", { name: "機會" })).toBeVisible();
    await expect(page.locator('[aria-label="Long opportunities"]')).toBeVisible();
    await expect(page.locator('[aria-label="Short opportunities"]')).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
