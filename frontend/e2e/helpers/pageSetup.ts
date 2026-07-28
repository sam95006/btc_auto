import { expect, type Page } from "@playwright/test";
import {
  attachConsoleCollector,
  assertNoUnexpectedConsoleErrors,
} from "./consoleErrors";
import {
  assertNoDataFunnelDefault,
  assertNoFloatingAssistant,
  assertNoForbiddenTradeControls,
  assertSingleAiCommander,
} from "./safetyAssertions";

export async function gotoRoute(page: Page, route: string): Promise<string[]> {
  const consoleErrors = attachConsoleCollector(page);
  await page.goto(route, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await expect(page.locator("main")).toBeVisible();
  return consoleErrors;
}

export async function runStandardSafetyChecks(
  page: Page,
  consoleErrors: string[],
): Promise<void> {
  await assertSingleAiCommander(page);
  await assertNoFloatingAssistant(page);
  await assertNoForbiddenTradeControls(page);
  await assertNoDataFunnelDefault(page);
  assertNoUnexpectedConsoleErrors(consoleErrors);
}
