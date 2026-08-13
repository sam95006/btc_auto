import { Link, Navigate, useNavigate } from "react-router-dom";
import { useEffect, useState, type FormEvent } from "react";
import { MarketingFooter, MarketingHeader } from "../layout/Shells";
import { useAuth } from "../context/AuthContext";
import { memberApi } from "../services";
import type { PlanDto } from "../types/dto";
import { IconChart, IconCrown, IconLock, IconMail, IconShield, IconTarget, IconTrend } from "../components/Icons";
import { SparkChart } from "../components/SparkChart";

export function LandingPage() {
  return (
    <div className="mpv1-auth-shell mpv1-land">
      <MarketingHeader />
      <section className="mpv1-land-hero">
        <div>
          <div className="mpv1-land-kicker">CRYPTO MARKET INTELLIGENCE</div>
          <h1>看懂市場，再做決定</h1>
          <p className="mpv1-land-lead">
            NEXUS 把複雜行情翻譯成白話結論：市場偏哪邊、哪些幣先看、今天最好先不要做什麼。給初學者結論，給進階者理由，給專業者完整證據。
          </p>
          <div className="mpv1-land-cta">
            <Link className="mpv1-btn mpv1-btn-primary" to="/register">
              開始使用
            </Link>
            <Link className="mpv1-btn mpv1-btn-outline" to="/plans">
              會員方案
            </Link>
            <Link className="mpv1-btn mpv1-btn-ghost" to="/login">
              已有帳號
            </Link>
          </div>
        </div>

        <div className="mpv1-preview-panel" aria-label="產品預覽">
          <div className="mpv1-preview-top">
            <div className="mpv1-preview-kpi">
              <div className="lbl">市場狀態</div>
              <div className="val bull">偏多</div>
            </div>
            <div className="mpv1-preview-kpi">
              <div className="lbl">最佳機會</div>
              <div className="val">ETH · 84</div>
            </div>
            <div className="mpv1-preview-kpi">
              <div className="lbl">市場風險</div>
              <div className="val warn">中等</div>
            </div>
          </div>
          <div className="mpv1-preview-chart">
            <SparkChart values={[2.05, 2.1, 2.08, 2.18, 2.22, 2.2, 2.3, 2.35, 2.41]} tone="accent" />
          </div>
          <div className="mpv1-preview-assets">
            {[
              ["ETH", "+2.8%", "可留意"],
              ["AVAX", "+3.3%", "可留意"],
              ["SOL", "+4.1%", "觀察中"],
            ].map(([sym, chg, st]) => (
              <div key={sym} className="mpv1-preview-asset">
                <strong>{sym}</strong>
                <span style={{ color: "#34d399" }}>{chg}</span>
                <span style={{ color: "#93c5fd" }}>{st}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mpv1-section" id="features">
        <div className="mpv1-section-head">
          <h2>市場到底發生什麼</h2>
          <p>我們把複雜資料變成簡單答案——先告訴你結論，再讓你決定要不要往下看。</p>
        </div>
        <div className="mpv1-pillars">
          <article className="mpv1-pillar">
            <div className="ico">
              <IconTrend size={18} />
            </div>
            <h3>現在市場偏哪邊</h3>
            <p>偏多／偏空／不明，搭配風險等級與一句白話說明。</p>
          </article>
          <article className="mpv1-pillar">
            <div className="ico">
              <IconTarget size={18} />
            </div>
            <h3>哪些幣值得先看</h3>
            <p>用評分、狀態與一句理由，排出今天該優先觀察的標的。</p>
          </article>
          <article className="mpv1-pillar">
            <div className="ico">
              <IconShield size={18} />
            </div>
            <h3>今天最好先不要做什麼</h3>
            <p>降低雜訊與追價風險，把「先等等」也寫清楚。</p>
          </article>
        </div>
      </section>

      <section className="mpv1-land-band">
        <div className="mpv1-section">
          <div className="mpv1-section-head">
            <h2>真實產品介面預覽</h2>
            <p>不是空泛文案——總覽、排行、風險提醒都為日常決策密度而設計。</p>
          </div>
          <div className="mpv1-ui-shot">
            <div className="mpv1-ui-shot-bar">
              <span>NEXUS · 總覽</span>
              <span>市場偏多</span>
              <span>風險中等</span>
            </div>
            <div className="mpv1-ui-shot-body">
              <div className="mpv1-card" style={{ margin: 0 }}>
                <div className="mpv1-card-title">Market Pulse</div>
                <div style={{ height: 120, marginTop: "0.5rem" }}>
                  <SparkChart values={[2.1, 2.15, 2.12, 2.25, 2.3, 2.28, 2.4]} />
                </div>
                <div className="mpv1-ticker-row">
                  <div className="mpv1-ticker">
                    <div className="sym">BTC</div>
                    <div className="px">$68,450</div>
                  </div>
                  <div className="mpv1-ticker">
                    <div className="sym">ETH</div>
                    <div className="px">$3,420</div>
                  </div>
                  <div className="mpv1-ticker">
                    <div className="sym">SOL</div>
                    <div className="px">$168</div>
                  </div>
                </div>
              </div>
              <div className="mpv1-card" style={{ margin: 0 }}>
                <div className="mpv1-card-title">Today in Plain Language</div>
                <div className="mpv1-plain-grid" style={{ marginTop: "0.65rem", gridTemplateColumns: "1fr" }}>
                  <div className="mpv1-plain-item">
                    <h4>今天市場正在發生什麼</h4>
                    <p>大型幣整體偏多，資金集中在少數相對強勢標的。</p>
                  </div>
                  <div className="mpv1-plain-item caution">
                    <h4>今天先不要做什麼</h4>
                    <p>不要追高波動、已大漲且風險偏高的幣。</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mpv1-section">
        <div className="mpv1-section-head">
          <h2>會員方案預覽</h2>
          <p>依需求開通深度：結論 → 理由 → 完整證據。</p>
        </div>
        <div className="mpv1-plan-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
          {[
            ["入門版", "NT$ 299", "市場方向與精選排行"],
            ["專業版", "NT$ 1,599", "完整證據與即時風險"],
            ["企業版", "聯絡我們", "團隊權限與整合諮詢"],
          ].map(([n, p, d]) => (
            <article key={n} className={`mpv1-plan${n === "專業版" ? " is-hot" : ""}`}>
              {n === "專業版" ? <div className="mpv1-plan-badge">推薦</div> : null}
              <h3 className="mpv1-card-title">{n}</h3>
              <div className="price">{p}</div>
              <p className="audience">{d}</p>
              <Link className="mpv1-btn mpv1-btn-outline mpv1-btn-block" to="/plans">
                查看詳情
              </Link>
            </article>
          ))}
        </div>
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
  const [email, setEmail] = useState("founder@nexus.local");
  const [password, setPassword] = useState("demo");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  if (session) return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await login(email, password);
      nav("/app");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mpv1-auth-shell">
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
                {busy ? "登入中…" : "登入 NEXUS"}
              </button>
            </form>
            <div className="mpv1-divider">或</div>
            <Link className="mpv1-btn mpv1-btn-outline mpv1-btn-block" to="/register">
              建立新帳號
            </Link>
            <button type="button" className="mpv1-btn mpv1-btn-ghost mpv1-btn-block" style={{ marginTop: "0.65rem" }}>
              使用 Google 帳號登入
            </button>
          </div>
        </section>
      </div>
      <MarketingFooter />
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

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!agree) {
      setErr("請先同意服務條款與隱私權政策");
      return;
    }
    if (password !== confirm) {
      setErr("兩次密碼不一致");
      return;
    }
    setErr("");
    setBusy(true);
    try {
      await register({ email, password, displayName, accountType });
      nav("/app");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-auth-body">
        <aside className="mpv1-auth-left">
          <div className="mpv1-auth-left-inner">
            <div className="mpv1-logo" style={{ color: "#fff" }}>
              NEXUS
            </div>
            <h1>三步驟，開啟您的情報之旅</h1>
            <p className="mpv1-lead">快速、安全地完成註冊，立即開始使用市場情報。</p>
            <div className="mpv1-auth-left-steps">
              {[
                ["1", "建立帳號"],
                ["2", "選擇會員方案"],
                ["3", "開始使用"],
              ].map(([n, t]) => (
                <div className="step" key={n}>
                  <span className="bubble">{n}</span>
                  <strong>{t}</strong>
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
                <label>姓名</label>
                <div className="mpv1-input">
                  <input
                    placeholder="請輸入您的姓名"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label>電子郵件</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">
                    <IconMail size={15} />
                  </span>
                  <input
                    type="email"
                    placeholder="請輸入電子郵件"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label>手機號碼</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">TW</span>
                  <input placeholder="請輸入手機號碼" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </div>
              </div>
              <div className="mpv1-field">
                <label>密碼</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">
                    <IconLock size={15} />
                  </span>
                  <input
                    type="password"
                    placeholder="8-20 字元英數混合"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
              </div>
              <div className="mpv1-field">
                <label>確認密碼</label>
                <div className="mpv1-input">
                  <span className="mpv1-input-ico">
                    <IconLock size={15} />
                  </span>
                  <input
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
      <MarketingFooter />
    </div>
  );
}

export function ForgotPasswordPage() {
  return (
    <div className="mpv1-auth-shell">
      <MarketingHeader />
      <div className="mpv1-page-pad">
        <div className="mpv1-auth-card" style={{ margin: "2rem auto" }}>
          <h2>忘記密碼</h2>
          <p className="mpv1-sub">本機預覽不寄送郵件。正式版會透過安全 API 處理重設流程。</p>
          <Link className="mpv1-btn mpv1-btn-primary mpv1-btn-block" to="/login">
            返回登入
          </Link>
        </div>
      </div>
      <MarketingFooter />
    </div>
  );
}

export function PlansPage() {
  const [plans, setPlans] = useState<PlanDto[]>([]);
  useEffect(() => {
    void memberApi.getPlans().then(setPlans);
  }, []);

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
          {plans.map((p) => {
            const hot = p.id === "professional";
            return (
              <article key={p.id} className={`mpv1-plan${hot ? " is-hot" : ""}`}>
                {hot ? <div className="mpv1-plan-badge">最多人選擇</div> : null}
                <h3 className="mpv1-card-title">{p.name}</h3>
                <div className="price">{p.priceLabel}</div>
                <div className="audience">適合誰：{p.audience}</div>
                <div className="daily">每天：{p.dailyValue}</div>
                <ul>
                  {p.features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                <Link className={`mpv1-btn ${hot ? "mpv1-btn-primary" : "mpv1-btn-outline"} mpv1-btn-block`} to="/register">
                  {p.id === "enterprise" ? "聯絡我們" : "選擇此方案"}
                </Link>
              </article>
            );
          })}
        </div>

        <table className="mpv1-compare">
          <thead>
            <tr>
              <th>功能比較</th>
              <th>入門版</th>
              <th>進階版</th>
              <th>專業版</th>
              <th>企業版</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["市場總覽", "✓", "✓", "✓", "✓"],
              ["排行深度", "Top 20", "Top 50", "Top 100", "Top 100"],
              ["今日重點", "✓", "✓", "✓", "✓"],
              ["進出場觀察", "—", "✓", "✓", "✓"],
              ["風險提醒", "基礎", "進階", "即時", "即時"],
              ["觀察清單", "10", "50", "無上限", "無上限"],
              ["歷史回溯", "—", "30 天", "180 天", "180 天"],
              ["完整證據", "—", "—", "✓", "✓"],
              ["團隊管理", "—", "—", "—", "✓"],
              ["API / Bridge", "—", "—", "—", "✓"],
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
