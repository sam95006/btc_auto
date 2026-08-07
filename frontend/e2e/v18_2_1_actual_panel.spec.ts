import { test, expect } from "@playwright/test";

test.describe("V18.2.1 actual panel preview", () => {
  test.use({
    baseURL: "http://127.0.0.1:4173",
  });

  test.beforeEach(async ({ page }) => {
    await page.goto("/opportunities?member_surface_v18_2_1=1");
  });

  test("opportunities hub loads with task-first IA", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /機會|找機會/ })).toBeVisible();
    await expect(page.getByTestId("opportunities-v1821")).toBeVisible();
  });

  test("overview has task-first product sections", async ({ page }) => {
    await page.goto("/overview?member_surface_v18_2_1=1");
    await expect(page.getByTestId("actual-panel-overview")).toBeVisible();
    await expect(page.getByTestId("overview-market-now").or(page.getByTestId("overview-market-hero"))).toBeVisible();
    await expect(page.getByTestId("decision-funnel")).toBeVisible();
    await expect(
      page.getByTestId("overview-primary-actions").or(page.getByRole("link", { name: /找市場機會|掃描/ })),
    ).toBeVisible();
  });

  test("density preference lives under Account display settings", async ({ page }) => {
    await page.goto("/account?member_surface_v18_2_1=1");
    await expect(page.getByText("顯示設定")).toBeVisible();
    const toggle = page.getByTestId("ui-density-toggle").first();
    await expect(toggle.getByRole("button", { name: "簡潔" })).toBeVisible();
    await expect(toggle.getByRole("button", { name: "專業" })).toBeVisible();
    // Mode controls must not dominate Overview chrome
    await page.goto("/overview?member_surface_v18_2_1=1");
    await expect(page.locator(".market-top-ticker [data-testid='ui-density-toggle']")).toHaveCount(0);
  });

  test("anomalies redirects to alerts", async ({ page }) => {
    await page.goto("/anomalies?member_surface_v18_2_1=1");
    await expect(page).toHaveURL(/\/alerts/);
  });
});
