import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Learning page", () => {
  test("renders learning hub with AI Learning Lab link", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/learning");
    await expect(page.getByRole("heading", { name: "學習" })).toBeVisible();
    await expect(page.getByText(/固定 25x shadow/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /AI Learning Lab/i }).first()).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
