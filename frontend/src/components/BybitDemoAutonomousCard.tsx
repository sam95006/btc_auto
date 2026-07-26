/** Bybit Demo autonomous ops card — homepage read-only status (no fake PnL). */

import { useEffect, useState } from "react";

export type AutonomousOpsStatus = {
  ok?: boolean;
  opsState?: string;
  opsStateZh?: string;
  controllerStatus?: string;
  scannerStatus?: string;
  sessionStatus?: string;
  sessionExpiresAt?: number | null;
  autoSend?: boolean;
  headlineZh?: string;
  orderStatusZh?: string;
  lastScanAtMs?: number | null;
  symbolsScanned?: number;
  tradableSymbols?: number;
  eligibleCandidates?: number;
  topCandidate?: {
    symbol?: string;
    side?: string;
    strategy?: string;
    confidence?: number;
    leverage?: number;
    allowTrade?: boolean;
    blockReasons?: string[];
  } | null;
  demoEquity?: number | null;
  availableBalance?: number | null;
  dailyPnl?: number | null;
  weeklyPnl?: number | null;
  capitalTier?: string;
  riskTier?: string;
  positionCount?: number;
  openOrderCount?: number;
  currentPosition?: Record<string, unknown> | null;
  protectionStatus?: string;
  blockReasons?: string[];
  lastTrade?: Record<string, unknown> | null;
  lastReflection?: Record<string, unknown> | null;
  lifecycle?: { steps?: string[]; completed?: string[] };
  emergencyStop?: boolean;
  reconciliationStatus?: string;
  paperStatus?: string | null;
  ledgerValid?: boolean | null;
  deploymentCommit?: string;
  bootId?: string;
  mainnetUsed?: boolean;
  realMoneyUsed?: boolean;
  secretSafe?: boolean;
};

const POLL_MS = 15000;

async function fetchOps(): Promise<AutonomousOpsStatus> {
  const res = await fetch("/api/nexus/demo/autonomous/status", {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`ops_http_${res.status}`);
  return (await res.json()) as AutonomousOpsStatus;
}

function fmtAge(ms: number | null | undefined): string {
  if (ms == null) return "尚無";
  const age = Math.max(0, Date.now() - ms);
  if (age < 60_000) return `${Math.round(age / 1000)}秒前`;
  if (age < 3600_000) return `${Math.round(age / 60_000)}分鐘前`;
  return `${Math.round(age / 3600_000)}小時前`;
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(digits);
}

function fmtMaybe(v: unknown, fallback = "資料尚未完整回填"): string {
  if (v == null || v === "") return fallback;
  return String(v);
}

function runLabel(status?: string): string {
  if (status === "RUNNING") return "運行中";
  if (status === "STOPPED") return "已停止";
  return status || "未知";
}

export function BybitDemoAutonomousCard() {
  const [data, setData] = useState<AutonomousOpsStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyStop, setBusyStop] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await fetchOps();
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "ops_unavailable");
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const onEmergencyStop = async () => {
    if (busyStop) return;
    const ok = window.confirm(
      "確認緊急停止？只會停止新的 Demo 訂單，不會刪除持倉，也不會自動平倉。",
    );
    if (!ok) return;
    setBusyStop(true);
    try {
      await fetch("/api/nexus/demo/autonomous/session/emergency-stop", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ reason: "ui_emergency_stop" }),
      });
      const next = await fetchOps();
      setData(next);
    } finally {
      setBusyStop(false);
    }
  };

  const pos = data?.currentPosition;
  const top = data?.topCandidate;
  const trade = data?.lastTrade;
  const completed = new Set(data?.lifecycle?.completed || []);
  const hasPos = (data?.positionCount || 0) > 0;
  const sessionActive = data?.sessionStatus === "ACTIVE";
  const autoSendOn = Boolean(data?.autoSend);
  const modeBadge = !sessionActive
    ? "待啟用"
    : autoSendOn
      ? "運行中"
      : "Session已啟用・Auto Send OFF";

  return (
    <section className="nx-p7-block nx-demo-ops-card" aria-label="Bybit Demo 自動交易">
      <div className="nx-demo-ops-head">
        <div>
          <h2 className="nx-sec-title">Bybit Demo 自動交易</h2>
          <p className="muted sm">Demo 模式 · 非實盤 · 非投資建議</p>
        </div>
        <div className="nx-demo-ops-badges">
          <span className="nx-demo-badge">Demo</span>
          <span className={`nx-demo-badge ${sessionActive && autoSendOn ? "ok" : "warn"}`}>
            自動Demo交易：{modeBadge}
          </span>
          <span className={`nx-demo-badge ${autoSendOn ? "ok" : "warn"}`}>
            Demo Auto Send：{autoSendOn ? "ON" : "OFF"}
          </span>
        </div>
      </div>

      {error ? <div className="nx-banner-warn">營運狀態暫不可用：{error}</div> : null}

      <p className="nx-demo-ops-state">
        目前狀態：<strong>{data?.headlineZh || data?.opsStateZh || "讀取中…"}</strong>
        <span className="muted mono"> {data?.opsState || ""}</span>
      </p>
      {!sessionActive ? (
        <p className="muted sm">自動下單尚未啟用 · 下單狀態：{data?.orderStatusZh || "等待 Demo Session"}</p>
      ) : (
        <p className="muted sm">
          Session：ACTIVE
          {data?.sessionExpiresAt
            ? ` · 到期 ${new Date(data.sessionExpiresAt).toLocaleString("zh-TW")}`
            : ""}
          {" · "}
          {data?.orderStatusZh || ""}
        </p>
      )}

      <div className="nx-demo-ops-grid">
        <div>
          <span className="muted">Session</span>
          <strong>{data?.sessionStatus || "NONE"}</strong>
        </div>
        <div>
          <span className="muted">市場掃描</span>
          <strong>{runLabel(data?.scannerStatus)}</strong>
        </div>
        <div>
          <span className="muted">Demo Equity</span>
          <strong className="mono">{fmtNum(data?.demoEquity)}</strong>
        </div>
        <div>
          <span className="muted">Available</span>
          <strong className="mono">{fmtNum(data?.availableBalance)}</strong>
        </div>
        <div>
          <span className="muted">本日 PnL</span>
          <strong className="mono">{data?.dailyPnl == null ? "—" : fmtNum(data.dailyPnl)}</strong>
        </div>
        <div>
          <span className="muted">本週 PnL</span>
          <strong className="mono">{data?.weeklyPnl == null ? "—" : fmtNum(data.weeklyPnl)}</strong>
        </div>
        <div>
          <span className="muted">Capital Tier</span>
          <strong>{data?.capitalTier || "VALIDATION"}</strong>
        </div>
        <div>
          <span className="muted">Risk Tier</span>
          <strong>{data?.riskTier || "0.5pct"}</strong>
        </div>
      </div>

      <div className="nx-demo-ops-scanline">
        <span>最後掃描：{fmtAge(data?.lastScanAtMs)}</span>
        <span>掃描合約：{data?.symbolsScanned ?? "—"}</span>
        <span>可交易：{data?.tradableSymbols ?? "—"}</span>
        <span>合格候選：{data?.eligibleCandidates ?? "—"}</span>
      </div>

      <div className="nx-demo-ops-section">
        <h3 className="nx-demo-ops-h3">最高候選</h3>
        {top ? (
          <p>
            {top.symbol || "—"} · {top.side || "—"} · {top.strategy || "—"} · 信心{" "}
            {fmtNum(top.confidence, 1)} · 建議槓桿 {top.leverage ?? "—"}x
            {top.allowTrade === false ? " · 暫不可交易" : ""}
          </p>
        ) : (
          <p className="muted">{hasPos ? "持倉中，暫不顯示新候選" : "尚無合格候選"}</p>
        )}
        {(data?.blockReasons || []).length ? (
          <p className="muted sm">阻塞原因：{(data?.blockReasons || []).join(", ")}</p>
        ) : null}
      </div>

      <div className="nx-demo-ops-section">
        <h3 className="nx-demo-ops-h3">目前持倉</h3>
        {hasPos && pos ? (
          <ul className="nx-demo-ops-list">
            <li>
              {String(pos.symbol)} · {String(pos.side)} · 槓桿 {String(pos.leverage ?? "—")}x · Isolated
            </li>
            <li>
              Entry {fmtNum(pos.entryPrice as number)} · Mark {fmtNum(pos.markPrice as number)} · uPnL{" "}
              {fmtNum(pos.unrealisedPnl as number)}
            </li>
            <li>
              SL {fmtMaybe(pos.stopLoss, "—")} · TP {fmtMaybe(pos.takeProfit, "—")} · Liq{" "}
              {fmtMaybe(pos.liquidationPrice, "—")}
            </li>
            <li>
              保護狀態：
              {data?.protectionStatus === "ACTIVE" ? "持倉中・已設置停損與停利" : data?.protectionStatus || "—"}
            </li>
          </ul>
        ) : (
          <p className="muted">
            目前持倉：無 · 下單狀態：{data?.orderStatusZh || (!sessionActive ? "等待 Demo Session" : "掃描中")}
          </p>
        )}
      </div>

      <div className="nx-demo-ops-section">
        <h3 className="nx-demo-ops-h3">最近交易</h3>
        {trade ? (
          <ul className="nx-demo-ops-list">
            <li>
              {fmtMaybe(trade.symbol, "—")} · {fmtMaybe(trade.side, "—")} ·{" "}
              {fmtMaybe(trade.strategy, "—")}
            </li>
            <li>
              Entry {fmtMaybe(trade.entry, "—")} · Exit {fmtMaybe(trade.exit, "—")}
            </li>
            <li>
              Net PnL{" "}
              {trade.netPnl == null || trade.incomplete
                ? "資料尚未完整回填"
                : fmtNum(trade.netPnl as number)}
              {" · "}R{" "}
              {trade.rMultiple == null || trade.incomplete
                ? "資料尚未完整回填"
                : fmtNum(trade.rMultiple as number)}
            </li>
            <li>Reflection：{fmtMaybe(trade.reflectionStatus, "—")}</li>
          </ul>
        ) : (
          <p className="muted">尚無已回填之最近交易</p>
        )}
      </div>

      <div className="nx-demo-ops-section">
        <h3 className="nx-demo-ops-h3">交易生命週期</h3>
        <div className="nx-demo-lifecycle">
          {(data?.lifecycle?.steps || []).map((step) => (
            <span key={step} className={completed.has(step) ? "done" : "pending"}>
              {step}
            </span>
          ))}
        </div>
      </div>

      <div className="nx-demo-ops-section">
        <h3 className="nx-demo-ops-h3">風控</h3>
        <p className="sm">
          Demo only · Mainnet blocked · Real money blocked · Isolated only · Max positions=1 · Max
          pending=1 · Risk≤0.5% · Daily／Weekly／Consecutive gates · Emergency{" "}
          {data?.emergencyStop ? "ON" : "OFF"} · Reconcile {data?.reconciliationStatus || "—"}
        </p>
        <div className="nx-demo-ops-actions">
          <button type="button" className="nx-text-btn" onClick={() => void onEmergencyStop()} disabled={busyStop}>
            Emergency Stop（只停新單）
          </button>
          <span className="muted sm">平倉請走獨立 Controlled Demo Close（需確認）</span>
        </div>
      </div>

      <p className="muted sm nx-demo-ops-foot">
        PAPER {data?.paperStatus || "—"} · Ledger{" "}
        {data?.ledgerValid == null ? "—" : data.ledgerValid ? "valid" : "invalid"} · commit{" "}
        {data?.deploymentCommit ? data.deploymentCommit.slice(0, 7) : "未揭露"} · boot{" "}
        {(data?.bootId || "").slice(0, 8) || "—"}
      </p>
    </section>
  );
}
