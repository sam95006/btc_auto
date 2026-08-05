import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MEMBER_A11Y_ROUTES, VIEWPORTS } from "./helpers/constants";
import { gotoRoute } from "./helpers/pageSetup";
import { assertNoHorizontalOverflow } from "./helpers/safetyAssertions";
import { MIN_TOUCH_TARGET_PX } from "../src/a11y";

test.describe("@a11y Member WCAG 2.2 AA", () => {
  for (const route of MEMBER_A11Y_ROUTES) {
    test(`@a11y ${route.path} axe wcag22aa no serious`, async ({ page }) => {
      await gotoRoute(page, route.path);
      await expect(page.locator("h1")).toBeVisible();
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

  test("@a11y skip link reaches main", async ({ page }) => {
    await gotoRoute(page, "/home");
    await page.keyboard.press("Tab");
    const skip = page.locator(".nx-skip-link");
    await expect(skip).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#main-content")).toBeFocused();
  });

  test("@a11y default document lang is zh-Hant-TW", async ({ page }) => {
    await gotoRoute(page, "/home");
    const lang = await page.locator("html").getAttribute("lang");
    expect(lang).toBe("zh-Hant-TW");
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/首頁|Home/);
  });

  test("@a11y English locale switch updates lang", async ({ page }) => {
    await gotoRoute(page, "/home");
    await page.getByRole("button", { name: "English" }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Member Home");
  });
});

test.describe("@a11y 375px overflow + touch targets", () => {
  test.use({ viewport: VIEWPORTS.mobile375 });

  test("@a11y home has no horizontal overflow at 375", async ({ page }) => {
    await gotoRoute(page, "/home");
    await assertNoHorizontalOverflow(page);
  });

  test("@a11y interactive controls meet 44px touch target", async ({ page }) => {
    await gotoRoute(page, "/home");
    const sizes = await page.evaluate((min) => {
      const selectors = [
        ".member-btn",
        ".member-mobile-nav a",
        ".nx-locale-switcher button",
        ".nav-collapse-btn",
      ];
      const bad: string[] = [];
      for (const sel of selectors) {
        for (const el of Array.from(document.querySelectorAll(sel))) {
          const r = (el as HTMLElement).getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && (r.width < min || r.height < min)) {
            bad.push(`${sel} ${Math.round(r.width)}x${Math.round(r.height)}`);
          }
        }
      }
      return bad;
    }, MIN_TOUCH_TARGET_PX);
    expect(sizes, sizes.join(", ")).toEqual([]);
  });
});

test.describe("@a11y zoom 200% reflow", () => {
  test("@a11y home usable at 200% zoom emulation", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    await gotoRoute(page, "/home");
    await page.addStyleTag({
      content: "html { zoom: 2; }",
    });
    await expect(page.locator("h1")).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });
});

test.describe("@a11y reduced motion", () => {
  test.use({
    contextOptions: {
      reducedMotion: "reduce",
    },
  });

  test("@a11y home renders under prefers-reduced-motion", async ({ page }) => {
    await gotoRoute(page, "/home");
    await expect(page.locator("main#main-content")).toBeVisible();
  });
});
