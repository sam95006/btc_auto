import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { MembershipTier, MemberSession } from "../types/dto";
import {
  getPersonalAccess,
  getMemberEntitlements,
  getMemberSession,
  registrationRequiresVerification,
  stagingLogin,
  stagingLogout,
  stagingRegister,
  type StagingRegisterResult,
} from "../services/stagingApi";

const CANONICAL_TIERS: MembershipTier[] = ["free", "starter", "pro", "advanced", "enterprise"];

/** Coerce a backend plan code to a canonical Personal tier (fail closed to free). */
function normalizeTier(code: string | null | undefined): MembershipTier {
  const c = (code || "").trim().toLowerCase();
  return (CANONICAL_TIERS as string[]).includes(c) ? (c as MembershipTier) : "free";
}

/** Best-effort map of the legacy member-entitlement plan naming to canonical. */
function mapMemberPlan(plan: string | null | undefined): MembershipTier {
  switch ((plan || "").trim().toUpperCase()) {
    case "ENTERPRISE": return "enterprise";
    case "PRO": return "pro";
    case "INTERMEDIATE": return "advanced";
    default: return "free";
  }
}

type AuthCtx = {
  session: MemberSession | null;
  ready: boolean;
  /** Effective tier = preview override or session tier */
  tier: MembershipTier;
  previewTier: MembershipTier | null;
  setPreviewTier: (t: MembershipTier | null) => void;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    confirmPassword: string;
    displayName: string;
    founderClaimCode?: string;
  }) => Promise<StagingRegisterResult>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<MemberSession | null>(null);
  const [ready, setReady] = useState(false);
  const [previewTier] = useState<MembershipTier | null>(null);

  const setPreviewTier = useCallback((_t: MembershipTier | null) => undefined, []);

  const hydrate = useCallback(async () => {
    const { session: remote, profile } = await getMemberSession();
    // Canonical effective plan is backend-authoritative and TRIAL-AWARE: an active
    // Starter trial resolves to Starter here, consistent with /personal/subscription.
    // It comes from the Personal access endpoint (NOT the generic billing plan,
    // which is billing-subscription-only). The old member-entitlement naming is a
    // best-effort fallback. The frontend never derives access from a tier rank.
    let tier: MembershipTier = "free";
    try {
      tier = normalizeTier((await getPersonalAccess()).effective_plan_code);
    } catch {
      try { tier = mapMemberPlan((await getMemberEntitlements()).plan); } catch { tier = "free"; }
    }
    setSession({
      id: remote.user_id, email: remote.email, displayName: profile.display_name || remote.email.split("@")[0],
      accountType: "individual", tier,
    });
  }, []);

  useEffect(() => {
    void hydrate().catch(() => setSession(null)).finally(() => setReady(true));
  }, [hydrate]);

  const login = useCallback(async (email: string, password: string) => {
    await stagingLogin(email, password);
    await hydrate();
  }, [hydrate]);

  const register = useCallback(async (input: {
    email: string; password: string; confirmPassword: string; displayName: string; founderClaimCode?: string;
  }): Promise<StagingRegisterResult> => {
    const result = await stagingRegister(input);
    if (registrationRequiresVerification(result)) {
      // Pending verification: there is no usable session yet. Do NOT hydrate.
      setSession(null);
      return result;
    }
    await hydrate();
    return result;
  }, [hydrate]);

  const logout = useCallback(async () => {
    await stagingLogout().catch(() => undefined);
    setSession(null);
  }, []);

  const tier: MembershipTier = session?.tier || "free";

  const value = useMemo(
    () => ({ session, ready, tier, previewTier, setPreviewTier, login, register, logout }),
    [session, ready, tier, previewTier, setPreviewTier, login, register, logout]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
