export type PublicPlan = "VISITOR" | "FREE" | "PRO" | "RESEARCH" | "ENTERPRISE";

export type PublicEntitlementDto = {
  schema: string;
  authority_id: string;
  policy_version: string;
  plan: PublicPlan;
  entitlement_source: string;
  capabilities: string[];
  limits: Record<string, number | string | null>;
  org_role?: string | null;
  effective_at: string;
  expires_at?: string | null;
  brand: {
    brand_status: string;
    pricing_status: string;
    billing_status: string;
    brand_display_name: string;
    price_display: string;
  };
  production_billing: boolean;
  read_only: boolean;
};

export type EntitlementDenialBody = {
  ok: false;
  error: "ENTITLEMENT_REQUIRED" | "POLICY_DENIED";
  capability_id: string;
  current_plan: string;
  required_plan?: string | null;
  message: string;
  upgrade_display: string;
  non_execution_disclaimer: boolean;
};

export const UI_DATA_STATES = [
  "LIVE",
  "LIVE_PARTIAL_DEGRADED",
  "DELAYED",
  "STALE",
  "STOPPED",
  "UNAVAILABLE",
  "FIXTURE",
  "DEMO_DATA",
] as const;

export type UiDataState = (typeof UI_DATA_STATES)[number];

export const ANALYTICS_DEFAULT_OBSERVATIONS = "NO_OBSERVATIONS";
