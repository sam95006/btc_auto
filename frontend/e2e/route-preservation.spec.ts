import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";

test.describe("Route preservation", () => {
  test("/ redirects to /overview", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/overview/);
  });

  test("/fleets redirects to /universe", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/fleets");
    await expect(page).toHaveURL(/\/universe/);
    await expect(page.getByRole("heading", { name: "全市場", level: 1 })).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });

  test("/scanner aliases to universe page", async ({ page }) => {
    await gotoRoute(page, "/scanner");
    await expect(page.getByRole("heading", { name: "全市場" })).toBeVisible();
  });

  test("/research-performance redirects to /performance", async ({ page }) => {
    await page.goto("/research-performance");
    await expect(page).toHaveURL(/\/performance/);
  });

  test("unknown route falls back to overview", async ({ page }) => {
    await page.goto("/this-route-does-not-exist-wave4");
    await expect(page).toHaveURL(/\/overview/);
  });
});
