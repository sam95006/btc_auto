import { Link, Navigate, useNavigate } from "react-router-dom";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";
import { memberApi } from "../services";
import type { PlanDto } from "../types/dto";

export function LandingPage() {
  return (
    <section className="mpv1-hero">
      <div>
        <p className="mpv1-brand-sub" style={{ marginBottom: "0.75rem" }}>
          PREMIUM MARKET INTELLIGENCE
        </p>
        <h1 className="mpv1-hero-brand">NEXUS</h1>
        <p className="mpv1-hero-line" style={{ marginTop: "1rem" }}>
          把複雜市場翻譯成你看得懂的結論：偏多或偏空、可留意或先等等、風險高不高。
        </p>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "1.5rem" }}>
          <Link className="mpv1-btn mpv1-btn-primary" to="/register">
            開始使用
          </Link>
          <Link className="mpv1-btn mpv1-btn-ghost" to="/plans">
            比較方案
          </Link>
          <Link className="mpv1-btn mpv1-btn-soft" to="/login">
            已有帳號
          </Link>
        </div>
      </div>
      <div className="mpv1-hero-visual" aria-hidden>
        <div className="mpv1-chip mpv1-chip-bull">市場偏多</div>
        <div className="mpv1-chip mpv1-chip-advice">可留意 · ETH</div>
        <p className="mpv1-muted">結論優先 · 細節可展開 · 不下單</p>
      </div>
      <div className="mpv1-grid mpv1-grid-3" style={{ marginTop: "1rem" }}>
        {[
          ["今天市場怎麼了", "偏多、偏空或方向不明，一句話說清楚。"],
          ["哪些幣值得先看", "用分數與白話理由幫你縮小範圍。"],
          ["風險提醒", "追價過熱、方向不明等提醒，避免一次看太多。"],
        ].map(([t, b]) => (
          <article key={t} className="mpv1-card">
            <h2 className="mpv1-card-title">{t}</h2>
            <p className="mpv1-muted">{b}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function LoginPage() {
  const { login, session } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("founder@nexus.local");
  const [password, setPassword] = useState("demo");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (session) return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await login(email, password);
      nav("/app");
    } catch {
      setErr("登入失敗（Mock）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mpv1-card mpv1-auth-card">
      <h1 className="mpv1-auth-title">登入</h1>
      <p className="mpv1-muted" style={{ marginBottom: "1.25rem" }}>
        本機模擬登入，不會連到正式後端。
      </p>
      <form className="mpv1-form" onSubmit={onSubmit}>
        <div className="mpv1-field">
          <label htmlFor="email">Email</label>
          <input id="email" value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        </div>
        <div className="mpv1-field">
          <label htmlFor="password">密碼</label>
          <input
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            required
          />
        </div>
        {err ? <p className="mpv1-muted">{err}</p> : null}
        <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">
          {busy ? "登入中…" : "登入"}
        </button>
      </form>
      <p className="mpv1-muted" style={{ marginTop: "1rem" }}>
        <Link to="/forgot-password">忘記密碼</Link>
        {" · "}
        <Link to="/register">註冊</Link>
      </p>
    </div>
  );
}

export function RegisterPage() {
  const { register, session } = useAuth();
  const nav = useNavigate();
  const [accountType, setAccountType] = useState<"individual" | "enterprise">("individual");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  if (session) return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await register({ email, password, displayName, accountType });
      nav("/app");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mpv1-card mpv1-auth-card">
      <h1 className="mpv1-auth-title">註冊</h1>
      <p className="mpv1-muted" style={{ marginBottom: "1rem" }}>
        選擇個人或企業帳號（模擬）。
      </p>
      <div className="mpv1-seg" style={{ marginBottom: "1rem" }}>
        <button type="button" className={accountType === "individual" ? "is-on" : undefined} onClick={() => setAccountType("individual")}>
          個人
        </button>
        <button type="button" className={accountType === "enterprise" ? "is-on" : undefined} onClick={() => setAccountType("enterprise")}>
          企業
        </button>
      </div>
      <form className="mpv1-form" onSubmit={onSubmit}>
        <div className="mpv1-field">
          <label htmlFor="name">顯示名稱</label>
          <input id="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
        </div>
        <div className="mpv1-field">
          <label htmlFor="reg-email">Email</label>
          <input id="reg-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="mpv1-field">
          <label htmlFor="reg-pass">密碼</label>
          <input id="reg-pass" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">
          {busy ? "建立中…" : "建立帳號"}
        </button>
      </form>
    </div>
  );
}

export function ForgotPasswordPage() {
  return (
    <div className="mpv1-card mpv1-auth-card">
      <h1 className="mpv1-auth-title">忘記密碼</h1>
      <p className="mpv1-muted">本機預覽不寄送郵件。正式版會透過安全 API 處理重設流程。</p>
      <Link className="mpv1-btn mpv1-btn-primary" style={{ marginTop: "1.25rem" }} to="/login">
        返回登入
      </Link>
    </div>
  );
}

export function PlansPage() {
  const [plans, setPlans] = useState<PlanDto[]>([]);
  useEffect(() => {
    void memberApi.getPlans().then(setPlans);
  }, []);
  return (
    <section>
      <div className="mpv1-page-head">
        <div>
          <h1 className="mpv1-page-title">會員方案</h1>
          <p className="mpv1-page-sub">差異在資訊深度：從總覽結論，到完整證據與團隊能力。</p>
        </div>
      </div>
      <div className="mpv1-plan-grid">
        {plans.map((p) => (
          <article key={p.id} className={`mpv1-card mpv1-plan${p.highlighted ? " is-hot" : ""}`}>
            <h2 className="mpv1-card-title">{p.name}</h2>
            <p className="mpv1-muted">{p.tagline}</p>
            <p style={{ marginTop: "0.85rem", fontWeight: 700 }}>{p.priceLabel}</p>
            <ul>
              {p.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <Link className="mpv1-btn mpv1-btn-soft" style={{ marginTop: "1rem" }} to="/register">
              選擇此方案
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}
