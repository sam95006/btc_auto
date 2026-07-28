import { test, expect } from "@playwright/test";
import { gotoRoute, runStandardSafetyChecks } from "./helpers/pageSetup";
import { assertFounderRuntimeLabels } from "./helpers/safetyAssertions";

test.describe("Founder runtime page", () => {
  test("shows READ ONLY founder-private observability", async ({ page }) => {
    const consoleErrors = await gotoRoute(page, "/founder/runtime");
    await assertFounderRuntimeLabels(page);
    await expect(page.getByText(/無下單|無 ARM|無 mainnet/i).first()).toBeVisible();
    await runStandardSafetyChecks(page, consoleErrors);
  });
});
