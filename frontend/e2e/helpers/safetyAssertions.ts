import { expect, type Page } from "@playwright/test";

export async function assertSingleAiCommander(page: Page): Promise<void> {
  const commanderFab = page.locator('button[aria-label="Open AiCommander"]');
  await expect(commanderFab).toHaveCount(1);
  await expect(page.locator('[aria-label="AiCommander"]')).toHaveCount(1);
}

export async function assertNoFloatingAssistant(page: Page): Promise<void> {
  await expect(page.locator('[aria-label="AI Assistant"]')).toHaveCount(0);
  await expect(page.locator('button[aria-label="Open AI assistant"]')).toHaveCount(0);
}

export async function assertNoForbiddenTradeControls(page: Page): Promise<void> {
  const body = page.locator("body");
  await expect(body.getByRole("button", { name: /^Live Trade$/i })).toHaveCount(0);
  await expect(body.getByRole("button", { name: /^ARM$/i })).toHaveCount(0);
  await expect(body.getByRole("button", { name: /Mainnet/i })).toHaveCount(0);
  await expect(body.getByText(/^Live Trade$/i)).toHaveCount(0);
}

export async function assertNoDataFunnelDefault(page: Page): Promise<void> {
  const funnelGrid = page.locator(".w4-funnel-grid");
  if ((await funnelGrid.count()) === 0) {
    return;
  }
  const steps = funnelGrid.locator(".w4-funnel-step strong.mono");
  const values = await steps.allTextContents();
  const nums = values
    .map((v) => parseInt(v.trim(), 10))
    .filter((n) => !Number.isNaN(n));
  if (nums.length >= 3 && nums[0] === 128 && nums[1] === 24 && nums[2] === 6) {
    throw new Error("Synthetic funnel default 128/24/6 detected as live data");
  }
}

export async function assertPortfolioLeveragePolicy(page: Page): Promise<void> {
  await expect(page.getByText(/25x/i).first()).toBeVisible();
  await expect(page.getByText(/Shadow/i).first()).toBeVisible();
  await expect(page.getByText(/NO live trade|NO ARM|NO mainnet/i).first()).toBeVisible();
}

export async function assertFounderRuntimeLabels(page: Page): Promise<void> {
  await expect(
    page.getByText(/Founder Authorization Required|Founder Private Operator|Founder Operator/i).first()
  ).toBeVisible();
  await expect(page.getByText(/FOUNDER PRIVATE|READ-ONLY|founder-only|member session denied/i).first()).toBeVisible();
  await expect(page.getByText(/私有|founder|Founder/i).first()).toBeVisible();
}

export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(2);
}
