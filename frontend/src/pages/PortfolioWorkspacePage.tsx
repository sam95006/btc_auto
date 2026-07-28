import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import {
  FIXED_SHADOW_LEVERAGE,
  MAX_SHADOW_OPEN_POSITIONS,
  portfolioLeverageBadge,
  shadowLeverageLabel,
} from "../wave4/fixedLeverageLabels";
import { NO_DATA } from "../wave4/noDataFunnel";

type ShadowPosition = {
  symbol: string;
  side: string;
  leverage: number;
  notionalUsdt?: number;
  unrealizedPnl?: number;
  status?: string;
};

type PortfolioSnapshot = {
  ok?: boolean;
  positions?: ShadowPosition[];
  openCount?: number;
  maxOpen?: number;
  leverageFixed?: number;
  mode?: string;
};

/**
 * Wave 4 Portfolio workspace — shadow only, fixed 25x, max 2 positions, NO live actions.
 */
export function PortfolioWorkspacePage() {
  const [snap, setSnap] = useState<PortfolioSnapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch("/api/nexus/shadow/portfolio/overview")
      .then((r) => r.json())
      .then((j) => {
        if (alive) setSnap(j);
      })
      .catch((e) => {
        if (alive) setErr(String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const positions = snap?.positions ?? [];
  const openCount = snap?.openCount ?? positions.length;
  const displayPositions = positions.slice(0, MAX_SHADOW_OPEN_POSITIONS);

  return (
    <div className="page-stack nx-portfolio-w4">
      <header>
        <h1>投資組合</h1>
        <p className="muted">Shadow 觀察工作區 · 固定槓桿 · 無 live 操作</p>
        <span className="w4-leverage-badge">{portfolioLeverageBadge()}</span>
      </header>

      <section className="nx-card" aria-label="Portfolio policy">
        <dl className="nx-kv mono">
          <div>
            <dt>模式</dt>
            <dd>{snap?.mode ?? "SHADOW_READ_ONLY"}</dd>
          </div>
          <div>
            <dt>固定槓桿</dt>
            <dd>{shadowLeverageLabel()}</dd>
          </div>
          <div>
            <dt>最大持倉</dt>
            <dd>{MAX_SHADOW_OPEN_POSITIONS}</dd>
          </div>
          <div>
            <dt>目前開倉</dt>
            <dd>{loading ? "…" : openCount}</dd>
          </div>
        </dl>
        <p className="tag tag-warn">NO live trade · NO ARM · NO mainnet buttons</p>
      </section>

      {err ? <div className="nx-banner-warn">{err}</div> : null}

      <section className="nx-card" aria-label="Open shadow positions">
        <h2 className="nx-sec-title">Shadow 持倉（最多 {MAX_SHADOW_OPEN_POSITIONS}）</h2>
        {loading ? (
          <p className="muted">載入中…</p>
        ) : displayPositions.length === 0 ? (
          <p className="w4-no-data">{NO_DATA} — 無 shadow 持倉</p>
        ) : (
          <table className="nx-scanner-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>方向</th>
                <th>槓桿</th>
                <th>Notional</th>
                <th>uPnL</th>
                <th>狀態</th>
              </tr>
            </thead>
            <tbody>
              {displayPositions.map((p) => (
                <tr key={p.symbol}>
                  <td>
                    <Link to={`/market/${p.symbol}`} className="mono">
                      {p.symbol.replace("USDT", "")}
                    </Link>
                  </td>
                  <td>{p.side}</td>
                  <td className="mono">{shadowLeverageLabel()}</td>
                  <td className="mono">{p.notionalUsdt ?? NO_DATA}</td>
                  <td className="mono">{p.unrealizedPnl ?? NO_DATA}</td>
                  <td>{p.status ?? "SHADOW"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted sm">
          顯示槓桿一律 {FIXED_SHADOW_LEVERAGE}x（UI 標籤）· 後端 shadow policy 為準
        </p>
      </section>

      <section className="nx-card muted" aria-label="Related links">
        <Link to="/global-shadow">全球 Shadow →</Link>
        {" · "}
        <Link to="/paper-lab">PAPER Lab →</Link>
        {" · "}
        <Link to="/performance">績效 →</Link>
      </section>
    </div>
  );
}
