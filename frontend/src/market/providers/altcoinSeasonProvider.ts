/**
 * Altcoin Season provider foundation (Product 7.2).
 * Richer state machine: pending / unavailable / error / stale.
 * lastAttempted + lastSuccessful tracked. NO meme-level index invented.
 * Note: NEXUS has Altcoin Breadth (BTC-relative performance) — distinct from
 * "official" Altseason index. Never conflate the two without clear label.
 */

import {
  pendingMetric,
  unavailableMetric,
  staleMetric,
  isStale,
  initialProviderState,
  type ParityMetric,
  type ProviderState,
} from "../parityContracts";

export type AltcoinSeasonValue = {
  /** 0–100 score from real provider only. Never estimated. */
  score: number;
  regime: string;
  /** Whether this is a "official" altseason index or a NEXUS breadth proxy. */
  indexType: "official" | "nexus-breadth-proxy";
  dataSource: string;
};

export type AltcoinSeasonProvider = {
  providerId: string;
  getState(): ProviderState;
  isAvailable(): Promise<boolean>;
  getIndex(): Promise<ParityMetric<AltcoinSeasonValue>>;
};

export class AltcoinSeasonProviderPending implements AltcoinSeasonProvider {
  providerId = "ALTCOIN_SEASON_PROVIDER_PENDING";

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

  async getIndex(): Promise<ParityMetric<AltcoinSeasonValue>> {
    const now = Date.now();
    this.state = {
      ...this.state,
      lastAttempted: now,
      consecutiveFailures: this.state.consecutiveFailures + 1,
      availability: "unavailable",
      lastError: "provider not configured",
    };

    return unavailableMetric<AltcoinSeasonValue>(
      "Altcoin Season",
      this.providerId,
      [
        "PROVIDER_PENDING · 尚未接入外部數據源",
        "不顯示虛構 Altseason 分數",
        "NEXUS Altcoin Breadth 可作為研究代理（非官方 Altseason）",
        "接入後需明確標示 indexType: official | nexus-breadth-proxy",
      ].join(" · "),
      this.state,
    );
  }
}

export const altcoinSeasonProvider: AltcoinSeasonProvider =
  new AltcoinSeasonProviderPending();

/**
 * Future real provider stale guard.
 * When wired, use isStale() to decide between live and stale label.
 */
export function makeAltcoinSeasonStaleGuard(
  value: AltcoinSeasonValue,
  lastSuccessful: number,
  source: string,
): ParityMetric<AltcoinSeasonValue> {
  if (isStale(lastSuccessful)) {
    return staleMetric<AltcoinSeasonValue>(
      "Altcoin Season",
      source,
      lastSuccessful,
      value,
    );
  }
  return {
    status: "live",
    value,
    label: "Altcoin Season",
    freshness: new Date(lastSuccessful).toLocaleTimeString(),
    lastAttempted: new Date().toISOString(),
    lastSuccessful: new Date(lastSuccessful).toISOString(),
    sampleCount: null,
    coverageNote: value.indexType === "nexus-breadth-proxy"
      ? "⚠ 此為 NEXUS Breadth 代理，非官方 Altseason 指數"
      : null,
    error: null,
    source,
  };
}

export { pendingMetric };
