import { Link } from "react-router-dom";

/** Wave 4 — Learning hub with AiLearningLab integration. */
export function LearningPage() {
  const topics = [
    { t: "指標與 OHLCV 基礎", href: "/academy" },
    { t: "Funding／OI／CVD 白話說明", href: "/academy" },
    { t: "為何 Risk Gate 會擋進場", href: "/trade-plan" },
    { t: "如何閱讀 AI 證據（三層）", href: "/opportunities" },
    { t: "平台操作：總覽 → 機會 → 標的工作台", href: "/overview" },
    { t: "AI Learning Lab（自適應政策 shadow）", href: "/ai-learning-lab" },
  ];
  return (
    <div className="page-stack nx-learning-p7 nx-learning-w4">
      <header>
        <h1>學習</h1>
        <p className="muted">教育內容 · 連結學院、Lab 與證據頁 · 非投資建議</p>
      </header>
      <ul className="nx-learning-list">
        {topics.map((row) => (
          <li key={row.t}>
            <Link to={row.href}>{row.t}</Link>
          </li>
        ))}
      </ul>
      <section className="nx-card" aria-label="AiLearningLab embed">
        <h2 className="nx-sec-title">AI Learning Lab</h2>
        <p className="muted sm">固定 25x shadow · 只讀 metrics · 非 EXECUTED</p>
        <Link to="/ai-learning-lab" className="nx-p7-ai-btn">
          開啟 AI Learning Lab →
        </Link>
      </section>
    </div>
  );
}
