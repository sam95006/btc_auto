import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";
import { assertNoForbiddenTradeControls } from "./helpers/safetyAssertions";

test.describe("PUB-E Founder Private Operator UI", () => {
  test("member session cannot see Founder Operator in primary nav", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/overview");
    await expect(page.locator('.sidebar-nav a[href="/founder/operator"]')).toHaveCount(0);
    await expect(page.locator('.sidebar-nav a[href="/founder/runtime"]')).toHaveCount(0);
    await runStandardSafetyChecks(page, consoleErrors);
  });

  test("unauthenticated founder operator shows authorization gate", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/founder/operator");
    await expect(
      page.getByText(/Founder Authorization Required|Operator Access Denied|驗證 Founder/i).first()
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/member session denied|會員工作階段無法/i).first()).toBeVisible();
    await assertNoForbiddenTradeControls(page);
    // Private panel titles must not render without auth
    await expect(page.getByRole("heading", { name: /^Capture Health$/i })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /^Lesson Gate$/i })).toHaveCount(0);
    await runStandardSafetyChecks(page, consoleErrors);
  });

  test("legacy /founder/runtime redirects toward operator gate", async ({ page }) => {
    await gotoRoute(page, "/founder/runtime");
    await expect(page).toHaveURL(/\/founder\/operator/);
  });
});
