/**
 * Altcoin Season provider foundation — pending only. No meme index.
 */

import { pendingMetric, type ParityMetric } from "../parityContracts";

export type AltcoinSeasonValue = {
  score: number;
  regime: string;
};

export type AltcoinSeasonProvider = {
  providerId: string;
  isAvailable(): Promise<boolean>;
  getIndex(): Promise<ParityMetric<AltcoinSeasonValue>>;
};

export class AltcoinSeasonProviderPending implements AltcoinSeasonProvider {
  providerId = "ALTCOIN_SEASON_PROVIDER_PENDING";

  async isAvailable() {
    return false;
  }

  async getIndex(): Promise<ParityMetric<AltcoinSeasonValue>> {
    return pendingMetric<AltcoinSeasonValue>(
      "Altcoin Season",
      this.providerId,
      "UNAVAILABLE_PROVIDER_PENDING · 可用 NEXUS Altcoin Breadth 作為研究代理（非官方 Altseason）",
    );
  }
}

export const altcoinSeasonProvider: AltcoinSeasonProvider = new AltcoinSeasonProviderPending();
