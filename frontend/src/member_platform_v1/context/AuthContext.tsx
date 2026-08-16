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
import { getMemberEntitlements, getMemberSession, stagingLogin, stagingLogout, stagingRegister } from "../services/stagingApi";

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
  }) => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<MemberSession | null>(null);
  const [ready, setReady] = useState(false);
  const [previewTier] = useState<MembershipTier | null>(null);

  const setPreviewTier = useCallback((_t: MembershipTier | null) => undefined, []);

  const hydrate = useCallback(async () => {
    const [{ session: remote, profile }, entitlements] = await Promise.all([getMemberSession(), getMemberEntitlements()]);
    const tier: MembershipTier = entitlements.entitlements.includes("ENTERPRISE") ? "enterprise"
      : entitlements.entitlements.includes("PROFESSIONAL") ? "professional"
      : entitlements.entitlements.includes("ADVANCED") ? "advanced" : "starter";
    setSession({
      id: remote.account_id, email: remote.email, displayName: profile.display_name || remote.email.split("@")[0],
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
  }) => {
    await stagingRegister(input);
    await hydrate();
  }, [hydrate]);

  const logout = useCallback(async () => {
    await stagingLogout().catch(() => undefined);
    setSession(null);
  }, []);

  const tier: MembershipTier = session?.tier || "starter";

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
