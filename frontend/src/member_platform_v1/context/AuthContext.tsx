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
  getMemberSession,
  registrationRequiresVerification,
  stagingLogin,
  stagingLogout,
  stagingRegister,
  type StagingRegisterResult,
} from "../services/stagingApi";

// Personal product tiers are ONLY these four. Enterprise is a SEPARATE product
// and must never become the Personal UI tier — it (and anything unknown) fails
// closed to free.
const PERSONAL_TIERS: MembershipTier[] = ["free", "starter", "pro", "advanced"];

/** Coerce the Personal access effective plan to a Personal tier (fail closed to
 * free). "enterprise" or any unknown code -> free; the frontend never upgrades
 * access, and never falls back to a legacy entitlement architecture. */
function normalizeTier(code: string | null | undefined): MembershipTier {
  const c = (code || "").trim().toLowerCase();
  return (PERSONAL_TIERS as string[]).includes(c) ? (c as MembershipTier) : "free";
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
    // Effective tier is backend-authoritative and TRIAL-AWARE, sourced ONLY from
    // the Personal access endpoint (NOT the generic billing plan, which is
    // billing-subscription-only). If Personal access cannot be established we fail
    // closed to free — never a legacy entitlement fallback, never an upgrade.
    let tier: MembershipTier = "free";
    try {
      tier = normalizeTier((await getPersonalAccess()).effective_plan_code);
    } catch {
      tier = "free";
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
