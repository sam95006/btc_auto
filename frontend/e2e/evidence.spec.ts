import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Evidence page", () => {
  test("renders evidence center READ ONLY", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/evidence");
    await expect(page.getByRole("heading", { name: /Evidence Center/i, level: 1 })).toBeVisible();
    await expect(page.getByText(/READ ONLY/i).first()).toBeVisible();
    await expect(page.locator('[aria-label="Evidence zones"]')).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
