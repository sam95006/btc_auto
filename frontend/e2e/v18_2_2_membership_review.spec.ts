import { test, expect } from "@playwright/test";

test.describe("V18.2.2 membership entitlement review", () => {
  test("review surface shows preview-only badges", async ({ page }) => {
    await page.goto("/preview/v18_2_1/review");
    const review = page.getByTestId("membership-entitlement-review");
    await expect(review.getByText("PREVIEW ONLY")).toBeVisible();
    await expect(review.getByText("NO LIVE TRADING")).toBeVisible();
    await expect(review.getByText("NO BILLING")).toBeVisible();
  });

  test("plan selectors include Chinese labels", async ({ page }) => {
    await page.goto("/review?member_surface_v18_2_1=1");
    await expect(page.getByTestId("review-plan-VISITOR")).toContainText("訪客");
    await expect(page.getByTestId("review-plan-RESEARCH")).toContainText("研究版");
    await expect(page.getByTestId("review-plan-ENTERPRISE")).toContainText("企業版");
  });

  test("RESEARCH plan loads entitlement dto", async ({ page }) => {
    await page.goto("/review?member_surface_v18_2_1=1");
    await page.getByTestId("review-plan-RESEARCH").click();
    await expect(page.getByTestId("review-selected-plan")).toContainText("RESEARCH");
    await expect(page.getByTestId("review-entitlement-dto")).toBeVisible();
  });

  test("display modes simple and expert", async ({ page }) => {
    await page.goto("/review?member_surface_v18_2_1=1");
    await expect(page.getByRole("button", { name: "簡潔" })).toBeVisible();
    await expect(page.getByRole("button", { name: "專業" })).toBeVisible();
    await page.getByRole("button", { name: "專業" }).click();
    await expect(page.getByText(/Current preview mode:.*EXPERT/)).toBeVisible();
  });

  test("route shortcut to opportunities", async ({ page }) => {
    await page.goto("/review?member_surface_v18_2_1=1");
    await page.getByTestId("review-route-opportunities").click();
    await expect(page).toHaveURL(/\/opportunities/);
    await expect(page.getByTestId("opportunities-v1821")).toBeVisible();
  });

  test("reset state returns visitor simple", async ({ page }) => {
    await page.goto("/review?member_surface_v18_2_1=1");
    await page.getByTestId("review-plan-PRO").click();
    await page.getByRole("button", { name: "專業" }).click();
    await page.getByTestId("review-reset-state").click();
    await expect(page.getByTestId("review-plan-VISITOR")).toHaveAttribute("aria-pressed", "true");
  });

  test("sidebar link from opportunities when review build", async ({ page }) => {
    await page.goto("/opportunities?member_surface_v18_2_1=1");
    const link = page.getByTestId("nav-membership-review");
    // V18.2.7: Membership review removed from normal sidebar; route-only access remains.
    await expect(link).toHaveCount(0);
  });

  test("review route still reachable without sidebar link", async ({ page }) => {
    await page.goto("/preview/v18_2_1/review");
    const review = page.getByTestId("membership-entitlement-review");
    const blocked = page.getByTestId("membership-review-blocked");
    await expect(review.or(blocked)).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("V18.2.2 review blocked without preview build", () => {
  test("review page blocked or redirect when flag off", async ({ page }) => {
    await page.goto("/review?member_surface_v18_2_1=1");
    const review = page.getByTestId("membership-entitlement-review");
    const blocked = page.getByTestId("membership-review-blocked");
    await expect(review.or(blocked)).toBeVisible({ timeout: 15_000 });
  });
});
