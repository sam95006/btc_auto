/**
 * News provider foundation — pending only. Never invents headlines.
 */

import { pendingMetric, type ParityMetric } from "../parityContracts";

export type NewsItem = {
  id: string;
  title: string;
  source?: string;
  publishedAt?: number | null;
  url?: string;
};

export type NewsFeedValue = {
  items: NewsItem[];
};

export type NewsProvider = {
  providerId: string;
  isAvailable(): Promise<boolean>;
  getHeadlines(limit?: number): Promise<ParityMetric<NewsFeedValue>>;
};

export class NewsProviderPending implements NewsProvider {
  providerId = "NEWS_PROVIDER_PENDING";

  async isAvailable() {
    return false;
  }

  async getHeadlines(_limit = 10): Promise<ParityMetric<NewsFeedValue>> {
    return pendingMetric<NewsFeedValue>(
      "News",
      this.providerId,
      "UNAVAILABLE_PROVIDER_PENDING · 不顯示假新聞標題",
    );
  }
}

export const newsProvider: NewsProvider = new NewsProviderPending();
