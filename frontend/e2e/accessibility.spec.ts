import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MEMBER_A11Y_ROUTES } from "./helpers/constants";
import { gotoRoute } from "./helpers/pageSetup";

/**
 * Legacy wave4 a11y entry — now scans Member Platform routes (PUB2-J).
 * Prefer e2e/a11y-member.spec.ts for WCAG 2.2 AA + overflow + touch gates.
 */
test.describe("@a11y Accessibility scans", () => {
  for (const route of MEMBER_A11Y_ROUTES.slice(0, 8)) {
    test(`@a11y ${route.path} has no serious axe violations`, async ({ page }) => {
      await gotoRoute(page, route.path);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
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
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious).toEqual([]);
  });
});
