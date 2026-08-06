import { useCallback, useEffect, useState } from "react";
import type { EntitlementDenialBody, PublicEntitlementDto, PublicPlan } from "./types";

const API = "/api/public/entitlements/v18_2/me";

export function usePublicEntitlements(plan: PublicPlan = "FREE") {
  const [dto, setDto] = useState<PublicEntitlementDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API}?plan=${encodeURIComponent(plan)}`, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((body) => {
        if (cancelled) return;
        if (body?.entitlement) {
          setDto(body.entitlement as PublicEntitlementDto);
          setError(null);
        } else {
          setError(body?.error || "entitlement_unavailable");
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [plan]);

  const hasCapability = useCallback(
    (capabilityId: string) => {
      return dto?.capabilities?.includes(capabilityId) ?? false;
    },
    [dto],
  );

  return { dto, loading, error, hasCapability };
}

export async function checkCapability(
  plan: PublicPlan,
  capabilityId: string,
): Promise<{ granted: true } | EntitlementDenialBody> {
  const resp = await fetch("/api/public/entitlements/v18_2/check", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Nexus-Plan": plan },
    body: JSON.stringify({ plan, capability_id: capabilityId }),
  });
  const body = await resp.json();
  if (resp.ok && body.granted) {
    return { granted: true };
  }
  return body as EntitlementDenialBody;
}
