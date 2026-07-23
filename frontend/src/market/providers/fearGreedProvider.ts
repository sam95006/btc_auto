/**
 * Fear & Greed provider foundation — pending only. No fake index values.
 */

import { pendingMetric, type ParityMetric } from "../parityContracts";

export type FearGreedValue = {
  value: number;
  classification: string;
};

export type FearGreedProvider = {
  providerId: string;
  isAvailable(): Promise<boolean>;
  getIndex(): Promise<ParityMetric<FearGreedValue>>;
};

export class FearGreedProviderPending implements FearGreedProvider {
  providerId = "FEAR_GREED_PROVIDER_PENDING";

  async isAvailable() {
    return false;
  }

  async getIndex(): Promise<ParityMetric<FearGreedValue>> {
    return pendingMetric<FearGreedValue>(
      "Fear & Greed",
      this.providerId,
      "UNAVAILABLE_PROVIDER_PENDING · 不顯示虛構指數",
    );
  }
}

export const fearGreedProvider: FearGreedProvider = new FearGreedProviderPending();
