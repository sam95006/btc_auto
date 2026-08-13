import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import type { MarketRankingRowDto } from "../types/dto";
import { AdviceChip, BiasChip, RiskChip, ScorePill } from "./Chips";
import { SparkChart } from "./SparkChart";

function fmtPrice(n: number) {
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function coinClass(symbol: string) {
  if (symbol.startsWith("BTC")) return "mpv1-coin-btc";
  if (symbol.startsWith("ETH")) return "mpv1-coin-eth";
  if (symbol.startsWith("SOL")) return "mpv1-coin-sol";
  return "";
}

export function RankTableHeader() {
  return (
    <thead>
      <tr>
        <th>#</th>
        <th>資產</th>
        <th>價格</th>
        <th>24h</th>
        <th>方向</th>
        <th>NEXUS</th>
        <th>評分</th>
        <th className="hide-sm">走勢</th>
        <th>風險</th>
        <th className="hide-sm">為什麼現在</th>
        <th></th>
      </tr>
    </thead>
  );
}

export function RankTableRow({
  row,
  rank,
  action,
}: {
  row: MarketRankingRowDto;
  rank: number;
  action?: ReactNode;
}) {
  const up = row.change24hPct >= 0;
  const base = row.symbol.replace("USDT", "");
  return (
    <tr>
      <td style={{ color: "var(--mp-text-3)", fontWeight: 700 }}>{rank}</td>
      <td>
        <Link to={`/app/market/${row.symbol}`} className="mpv1-asset-cell">
          <span className={`mpv1-coin ${coinClass(row.symbol)}`}>{base.slice(0, 1)}</span>
          <span>
            <strong>{base}</strong>
            <span>{row.name}</span>
          </span>
        </Link>
      </td>
      <td style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>${fmtPrice(row.price)}</td>
      <td className={up ? "mpv1-chg-up" : "mpv1-chg-down"}>
        {up ? "+" : ""}
        {row.change24hPct.toFixed(2)}%
      </td>
      <td>
        <BiasChip bias={row.bias} label={row.bias === "bullish" ? "偏多" : row.bias === "bearish" ? "偏空" : "中性"} />
      </td>
      <td>
        <AdviceChip advice={row.advice} label={row.adviceLabel} />
      </td>
      <td>
        <ScorePill score={row.score} />
      </td>
      <td className="hide-sm">
        <SparkChart values={row.sparkline || []} compact tone={up ? "bull" : "bear"} />
      </td>
      <td>
        <RiskChip risk={row.risk} label={row.riskLabel} />
      </td>
      <td className="hide-sm">
        <div className="mpv1-reason-cell">{row.beginnerReason}</div>
      </td>
      <td>
        {action ?? (
          <Link className="mpv1-btn mpv1-btn-ghost mpv1-btn-sm" to={`/app/market/${row.symbol}`}>
            分析
          </Link>
        )}
      </td>
    </tr>
  );
}

/** Compact opportunity card row */
export function OppMiniRow({ row }: { row: MarketRankingRowDto }) {
  const up = row.change24hPct >= 0;
  const base = row.symbol.replace("USDT", "");
  return (
    <Link
      to={`/app/market/${row.symbol}`}
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: "0.35rem",
        padding: "0.65rem 0.75rem",
        borderBottom: "1px solid var(--mp-border)",
        fontSize: "0.82rem",
      }}
    >
      <div>
        <strong>{base}</strong>
        <div style={{ color: "var(--mp-text-3)", fontSize: "0.72rem", marginTop: 2 }}>{row.adviceLabel}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontWeight: 700 }}>${fmtPrice(row.price)}</div>
        <div className={up ? "mpv1-chg-up" : "mpv1-chg-down"} style={{ fontSize: "0.75rem" }}>
          {up ? "+" : ""}
          {row.change24hPct.toFixed(2)}%
        </div>
      </div>
      <div style={{ gridColumn: "1 / -1", color: "var(--mp-text-2)", fontSize: "0.75rem", lineHeight: 1.35 }}>
        {row.beginnerReason}
        {row.score != null ? ` · ${row.score}/100` : ""}
      </div>
    </Link>
  );
}

/** Legacy compact link row — kept for simple lists */
export function MarketRow({ row }: { row: MarketRankingRowDto }) {
  return <OppMiniRow row={row} />;
}
