import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { AuthFooter, MarketingFooter, MarketingHeader } from "../layout/Shells";
import { useAuth } from "../context/AuthContext";
import { usePersonalCatalog } from "../hooks/usePersonalCatalog";
import {
  registrationRequiresVerification,
  stagingForgotPassword,
  stagingResendVerification,
  stagingResetPassword,
  stagingVerifyEmail,
} from "../services/stagingApi";
import { IconChart, IconCrown, IconLock, IconMail, IconShield, IconTarget, IconTrend } from "../components/Icons";
import { SparkChart } from "../components/SparkChart";

export function LandingPage() {
  const { catalog } = usePersonalCatalog();
  const previewPlans = catalog?.commercial.plans ?? [];
  const landingPrice = (p: { contact_sales: boolean; monthly_usd: number | null }) =>
    p.contact_sales ? "客製化" : (p.monthly_usd == null || p.monthly_usd === 0) ? "免費" : `$${p.monthly_usd}/月`;
  return (
    <div className="mpv1-auth-shell mpv1-land">
      <MarketingHeader />

      <section className="mpv1-land-hero">
        <div>
          <div
            className="mpv1-chip mpv1-chip-obs"
            style={{ gap: "0.35rem", padding: "0.35rem 0.75rem", fontSize: "0.78rem" }}
          >
            <IconShield size={14} /> 全球加密市場情報平台
          </div>
          <h1>看懂市場，再做決定</h1>
          <p className="mpv1-land-lead">公開市場資料、成員觀察清單與官方市場新聞。</p>
          <ul className="mpv1-feature-list" style={{ marginTop: "1.15rem", color: "var(--mp-text)" }}>
            <li>
              <span className="mpv1-ico" aria-hidden>
                <IconTrend size={16} />
              </span>
              <div>
                <strong>公開市場資料</strong>
                <span>交易所公開行情</span>
              </div>
            </li>
            <li>
              <span className="mpv1-ico" aria-hidden>
                <IconTarget size={16} />
              </span>
              <div>
                <strong>市場排行</strong>
                <span>依 24h 漲跌、成交量、波動與流動性排序</span>
              </div>
            </li>
            <li>
              <span className="mpv1-ico" aria-hidden>
                <IconShield size={16} />
              </span>
              <div>
                <strong>資料來源透明</strong>
                <span>尚未取得的 NEXUS 觀點不會以假資料呈現</span>
              </div>
            </li>
          </ul>
          <div className="mpv1-land-cta">
            <Link className="mpv1-btn mpv1-btn-primary" to="/register">
              登入
            </Link>
            <Link className="mpv1-btn mpv1-btn-outline" to="/plans">
              查看會員方案
            </Link>
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.75rem 1.1rem",
              marginTop: "0.95rem",
              color: "var(--mp-text-2)",
              fontSize: "0.82rem",
              fontWeight: 600,
            }}
          >
            <span>安全帳號登入</span>
            <span>帳務即將推出</span>
          </div>
        </div>

        <div className="mpv1-preview-panel" data-classification="RUNTIME_REQUIRED">
          <h2>即時市場與成員產品</h2>
          <p>公開市場行情、成員觀察清單和官方新聞會在登入後顯示。</p>
          <p className="mpv1-muted">NEXUS 分數、方向訊號、AI 解讀與風險結論即將推出；在此之前不會以假資料呈現。</p>
          <Link className="mpv1-btn mpv1-btn-outline" to="/login">前往登入</Link>
        </div>
      </section>

      <section className="mpv1-section" id="features">
        <div className="mpv1-section-head">
          <h2>市場到底發生什麼</h2>
          <p>先給結論，再給理由。</p>
        </div>
        <div className="mpv1-pillars">
          <article className="mpv1-pillar">
            <div className="ico">
              <IconTrend size={18} />
            </div>
            <h3>現在市場偏哪邊</h3>
            <p>偏多／偏空／中性，一句話看懂方向。</p>
          </article>
          <article className="mpv1-pillar">
            <div className="ico">
              <IconTarget size={18} />
            </div>
            <h3>哪些幣值得先看</h3>
            <p>用評分與狀態排出今天優先標的。</p>
          </article>
          <article className="mpv1-pillar">
            <div className="ico">
              <IconShield size={18} />
            </div>
            <h3>今天最好先不要做什麼</h3>
            <p>把「先等等」寫清楚，降低追價風險。</p>
          </article>
        </div>
      </section>

      <section className="mpv1-land-band">
        <div className="mpv1-section">
          <div className="mpv1-section-head">
            <h2>我們把複雜資料變成簡單答案</h2>
            <p>總覽、深度分析與風險日曆，對齊日常決策節奏。</p>
          </div>
          <div className="mpv1-value-grid">
            <article className="mpv1-card" style={{ margin: 0 }}>
              <div className="mpv1-card-title" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <IconChart size={16} /> 市場總覽
              </div>
              <p className="mpv1-muted" style={{ margin: "0.45rem 0 0.75rem" }}>
                一眼看懂資金、波動與溫度。
              </p>
              <div style={{ height: 100 }}>
                <SparkChart values={[2.1, 2.15, 2.12, 2.25, 2.3, 2.28, 2.4, 2.38, 2.45]} />
              </div>
              <div className="mpv1-ticker-row" style={{ marginTop: "0.65rem" }}>
                <div className="mpv1-ticker">
                  <div className="sym">市值</div>
                  <div className="px">$2.41T</div>
                </div>
                <div className="mpv1-ticker">
                  <div className="sym">24h</div>
                  <div className="px">$126B</div>
                </div>
              </div>
            </article>

            <article className="mpv1-card" style={{ margin: 0 }}>
              <div className="mpv1-card-title" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <IconTarget size={16} /> 深度分析
              </div>
              <p className="mpv1-muted" style={{ margin: "0.45rem 0 0.75rem" }}>
                把機會拆成可檢查的清單。
              </p>
              <ul className="mpv1-intel-list">
                <li>
                  <span className="bullet">✓</span>
                  <span>技術結構：趨勢與關鍵支撐／壓力</span>
                </li>
                <li>
                  <span className="bullet">✓</span>
                  <span>資金流向：現貨／合約相對強弱</span>
                </li>
                <li>
                  <span className="bullet">✓</span>
                  <span>情緒與鏈上：過熱或過冷的訊號</span>
                </li>
                <li>
                  <span className="bullet warn">!</span>
                  <span>風險標記：波動、解鎖與事件衝突</span>
                </li>
              </ul>
            </article>

            <article className="mpv1-card" style={{ margin: 0 }}>
              <div className="mpv1-card-title" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <IconShield size={16} /> 風險事件日曆
              </div>
              <p className="mpv1-muted" style={{ margin: "0.45rem 0 0.75rem" }}>
                先看今天可能踩到的雷。
              </p>
              <ul className="mpv1-intel-list">
                <li>
                  <span className="bullet warn">•</span>
                  <span>SOL 大量解鎖提醒 · 今日</span>
                </li>
                <li>
                  <span className="bullet warn">•</span>
                  <span>US CPI 數據公布 · 明日</span>
                </li>
                <li>
                  <span className="bullet">•</span>
                  <span>BTC 期權到期週 · 本週</span>
                </li>
                <li>
                  <span className="bullet">•</span>
                  <span>穩定幣流動性異常觀察</span>
                </li>
              </ul>
            </article>
          </div>
        </div>
      </section>

      <section className="mpv1-section">
        <div className="mpv1-section-head">
          <h2>選擇最適合你的會員方案</h2>
          <p>從免費入門到完整證據，依需求開通深度。</p>
        </div>
        <div className="mpv1-plan-grid">
          {previewPlans.filter((p) => p.code !== "enterprise").map((p) => {
            const hot = p.code === "pro";
            const copy = PLAN_COPY[p.code] ?? { audience: "—", daily: "—" };
            return (
              <article key={p.code} className={`mpv1-plan${hot ? " is-hot" : ""}`}>
                {hot ? <div className="mpv1-plan-badge">最受歡迎</div> : null}
                <h3 className="mpv1-card-title">{p.display_name}</h3>
                <div className="price">{landingPrice(p)}</div>
                <p className="audience">{copy.daily}</p>
                <Link
                  className={`mpv1-btn ${hot ? "mpv1-btn-primary" : "mpv1-btn-outline"} mpv1-btn-block`}
                  to="/plans"
                >
                  查看詳情
                </Link>
              </article>
            );
          })}
        </div>
        {/* Enterprise is a separate product / sales path — not a Personal tier. */}
        <p className="mpv1-muted" style={{ textAlign: "center", marginTop: "0.85rem" }}>
          團隊與組織需求？<Link to="/plans">了解 NEXUS Enterprise（洽詢）</Link>
        </p>
      </section>

      <section className="mpv1-land-band" id="faq">
        <div className="mpv1-section">
          <div className="mpv1-trust-row">
            <div className="mpv1-trust-item">
              <IconShield size={22} />
              <strong>不下單、不託管</strong>
              <span>情報平台，專注看懂市場與風險</span>
            </div>
            <div className="mpv1-trust-item">
              <IconChart size={22} />
              <strong>結論優先</strong>
              <span>複雜度留在底下，初學者也讀得懂</span>
            </div>
            <div className="mpv1-trust-item">
              <IconLock size={22} />
              <strong>資料屬於你</strong>
              <span>隱私與安全加密為預設原則</span>
            </div>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}

function AuthFinancialDeco({ patternId = "mpv1DotGrid" }: { patternId?: string }) {
  const softId = `${patternId}-soft`;
  return (
    <div className="mpv1-auth-deco" aria-hidden>
      <svg className="mpv1-auth-deco-svg" viewBox="0 0 480 640" preserveAspectRatio="xMidYMid slice">
        <defs>
          <pattern id={patternId} width="18" height="18" patternUnits="userSpaceOnUse">
            <circle cx="1.2" cy="1.2" r="1.1" fill="rgba(191,219,254,0.22)" />
          </pattern>
          <linearGradient id={softId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="rgba(96,165,250,0.18)" />
            <stop offset="100%" stopColor="rgba(37,99,235,0.05)" />
          </linearGradient>
        </defs>
        <rect width="480" height="640" fill={`url(#${patternId})`} />
        <rect x="40" y="280" width="400" height="280" rx="24" fill={`url(#${softId})`} />
        <polyline
          fill="none"
          stroke="rgba(147,197,253,0.42)"
          strokeWidth="2"
          points="60,520 110,490 150,505 200,430 250,450 300,360 350,390 400,310 440,330"
        />
        {[
          [90, 470, 500, true],
          [130, 455, 495, false],
          [170, 440, 480, true],
          [210, 400, 460, true],
          [250, 420, 470, false],
          [290, 350, 430, true],
          [330, 370, 440, false],
          [370, 300, 390, true],
          [410, 315, 400, true],
        ].map(([x, o, c, up], i) => {
          const top = Math.min(o as number, c as number);
          const bot = Math.max(o as number, c as number);
          const color = up ? "rgba(52,211,153,0.38)" : "rgba(248,113,113,0.34)";
          return (
            <g key={i}>
              <line x1={x as number} x2={x as number} y1={top - 18} y2={bot + 18} stroke={color} strokeWidth="1.3" />
              <rect x={(x as number) - 6} y={top} width="12" height={Math.max(8, bot - top)} rx="1.5" fill={color} />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function AuthLeftBrand({
  title,
  lead,
  features,
}: {
  title: string;
  lead: string;
  features: Array<{ Icon: typeof IconTrend; title: string; body: string }>;
}) {
  return (
    <aside className="mpv1-auth-left">
      <AuthFinancialDeco />
      <div className="mpv1-auth-left-inner">
        <div className="mpv1-logo" style={{ color: "#fff" }}>
          NEXUS
        </div>
        <h1>{title}</h1>
        <p className="mpv1-lead">{lead}</p>
        <ul className="mpv1-feature-list">
          {features.map((f) => (
            <li key={f.title}>
              <span className="mpv1-ico" aria-hidden>
                <f.Icon size={16} />
              </span>
              <div>
                <strong>{f.title}</strong>
                <span>{f.body}</span>
              </div>
            </li>
          ))}
        </ul>
        <div className="mpv1-secure-badge">
          <IconShield size={15} /> 安全可靠 · 嚴格保護您的資料與資產
        </div>
      </div>
    </aside>
  );
}

export function LoginPage() {
  const { login, session } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (session) return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      nav("/app");
    } catch {
      setError("Email 或密碼錯誤");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mpv1-auth-shell">
      <div className="mpv1-d-only">
        <MarketingHeader active="login" />
        <div className="mpv1-auth-body">
          <AuthLeftBrand
            title="看懂市場，才好做決定"
            lead="加密市場情報與交易洞察平台"
            features={[
              { Icon: IconTrend, title: "快速掌握市場方向", body: "即時洞察市場趨勢，掌握關鍵機會。" },
              { Icon: IconChart, title: "把複雜數據變簡單", body: "圖表與指標清晰呈現，輕鬆理解不費力。" },
              { Icon: IconCrown, title: "依會員等級開通不同功能", body: "彈性方案滿足不同需求，解鎖更多專業工具。" },
            ]}
          />
          <section className="mpv1-auth-right">
            <div className="mpv1-auth-card">
              <h2>會員登入</h2>
              <p className="mpv1-sub">歡迎回來！請登入您的帳號以繼續使用 NEXUS</p>
              <form onSubmit={onSubmit}>
                <div className="mpv1-field">
                  <label htmlFor="email">電子郵件</label>
                  <div className="mpv1-input">
                    <span className="mpv1-input-ico">
                      <IconMail size={15} />
                    </span>
                    <input
                      id="email"
                      type="email"
                      placeholder="請輸入電子郵件"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                    />
                  </div>
                </div>
                <div className="mpv1-field">
                  <label htmlFor="password">密碼</label>
                  <div className="mpv1-input">
                    <span className="mpv1-input-ico">
                      <IconLock size={15} />
                    </span>
                    <input
                      id="password"
                      type={show ? "text" : "password"}
                      placeholder="請輸入密碼"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                    <button type="button" className="mpv1-link" onClick={() => setShow((v) => !v)}>
                      {show ? "隱藏" : "顯示"}
                    </button>
                  </div>
                </div>
                <div className="mpv1-row-between">
                  <label className="mpv1-check">
                    <input type="checkbox" defaultChecked /> 記住我
                  </label>
                  <Link className="mpv1-link" to="/forgot-password">
                    忘記密碼？
                  </Link>
                </div>
                <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">
                  {busy ? "登入中…" : "登入"}
                </button>
                {error ? <p className="mpv1-auth-error" role="alert">{error}</p> : null}
              </form>
              <p className="mpv1-sub">僅限已佈建帳號登入。</p>
            </div>
          </section>
        </div>
        <AuthFooter />
      </div>

      <div className="mpv1-m-login mpv1-m-only">
        <div className="mpv1-m-login-bg" aria-hidden />
        <header className="mpv1-m-login-top">
          <div className="mpv1-logo">NEXUS</div>
          <button type="button" className="mpv1-m-iconbtn" aria-label="說明">
            ?
          </button>
        </header>
        <div className="mpv1-m-login-hero">
          <h1>歡迎回來</h1>
          <p>查看今天市場重點與你的觀察清單</p>
        </div>

        <p className="mpv1-m-passkey-hint">目前採邀請制，帳號由管理員開通後以電子郵件與密碼登入。</p>

        <form onSubmit={onSubmit} className="mpv1-m-login-form">
          <div className="mpv1-field">
            <label htmlFor="m-email">電子郵件</label>
            <div className="mpv1-input">
              <span className="mpv1-input-ico"><IconMail size={15} /></span>
              <input id="m-email" type="email" placeholder="name@email.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
          </div>
          <div className="mpv1-field">
            <label htmlFor="m-password">密碼</label>
            <div className="mpv1-input">
              <span className="mpv1-input-ico"><IconLock size={15} /></span>
              <input id="m-password" type={show ? "text" : "password"} placeholder="請輸入密碼" value={password} onChange={(e) => setPassword(e.target.value)} required />
              <button type="button" className="mpv1-link" onClick={() => setShow((v) => !v)}>{show ? "隱藏" : "顯示"}</button>
            </div>
          </div>
          <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">
            {busy ? "登入中…" : "登入"}
          </button>
          {error ? <p className="mpv1-auth-error" role="alert">{error}</p> : null}
        </form>

        <p className="mpv1-m-recover">
          登入遇到問題？ <Link to="/forgot-password">找回帳號 / 忘記密碼</Link>
        </p>
        <p className="mpv1-m-register">
          僅限已佈建帳號登入
        </p>

        <footer className="mpv1-m-trust">
          <div>安全登入 · 支援 Passkey / 2FA</div>
          <div>資料加密傳輸</div>
          <div>NEXUS 不透過登入要求交易所 API Key</div>
        </footer>
      </div>
    </div>
  );
}

export function RegisterPage() {
  const { register, session } = useAuth();
  const nav = useNavigate();
  const [accountType, setAccountType] = useState<"individual" | "enterprise">("individual");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (session) return <Navigate to="/app" replace />;
  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-page-pad">
        <div className="mpv1-auth-card" style={{ margin: "2rem auto" }}>
          <h2>建立帳號</h2>
          <p className="mpv1-sub">目前採邀請制，尚未開放公開註冊。</p>
          <form onSubmit={(event) => void onSubmit(event)}>
            <label className="mpv1-field">名稱<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required maxLength={120} /></label>
            <label className="mpv1-field">Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
            <label className="mpv1-field">密碼<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} /></label>
            <label className="mpv1-field">確認密碼<input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required minLength={12} /></label>
            <details className="mpv1-field">
              <summary>Founder 初始化（選填）</summary>
              <input aria-label="Founder Claim Code" type="password" value={phone} onChange={(event) => setPhone(event.target.value)} />
            </details>
            {err ? <p className="mpv1-auth-error" role="alert">{err}</p> : null}
            <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">{busy ? "建立中…" : "建立帳號"}</button>
          </form>
          <p className="mpv1-sub">已有帳號？ <Link to="/login">登入</Link></p>
        </div>
      </div>
      <AuthFooter />
    </div>
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password.length < 12 || password.length > 128) {
      setErr("密碼至少需為 12 字元");
      return;
    }
    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
      setErr("密碼需英數混合");
      return;
    }
    if (password !== confirm) {
      setErr("兩次密碼不一致");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      const result = await register({ email, password, confirmPassword: confirm, displayName, founderClaimCode: phone || undefined });
      if (registrationRequiresVerification(result)) {
        // Pending verification: no usable session. Route to the check-email
        // page, passing the email via router state only (never URL/storage).
        nav("/check-email", { state: { email } });
      } else {
        nav("/app");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-auth-body">
        <aside className="mpv1-auth-left">
          <AuthFinancialDeco patternId="mpv1DotGridReg" />
          <div className="mpv1-auth-left-inner">
            <div className="mpv1-logo" style={{ color: "#fff" }}>
              NEXUS
            </div>
            <h1>三步驟，開啟您的情報之旅</h1>
            <p className="mpv1-lead">快速、安全地完成註冊，立即開始使用市場情報。</p>
            <div className="mpv1-auth-left-steps">
              {[
                ["1", "建立帳號", "填寫基本資料，快速建立您的專屬帳號"],
                ["2", "選擇會員方案", "依需求選擇最適合的會員方案與服務"],
                ["3", "開始使用", "完成註冊後，即可使用 NEXUS 各項功能"],
              ].map(([n, t, d]) => (
                <div className="step" key={n}>
                  <span className="bubble">{n}</span>
                  <div>
                    <strong>{t}</strong>
                    <span style={{ display: "block", opacity: 0.85, fontSize: "0.82rem", marginTop: "0.15rem" }}>
                      {d}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mpv1-trust-row">
              <div>
                <IconShield size={14} /> 安全可靠
              </div>
              <div>
                <IconTrend size={14} /> 快速上手
              </div>
              <div>
                <IconCrown size={14} /> 專業支援
              </div>
            </div>
          </div>
        </aside>
        <section className="mpv1-auth-right">
          <div className="mpv1-auth-card">
            <h2>建立新帳號</h2>
            <div className="mpv1-steps">
              <span className="is-on">
                <i>1</i>填寫資料
              </span>
              <span>
                <i>2</i>確認驗證
              </span>
              <span>
                <i>3</i>完成註冊
              </span>
            </div>
            <div className="mpv1-seg">
              <button
                type="button"
                className={accountType === "individual" ? "is-on" : undefined}
                onClick={() => setAccountType("individual")}
              >
                個人會員
              </button>
              <button
                type="button"
                className={accountType === "enterprise" ? "is-on" : undefined}
                onClick={() => setAccountType("enterprise")}
              >
                企業會員
              </button>
            </div>
            <form onSubmit={onSubmit}>
              <div className="mpv1-field">
                <label htmlFor="reg-name">姓名</label>
                <div className="mpv1-input">
                  <input
                    id="reg-name"
                    placeholder="請輸入您的姓名"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label htmlFor="reg-email">電子郵件</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">
                    <IconMail size={15} />
                  </span>
                  <input
                    id="reg-email"
                    type="email"
                    placeholder="請輸入電子郵件"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label htmlFor="reg-phone">手機號碼</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">TW</span>
                  <input
                    id="reg-phone"
                    placeholder="請輸入手機號碼"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label htmlFor="reg-password">密碼</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">
                    <IconLock size={15} />
                  </span>
                  <input
                    id="reg-password"
                    type="password"
                    placeholder="8-20 字元英數混合"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    maxLength={20}
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label htmlFor="reg-confirm">確認密碼</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">
                    <IconLock size={15} />
                  </span>
                  <input
                    id="reg-confirm"
                    type="password"
                    placeholder="再次輸入密碼"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                  />
                </div>
              </div>
              <label className="mpv1-check" style={{ marginBottom: "0.85rem" }}>
                <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
                我已閱讀並同意《服務條款》與《隱私權政策》
              </label>
              {err ? (
                <p className="mpv1-muted" style={{ color: "#dc2626", marginBottom: "0.75rem" }}>
                  {err}
                </p>
              ) : null}
              <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">
                {busy ? "建立中…" : "立即註冊"}
              </button>
            </form>
            <p className="mpv1-sub" style={{ marginTop: "1rem", marginBottom: 0 }}>
              已經有帳號？
              <Link className="mpv1-link" to="/login">
                立即登入
              </Link>
            </p>
          </div>
        </section>
      </div>
      <AuthFooter />
    </div>
  );
}

function AuthCard({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-page-pad">
        <div className="mpv1-auth-card" style={{ margin: "2rem auto" }}>
          <h2>{title}</h2>
          {sub ? <p className="mpv1-sub">{sub}</p> : null}
          {children}
        </div>
      </div>
      <AuthFooter />
    </div>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      // Response is intentionally generic (enumeration resistant); always show
      // the same confirmation regardless of whether the account exists.
      await stagingForgotPassword(email.trim().toLowerCase());
      setDone(true);
    } finally {
      setBusy(false);
    }
  }
  if (done) {
    return (
      <AuthCard title="忘記密碼" sub="如果該 Email 對應到一個帳號，我們已寄出密碼重設連結。請檢查你的信箱（連結一小時內有效）。">
        <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/login">返回登入</Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="忘記密碼" sub="輸入你的 Email，我們會寄出密碼重設連結。">
      <form onSubmit={(event) => void onSubmit(event)}>
        <label className="mpv1-field">Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">{busy ? "送出中…" : "寄送重設連結"}</button>
      </form>
      <p className="mpv1-sub">想起來了？ <Link to="/login">返回登入</Link></p>
    </AuthCard>
  );
}

export function PendingVerificationPage() {
  const location = useLocation();
  const prefill = (location.state as { email?: string } | null)?.email || "";
  const [email, setEmail] = useState(prefill);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  async function onResend(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await stagingResendVerification(email.trim().toLowerCase());
      setSent(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthCard title="請確認你的 Email" sub="我們已寄出一封驗證信。請點擊信中的連結完成帳號啟用（連結 24 小時內有效）。">
      {sent ? (
        <p className="mpv1-sub">如果該 Email 尚未驗證，我們已重新寄出驗證連結。</p>
      ) : (
        <form onSubmit={(event) => void onResend(event)}>
          <label className="mpv1-field">沒收到信？重新寄送<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <button className="mpv1-btn mpv1-btn-secondary mpv1-btn-block" disabled={busy} type="submit">{busy ? "寄送中…" : "重新寄送驗證信"}</button>
        </form>
      )}
      <p className="mpv1-sub"><Link to="/login">返回登入</Link></p>
    </AuthCard>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [state, setState] = useState<"working" | "ok" | "invalid">("working");
  useEffect(() => {
    let active = true;
    if (!token) {
      setState("invalid");
      return;
    }
    void stagingVerifyEmail(token).then((res) => {
      if (active) setState(res.ok ? "ok" : "invalid");
    });
    return () => {
      active = false;
    };
  }, [token]);
  if (state === "working") {
    return <AuthCard title="驗證中…" sub="正在確認你的 Email 驗證連結。" >{null}</AuthCard>;
  }
  if (state === "ok") {
    return (
      <AuthCard title="Email 已驗證" sub="你的帳號已啟用，現在可以登入。">
        <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/login">前往登入</Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="連結無效或已過期" sub="這個驗證連結無法使用。你可以重新寄送一封新的驗證信。">
      <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/check-email">重新寄送驗證信</Link>
    </AuthCard>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (password.length < 12) {
      setErr("密碼至少需為 12 字元");
      return;
    }
    if (password !== confirm) {
      setErr("兩次密碼不一致");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      const res = await stagingResetPassword(token, password);
      if (res.ok) {
        setDone(true);
      } else if (res.code === "weak_password") {
        setErr("密碼強度不足");
      } else {
        setErr("重設連結無效或已過期，請重新申請。");
      }
    } finally {
      setBusy(false);
    }
  }
  if (!token) {
    return <AuthCard title="重設密碼" sub="缺少有效的重設連結。請重新申請忘記密碼。"><Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/forgot-password">前往忘記密碼</Link></AuthCard>;
  }
  if (done) {
    return (
      <AuthCard title="密碼已更新" sub="你的密碼已重設，且所有既有登入工作階段皆已登出。請用新密碼登入。">
        <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/login">前往登入</Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="重設密碼" sub="請設定新密碼（至少 12 字元）。">
      <form onSubmit={(event) => void onSubmit(event)}>
        <label className="mpv1-field">新密碼<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} /></label>
        <label className="mpv1-field">確認新密碼<input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} required minLength={12} /></label>
        {err ? <p className="mpv1-auth-error" role="alert">{err}</p> : null}
        <button className="mpv1-btn mpv1-btn-primary mpv1-btn-block" disabled={busy} type="submit">{busy ? "更新中…" : "更新密碼"}</button>
      </form>
    </AuthCard>
  );
}

// Presentation copy only (audience/taglines). Canonical PRICING and identity come
// from the backend catalog — never hard-coded here.
const PLAN_COPY: Record<string, { audience: string; daily: string }> = {
  free: { audience: "剛開始了解市場的你", daily: "掌握市場方向與重點" },
  starter: { audience: "想每天快速看懂市場的你", daily: "市場狀態、關注清單與提醒" },
  pro: { audience: "需要更深證據與工具的你", daily: "更完整的證據與市場深度" },
  advanced: { audience: "重度使用者與專業交易者", daily: "最深的排行、風險與資料" },
  enterprise: { audience: "團隊與機構", daily: "組織權限與整合（洽詢）" },
};

export function PlansPage() {
  const { catalog } = usePersonalCatalog();
  const allPlans = catalog?.commercial.plans ?? [];
  // Enterprise is a SEPARATE product, not the top Personal tier. Personal plans are
  // Free / Starter / Pro / Advanced; Enterprise is presented in its own section.
  const personalPlans = allPlans.filter((p) => p.code !== "enterprise");
  const enterprisePlan = allPlans.find((p) => p.code === "enterprise");
  const priceLabel = (p: { contact_sales: boolean; monthly_usd: number | null }) =>
    p.contact_sales ? "聯絡我們" : (p.monthly_usd == null || p.monthly_usd === 0) ? "免費" : `$${p.monthly_usd}/月`;

  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader active="plans" />
      <section className="mpv1-plans-hero">
        <div>
          <h1>選擇適合你的會員方案</h1>
          <p>不同層級，對應不同深度的市場工具與決策支援。隨時可升級，隨時可取消。</p>
        </div>
        <div style={{ display: "grid", gap: "0.55rem", color: "#bfdbfe", fontSize: "0.88rem" }}>
          <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
            <IconShield size={15} /> 安全可靠
          </div>
          <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
            <IconTrend size={15} /> 隨時可升級
          </div>
          <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
            <IconLock size={15} /> 資料只屬於你
          </div>
        </div>
      </section>

      <div className="mpv1-plans-wrap">
        <div className="mpv1-value-grid">
          {[
            ["市場方向", "快速掌握偏多 / 偏空 / 不明"],
            ["值得關注的幣種", "找出相對強勢或異常波動的標的"],
            ["今天先不要做什麼", "降低雜訊與不必要風險"],
          ].map(([t, b]) => (
            <article key={t} className="mpv1-card">
              <h3 className="mpv1-card-title">{t}</h3>
              <p className="mpv1-muted">{b}</p>
            </article>
          ))}
        </div>

        <div className="mpv1-plan-grid">
          {personalPlans.map((p) => {
            const hot = p.code === "pro";
            const copy = PLAN_COPY[p.code] ?? { audience: "—", daily: "—" };
            return (
              <article key={p.code} className={`mpv1-plan${hot ? " is-hot" : ""}`}>
                {hot ? <div className="mpv1-plan-badge">最受歡迎</div> : null}
                <h3 className="mpv1-card-title">{p.display_name}</h3>
                <div className="price">{priceLabel(p)}</div>
                <div className="audience">適合誰：{copy.audience}</div>
                <div className="daily">每天：{copy.daily}</div>
                <Link className={`mpv1-btn ${hot ? "mpv1-btn-primary" : "mpv1-btn-outline"} mpv1-btn-block`} to="/register">
                  選擇此方案
                </Link>
              </article>
            );
          })}
        </div>
        <p className="mpv1-muted" style={{ textAlign: "center", marginTop: "0.75rem" }}>價格採年繳約 8 折；線上訂閱即將開放。</p>

        {/* Enterprise is a SEPARATE product with its own sales path — never the next
            Personal subscription level. Contact-sales only (no self-service checkout). */}
        <section className="mpv1-enterprise-band">
          <div>
            <span className="mpv1-enterprise-eyebrow">為團隊與組織</span>
            <h3>{enterprisePlan?.display_name ?? "NEXUS Enterprise"}</h3>
            <p className="mpv1-muted">為團隊與機構提供的獨立方案：組織權限、成員管理與整合能力。部分企業功能仍在開發中，將以誠實的狀態呈現。採洽詢報價，非線上自助訂閱。</p>
          </div>
          <Link className="mpv1-btn mpv1-btn-primary" to="/register">聯絡我們</Link>
        </section>

        <table className="mpv1-compare">
          <thead>
            <tr>
              <th>個人方案功能比較</th>
              <th>入門版</th>
              <th>進階版</th>
              <th>專業版</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["市場總覽", "✓", "✓", "✓"],
              ["排行深度", "Top 20", "Top 50", "Top 100"],
              ["今日重點", "✓", "✓", "✓"],
              ["進出場觀察", "—", "✓", "✓"],
              ["風險提醒", "基礎", "進階", "即時"],
              ["觀察清單", "10", "50", "無上限"],
              ["歷史回溯", "—", "30 天", "180 天"],
              ["完整證據", "—", "—", "✓"],
            ].map((row) => (
              <tr key={row[0]}>
                {row.map((cell) => (
                  <td key={`${row[0]}-${cell}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mpv1-muted" style={{ textAlign: "center", marginTop: "1.25rem" }}>
          所有方案皆支援安全加密與隱私保護，你的資料只屬於你。
        </p>
      </div>
      <MarketingFooter />
    </div>
  );
}
