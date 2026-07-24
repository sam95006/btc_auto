/**
 * Fear & Greed provider foundation (Product 7.2).
 * Richer state machine: pending / unavailable / error / stale.
 * lastAttempted + lastSuccessful tracked. NO fake index values ever.
 */

import {
  unavailableMetric,
  staleMetric,
  isStale,
  initialProviderState,
  type ParityMetric,
  type ProviderState,
} from "../parityContracts";

export type FearGreedValue = {
  /** 0–100 index value from real provider only. Never estimated. */
  value: number;
  classification: string;
  /** Source endpoint / provider name for traceability. */
  dataSource: string;
};

export type FearGreedProvider = {
  providerId: string;
  getState(): ProviderState;
  isAvailable(): Promise<boolean>;
  getIndex(): Promise<ParityMetric<FearGreedValue>>;
};

/**
 * Pending stub — no real data source wired yet.
 * Tracks lastAttempted so UI can show when last probe occurred.
 * State transitions: pending → (if wired) available/error/unavailable.
 */
export class FearGreedProviderPending implements FearGreedProvider {
  providerId = "FEAR_GREED_PROVIDER_PENDING";

  private state: ProviderState = initialProviderState();

  getState(): ProviderState {
    return { ...this.state };
  }

  async isAvailable(): Promise<boolean> {
    this.state = {
      ...this.state,
      lastAttempted: Date.now(),
      availability: "unavailable",
    };
    return false;
  }

  async getIndex(): Promise<ParityMetric<FearGreedValue>> {
    const now = Date.now();
    this.state = {
      ...this.state,
      lastAttempted: now,
      consecutiveFailures: this.state.consecutiveFailures + 1,
      availability: "unavailable",
      lastError: "provider not configured",
    };

    // If we had a stale cached value, return stale — but we have none here.
    return unavailableMetric<FearGreedValue>(
      "Fear & Greed",
      this.providerId,
      [
        "PROVIDER_PENDING · 尚未接入外部數據源",
        "不顯示虛構指數值",
        "接入後需要：真實 API 端點 + 速率限制 + 快取",
        "替代：NEXUS Altcoin Breadth（不是 Fear/Greed 官方指數）",
      ].join(" · "),
      this.state,
    );
  }
}

export const fearGreedProvider: FearGreedProvider = new FearGreedProviderPending();

/**
 * Contract stub for future real provider.
 * When a real data source is wired, it should extend this interface and
 * implement stale detection using isStale() + staleMetric().
 */
export type FearGreedRealProviderContract = FearGreedProvider & {
  /** Cache TTL in ms — must not return values older than this without stale label. */
  cacheTtlMs: number;
  /** Called if fetch fails — must increment consecutiveFailures and set lastAttempted. */
  onFetchError(err: unknown): ParityMetric<FearGreedValue>;
};

export function makeFearGreedStaleGuard(
  value: FearGreedValue,
  lastSuccessful: number,
  source: string,
): ParityMetric<FearGreedValue> {
  if (isStale(lastSuccessful)) {
    return staleMetric<FearGreedValue>("Fear & Greed", source, lastSuccessful, value);
  }
  return {
    status: "live",
    value,
    label: "Fear & Greed",
    freshness: new Date(lastSuccessful).toLocaleTimeString(),
    lastAttempted: new Date().toISOString(),
    lastSuccessful: new Date(lastSuccessful).toISOString(),
    sampleCount: null,
    coverageNote: null,
    error: null,
    source,
  };
}

export { };
