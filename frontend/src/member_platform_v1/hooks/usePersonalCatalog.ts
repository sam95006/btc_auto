/**
 * NEXUS-EXPERIENCE-1B.1 — canonical Personal catalog foundation.
 *
 * Single source of truth for commercial plans, capability states and trial
 * metadata is the backend `/api/v1/personal/catalog` contract (nexus_platform).
 * The frontend must NOT duplicate canonical pricing or capability truth in
 * constants — it consumes this hook instead.
 */
import { useEffect, useState } from "react";
import { getPersonalCatalog, type PersonalCatalog } from "../services/stagingApi";

export type CatalogState = {
  catalog: PersonalCatalog | null | undefined; // undefined=loading, null=error
  loading: boolean;
  error: boolean;
};

export function usePersonalCatalog(): CatalogState {
  const [catalog, setCatalog] = useState<PersonalCatalog | null | undefined>(undefined);
  useEffect(() => {
    let on = true;
    getPersonalCatalog()
      .then((c) => { if (on) setCatalog(c); })
      .catch(() => { if (on) setCatalog(null); });
    return () => { on = false; };
  }, []);
  return { catalog, loading: catalog === undefined, error: catalog === null };
}

/** Canonical price label from backend pricing (never a hard-coded constant). */
export function planPriceLabel(
  plan: PersonalCatalog["commercial"]["plans"][number],
  currency: string,
  fmt: { free: string; contact: string; perMonth: (amount: string, currency: string) => string },
): string {
  if (plan.contact_sales) return fmt.contact;
  if (plan.monthly_usd == null || plan.monthly_usd === 0) return fmt.free;
  return fmt.perMonth(String(plan.monthly_usd), currency);
}
