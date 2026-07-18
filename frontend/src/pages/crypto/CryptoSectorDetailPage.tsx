import { Link, useParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { fetchSectorDetail, fetchSectorSymbols, type SectorRow } from "../../market/sectorApi";

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function BarChart({
  title,
  items,
}: {
  title: string;
  items: { label: string; value: number; tone?: string }[];
}) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  return (
    <section className="nx-chart-card">
      <h2 className="nx-sec-title">{title}</h2>
      <ul className="nx-bar-list">
        {items.map((it) => (
          <li key={it.label}>
            <span className="lbl">{it.label}</span>
            <span className="nx-bar-track">
              <span
                className={`nx-bar-fill ${it.tone || ""}`}
                style={{ width: `${Math.min(100, (Math.abs(it.value) / max) * 100)}%` }}
              />
            </span>
            <span className="mono">{it.value}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CryptoSectorDetailPage() {
  const { sectorSlug = "" } = useParams();
  const [sector, setSector] = useState<SectorRow | null>(null);
  const [insight, setInsight] = useState("");
  const [symbols, setSymbols] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [memberFilter, setMemberFilter] = useState("ALL");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [d, s] = await Promise.all([
          fetchSectorDetail(sectorSlug),
          fetchSectorSymbols(sectorSlug, 80),
        ]);
        if (!alive) return;
        if (!d.ok) {
          setError(d.error || "not_found");
          setSector(null);
        } else {
          setError(null);
          setSector(d.sector || null);
          setInsight(d.insight || "");
        }
        setSymbols(s.symbols || []);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "load_failed");
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 20000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [sectorSlug]);

  const filtered = useMemo(() => {
    if (memberFilter === "DEEP") return symbols.filter((m) => m.inDeepScan);
    if (memberFilter === "LONG") return symbols.filter((m) => m.side === "LONG");
    if (memberFilter === "SHORT") return symbols.filter((m) => m.side === "SHORT");
    if (memberFilter === "CONFIRMED") return symbols.filter((m) => m.stage === "CONFIRMED");
    if (memberFilter === "OVEREXTENDED") return symbols.filter((m) => m.stage === "OVEREXTENDED");
    if (memberFilter === "COLLECTING") return symbols.filter((m) => m.collecting);
    return symbols;
  }, [symbols, memberFilter]);

  const perfBars = useMemo(() => {
    return filtered
      .filter((m) => m.change24hPct != null)
      .slice(0, 12)
      .map((m) => ({
        label: String(m.symbol).replace("USDT", ""),
        value: Number(m.change24hPct),
        tone: Number(m.change24hPct) >= 0 ? "up" : "down",
      }));
  }, [filtered]);

  return (
    <div className="page-stack nx-sector-detail nx-p3">
      <div className="nx-ov-meta">
        <Link to="/crypto/sectors">← 版塊列表</Link>
      </div>
      {error ? <div className="nx-banner-warn">{error}</div> : null}
      {sector ? (
        <>
          <header className="nx-ov-header">
            <h1 className="nx-page-title">{sector.nameZhTW}</h1>
            <p className="nx-status-line">
              {sector.sectorStateLabelZh} · {sector.sampleNote} · {sector.freshness}
            </p>
            <p className="muted">{insight}</p>
            <p className="muted sm">規則洞察 · 非買入建議 · 附樣本覆蓋說明</p>
          </header>
          <section className="nx-regime-stats">
            <div>
              <span className="lbl">加權 24h</span>
              <strong>{fmtPct(sector.turnoverWeightedReturn24h)}</strong>
            </div>
            <div>
              <span className="lbl">中位 24h</span>
              <strong>{fmtPct(sector.medianReturn24h)}</strong>
            </div>
            <div>
              <span className="lbl">廣度 ↑／↓</span>
              <strong>
                {sector.risingCount ?? "—"}/{sector.fallingCount ?? "—"}
              </strong>
            </div>
            <div>
              <span className="lbl">多／空候選</span>
              <strong>
                {sector.longCandidateCount}/{sector.shortCandidateCount}
              </strong>
            </div>
            <div>
              <span className="lbl">已確認</span>
              <strong>{sector.confirmedCandidateCount}</strong>
            </div>
            <div>
              <span className="lbl">深度覆蓋</span>
              <strong>
                {sector.deepScanMemberCount}/{sector.memberCount}
              </strong>
            </div>
          </section>

          <BarChart
            title="版塊廣度（上漲／下跌／中性／累積中）"
            items={[
              { label: "上漲", value: sector.risingCount || 0, tone: "up" },
              { label: "下跌", value: sector.fallingCount || 0, tone: "down" },
              { label: "中性", value: sector.neutralCount || 0 },
              { label: "累積中", value: sector.collectingCount || 0 },
            ]}
          />
          <BarChart title="成員績效排行（24h）" items={perfBars} />
          <BarChart
            title="候選多空分布"
            items={[
              { label: "做多", value: sector.longCandidateCount, tone: "up" },
              { label: "做空", value: sector.shortCandidateCount, tone: "down" },
              { label: "已確認", value: sector.confirmedCandidateCount },
              { label: "過熱", value: sector.overextendedCount },
            ]}
          />
          <section className="nx-chart-card">
            <h2 className="nx-sec-title">Funding／週轉貢獻</h2>
            <p className="mono">
              Funding 中位{" "}
              {sector.medianFundingRate != null
                ? `${(sector.medianFundingRate * 100).toFixed(4)}%`
                : "樣本不足"}{" "}
              · 週轉貢獻 {sector.turnoverContribution != null ? Math.round(sector.turnoverContribution) : "—"}
            </p>
            <p className="muted sm">
              OI 5m 中位 {fmtPct(sector.medianOiChange5m)}（不足時顯示資料累積中，不以 0 填補）
            </p>
          </section>

          <section className="nx-chart-card">
            <h2 className="nx-sec-title">價格／持倉結構</h2>
            <p className="muted sm">
              版塊詳情不內嵌完整 Price／OI 散點；請使用已套用本版塊篩選的專頁。
            </p>
            <Link className="nx-link" to={`/crypto/price-oi?sector=${encodeURIComponent(sector.slug)}`}>
              查看此版塊的價格／持倉結構 →
            </Link>
          </section>

          <div className="nx-filter-row">
            {[
              ["ALL", "全部"],
              ["DEEP", "深度掃描"],
              ["LONG", "做多"],
              ["SHORT", "做空"],
              ["CONFIRMED", "已確認"],
              ["OVEREXTENDED", "過熱"],
              ["COLLECTING", "累積中"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={memberFilter === id ? "active" : ""}
                onClick={() => setMemberFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>

          <section className="nx-chart-card">
            <h2 className="nx-sec-title">成員排行</h2>
            <ul className="nx-turn-list">
              {filtered.map((m) => (
                <li key={String(m.symbol)}>
                  <Link to={`/market/${m.symbol}`} className="nx-turn-row">
                    <span className="mono">{String(m.symbol).replace("USDT", "")}</span>
                    <span>{fmtPct(m.change24hPct as number)}</span>
                    <span className="muted">{String(m.side || (m.inDeepScan ? "深度" : "廣度"))}</span>
                    <span className="muted">{String(m.freshness || "—")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
}
