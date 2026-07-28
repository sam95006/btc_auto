import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { PRIMARY_ROUTES } from "./helpers/constants";
import { gotoRoute } from "./helpers/pageSetup";

test.describe("@a11y Accessibility scans", () => {
  for (const route of PRIMARY_ROUTES) {
    test(`@a11y ${route.path} has no serious axe violations`, async ({ page }) => {
      await gotoRoute(page, route.path);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .disableRules(["color-contrast", "aria-required-children"])
        .analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      expect(
        serious,
        serious.map((v) => `${v.id}: ${v.description}`).join("\n"),
      ).toEqual([]);
    });
  }

  test("@a11y founder runtime passes axe", async ({ page }) => {
    await gotoRoute(page, "/founder/runtime");
    const results = await new AxeBuilder({ page })
      .disableRules(["color-contrast", "aria-required-children"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious).toEqual([]);
  });
});
