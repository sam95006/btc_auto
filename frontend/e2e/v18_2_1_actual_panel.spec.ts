import { test, expect } from "@playwright/test";

test.describe("V18.2.1 actual panel preview", () => {
  test.use({
    baseURL: "http://127.0.0.1:4173",
  });

  test.beforeEach(async ({ page }) => {
    await page.goto("/opportunities?member_surface_v18_2_1=1");
  });

  test("opportunities hub loads with simplified IA", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "機會" })).toBeVisible();
    await expect(page.getByTestId("opportunities-v1821")).toBeVisible();
  });

  test("overview has six primary sections", async ({ page }) => {
    await page.goto("/overview?member_surface_v18_2_1=1");
    await expect(page.getByTestId("actual-panel-overview")).toBeVisible();
    await expect(page.getByTestId("overview-ticker")).toBeVisible();
    await expect(page.getByTestId("overview-status-strip")).toBeVisible();
    await expect(page.getByTestId("top-opportunities")).toBeVisible();
    await expect(page.getByTestId("decision-funnel")).toBeVisible();
    await expect(page.getByTestId("critical-alerts")).toBeVisible();
    await expect(page.getByTestId("ask-ai")).toBeVisible();
  });

  test("anomalies redirects to alerts", async ({ page }) => {
    await page.goto("/anomalies?member_surface_v18_2_1=1");
    await expect(page).toHaveURL(/\/alerts/);
  });
});
