/**
 * Replaceable service layer.
 * Today: MockAdapter. Later: ZeaburPublicApiAdapter — same DTOs, same UI.
 */
import type {
  AlertDto,
  AssetDetailDto,
  DashboardDto,
  MarketRankingRowDto,
  MembershipTier,
  MemberSession,
  PlanDto,
} from "../types/dto";
import {
  buildDashboard,
  getAssetDetail,
  MOCK_ALERTS,
  MOCK_PLANS,
  MOCK_RANKING,
} from "../mocks/data";

export interface MarketApi {
  getDashboard(tier: MembershipTier, watchSymbols: string[]): Promise<DashboardDto>;
  getRanking(tier: MembershipTier): Promise<MarketRankingRowDto[]>;
  getAsset(symbol: string): Promise<AssetDetailDto | null>;
}

export interface AlertApi {
  list(): Promise<AlertDto[]>;
  markRead(id: string): Promise<void>;
}

export interface MemberApi {
  getPlans(): Promise<PlanDto[]>;
  login(email: string, _password: string): Promise<MemberSession>;
  register(input: {
    email: string;
    displayName: string;
    accountType: "individual" | "enterprise";
  }): Promise<MemberSession>;
}

const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));

export const marketApi: MarketApi = {
  async getDashboard(tier, watchSymbols) {
    await delay();
    return buildDashboard(tier, watchSymbols);
  },
  async getRanking(tier) {
    await delay();
    return tier === "starter" ? MOCK_RANKING.slice(0, 4) : MOCK_RANKING;
  },
  async getAsset(symbol) {
    await delay();
    return getAssetDetail(symbol);
  },
};

let alertStore = [...MOCK_ALERTS];

export const alertApi: AlertApi = {
  async list() {
    await delay();
    return [...alertStore];
  },
  async markRead(id) {
    await delay(60);
    alertStore = alertStore.map((a) => (a.id === id ? { ...a, read: true } : a));
  },
};

export const memberApi: MemberApi = {
  async getPlans() {
    await delay();
    return MOCK_PLANS;
  },
  async login(email) {
    await delay(200);
    return {
      id: "mem_mock_1",
      email,
      displayName: email.split("@")[0] || "會員",
      accountType: "individual",
      tier: "advanced",
    };
  },
  async register(input) {
    await delay(220);
    return {
      id: "mem_mock_new",
      email: input.email,
      displayName: input.displayName || input.email.split("@")[0] || "新會員",
      accountType: input.accountType,
      tier: "starter",
    };
  },
};
