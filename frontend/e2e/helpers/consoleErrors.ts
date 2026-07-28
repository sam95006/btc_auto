import type { Page } from "@playwright/test";

/**
 * Benign console patterns allowed during static preview (no backend).
 * Documented for Wave 4.1 visual acceptance — CI and local preview share this list.
 */
export const CONSOLE_ERROR_ALLOWLIST: RegExp[] = [
  /Failed to load resource/i,
  /net::ERR_/i,
  /fetch/i,
  /NetworkError/i,
  /WebSocket/i,
  /ws:\/\//i,
  /404.*favicon/i,
  /scanner/i,
  /portfolio/i,
  /api\/nexus/i,
  /api\/market/i,
  /CORS/i,
  /ResizeObserver loop/i,
];

export function isAllowedConsoleError(text: string): boolean {
  return CONSOLE_ERROR_ALLOWLIST.some((pattern) => pattern.test(text));
}

export function attachConsoleCollector(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (isAllowedConsoleError(text)) return;
    errors.push(text);
  });
  page.on("pageerror", (err) => {
    const text = err.message;
    if (isAllowedConsoleError(text)) return;
    errors.push(text);
  });
  return errors;
}

export function assertNoUnexpectedConsoleErrors(errors: string[]): void {
  if (errors.length) {
    throw new Error(`Unexpected console errors:\n${errors.join("\n")}`);
  }
}
