/**
 * PUB2-J performance budgets for the Member Platform shell.
 * Measured by scripts/measure_performance_budget.mjs after `vite build`.
 */
export const PERFORMANCE_BUDGETS = {
  /** Largest single hashed JS chunk (bytes, uncompressed on disk). */
  maxEntryJsBytes: 450_000,
  /** Sum of all hashed JS assets. */
  maxTotalJsBytes: 900_000,
  /** Sum of all hashed CSS assets. */
  maxTotalCssBytes: 220_000,
  /** HTML document. */
  maxIndexHtmlBytes: 12_000,
  /** Soft timing targets for local preview (ms) — advisory in e2e. */
  maxDomContentLoadedMs: 3_000,
  maxLoadEventMs: 5_000,
} as const;

export type PerformanceBudgets = typeof PERFORMANCE_BUDGETS;
