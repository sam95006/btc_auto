import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { MembershipTier, MemberSession } from "../types/dto";
import { memberApi } from "../services";

const SESSION_KEY = "nexus_mp_v1_session";
const TIER_PREVIEW_KEY = "nexus_mp_v1_tier_preview";

type AuthCtx = {
  session: MemberSession | null;
  /** Effective tier = preview override or session tier */
  tier: MembershipTier;
  previewTier: MembershipTier | null;
  setPreviewTier: (t: MembershipTier | null) => void;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    displayName: string;
    accountType: "individual" | "enterprise";
  }) => Promise<void>;
  logout: () => void;
};

const Ctx = createContext<AuthCtx | null>(null);

function loadSession(): MemberSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as MemberSession) : null;
  } catch {
    return null;
  }
}

function loadPreview(): MembershipTier | null {
  try {
    const raw = localStorage.getItem(TIER_PREVIEW_KEY);
    if (raw === "starter" || raw === "advanced" || raw === "professional" || raw === "enterprise") {
      return raw;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<MemberSession | null>(() => loadSession());
  const [previewTier, setPreviewTierState] = useState<MembershipTier | null>(() => loadPreview());

  const setPreviewTier = useCallback((t: MembershipTier | null) => {
    setPreviewTierState(t);
    if (t) localStorage.setItem(TIER_PREVIEW_KEY, t);
    else localStorage.removeItem(TIER_PREVIEW_KEY);
  }, []);

  const persist = (s: MemberSession | null) => {
    setSession(s);
    if (s) localStorage.setItem(SESSION_KEY, JSON.stringify(s));
    else localStorage.removeItem(SESSION_KEY);
  };

  const login = useCallback(async (email: string, password: string) => {
    const s = await memberApi.login(email, password);
    persist(s);
  }, []);

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      displayName: string;
      accountType: "individual" | "enterprise";
    }) => {
      const s = await memberApi.register(input);
      persist(s);
    },
    []
  );

  const logout = useCallback(() => persist(null), []);

  const tier: MembershipTier = previewTier || session?.tier || "starter";

  const value = useMemo(
    () => ({ session, tier, previewTier, setPreviewTier, login, register, logout }),
    [session, tier, previewTier, setPreviewTier, login, register, logout]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
