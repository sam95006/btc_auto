import { Link, Navigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { getEquitiesProviderStatus } from "../../market/equities/providers";

function EquitiesTabs() {
  const loc = useLocation();
  const tok = loc.pathname.includes("/tokenized");
  const ana = loc.pathname.includes("/analysis");
  return (
    <div className="nx-eq-tabs" role="tablist">
      <Link className={tok || (!tok && !ana) ? "active" : ""} to="/equities/tokenized" role="tab">
        美股代幣
      </Link>
      <Link className={ana ? "active" : ""} to="/equities/analysis" role="tab">
        美股分析
      </Link>
    </div>
  );
}

function ProviderBanner({ kind }: { kind: "tokenized" | "analysis" }) {
  const [st, setSt] = useState<Awaited<ReturnType<typeof getEquitiesProviderStatus>> | null>(null);
  useEffect(() => {
    void getEquitiesProviderStatus().then(setSt);
  }, []);
  const available = kind === "tokenized" ? st?.tokenizedAvailable : st?.equityAvailable;
  return (
    <div className="nx-banner-warn">
      {available
        ? "資料提供者已連接"
        : "資料提供者尚未連接 — 不會顯示假行情。NEXUS 不爬取 TradingView，也不使用未授權股票資料。"}
      <div className="muted sm">
        Provider: {kind === "tokenized" ? st?.tokenizedProviderId : st?.equityProviderId} · licensed=
        {String(st?.licensedEquityData)} · fakeDataForbidden={String(st?.fakeDataForbidden)}
      </div>
    </div>
  );
}

export function EquitiesTokenizedPage() {
  return (
    <div className="page-stack nx-equities-page nx-p3">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">美股專區</h1>
        <EquitiesTabs />
        <p className="nx-status-line">美股代幣 · 研究模式 · 不執行交易</p>
      </header>
      <ProviderBanner kind="tokenized" />
      <section className="nx-chart-card">
        <h2 className="nx-sec-title">預期欄位（Provider 就緒後啟用）</h2>
        <ul className="muted">
          <li>Token symbol／Underlying／Issuer／Network／Venue</li>
          <li>Token price／Underlying reference／Premium／Discount</li>
          <li>Liquidity／Redeemability／Market hours／Jurisdiction</li>
          <li>Counterparty／Issuer risk flags · Freshness</li>
        </ul>
        <p className="muted sm">本輪不建立假標的卡片。代幣化不等於直接持有股票。</p>
      </section>
      <Link to="/overview">← 市場總覽</Link>
    </div>
  );
}

export function EquitiesAnalysisPage() {
  const [q, setQ] = useState("");
  return (
    <div className="page-stack nx-equities-page nx-p3">
      <header className="nx-ov-header">
        <h1 className="nx-page-title">美股專區</h1>
        <EquitiesTabs />
        <p className="nx-status-line">美股分析 · Provider-ready shell · 無假價格</p>
      </header>
      <ProviderBanner kind="analysis" />
      <label className="nx-search-wrap">
        <span className="sr-only">搜尋美股</span>
        <input
          className="nx-search"
          value={q}
          onChange={(e) => setQ(e.target.value.toUpperCase())}
          placeholder="搜尋 AAPL、NVDA…（需 Provider）"
        />
      </label>
      <section className="nx-chart-card">
        <h2 className="nx-sec-title">產品骨架已就緒</h2>
        <p className="muted">
          搜尋、Watchlist、圖表 adapter、Symbol detail shell 可擴充。目前無合規股票行情 Provider，因此不載入
          live quote。查詢「{q || "—"}」不會產生假數據。
        </p>
      </section>
      <Link to="/equities/tokenized">美股代幣 →</Link>
    </div>
  );
}

export function EquitiesIndexRedirect() {
  return <Navigate to="/equities/tokenized" replace />;
}

