import { test, expect } from "@playwright/test";
import { VIEWPORTS, PRIMARY_ROUTES } from "./helpers/constants";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";
import { assertNoHorizontalOverflow } from "./helpers/safetyAssertions";

test.describe("Responsive layout", () => {
  for (const route of PRIMARY_ROUTES) {
    test(`mobile viewport has no horizontal overflow on ${route.path}`, async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile);
      const consoleErrors = await gotoRoute(page, route.path);
      await expect(page.getByRole("heading", { name: route.heading, level: 1 })).toBeVisible();
      await assertNoHorizontalOverflow(page);
      await runStandardSafetyChecks(page, consoleErrors);
    });
  }

  test("mobile bottom nav visible on overview", async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await gotoRoute(page, "/overview");
    await expect(page.locator(".w4-mobile-bottom-nav")).toBeVisible();
  });
});
