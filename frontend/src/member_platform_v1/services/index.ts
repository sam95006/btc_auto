/** Static product catalog. Member state is served exclusively by stagingApi. */
import type { PlanDto } from "../types/dto";

export {
  STAGING_API_ORIGIN,
  checkEntitlement,
  getLiveMarketSnapshot,
  getOrganizationPermissions,
  getStagingApiStatus,
} from "./stagingApi";

const PRODUCT_CATALOG: PlanDto[] = [
  { id: "starter", name: "入門", tagline: "產品型錄", audience: "產品型錄", priceLabel: "NT$0", dailyValue: "帳務未開放", features: ["公開市場資料", "staging member session"] },
  { id: "advanced", name: "進階", tagline: "產品型錄", audience: "產品型錄", priceLabel: "未開放", dailyValue: "帳務未開放", features: ["功能以有效權益為準"] },
  { id: "professional", name: "專業", tagline: "產品型錄", audience: "產品型錄", priceLabel: "未開放", dailyValue: "帳務未開放", features: ["功能以有效權益為準"] },
  { id: "enterprise", name: "企業", tagline: "產品型錄", audience: "產品型錄", priceLabel: "未開放", dailyValue: "帳務未開放", features: ["組織權限以資料庫為準"] },
];

export const memberApi = {
  async getPlans(): Promise<PlanDto[]> {
    return PRODUCT_CATALOG;
  },
};
