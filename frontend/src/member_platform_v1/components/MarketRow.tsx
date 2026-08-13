import { Link } from "react-router-dom";
import type { MarketRankingRowDto } from "../types/dto";
import { AdviceChip, BiasChip, ScorePill } from "./Chips";

function fmtPrice(n: number) {
  if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function MarketRow({ row }: { row: MarketRankingRowDto }) {
  const up = row.change24hPct >= 0;
  return (
    <Link className="mpv1-market-row" to={`/app/market/${row.symbol}`}>
      <div>
        <div className="mpv1-sym">{row.symbol.replace("USDT", "")}</div>
        <div className="mpv1-sym-name">{row.name}</div>
        <p className="mpv1-reason">{row.beginnerReason}</p>
      </div>
      <div className="mpv1-row-meta">
        <BiasChip bias={row.bias} label={row.biasLabel.replace("市場", "")} />
        <AdviceChip label={row.adviceLabel} />
        <ScorePill score={row.score} />
      </div>
      <div className="mpv1-price">
        <div>${fmtPrice(row.price)}</div>
        <div className={up ? "mpv1-chg-up" : "mpv1-chg-down"}>
          {up ? "+" : ""}
          {row.change24hPct.toFixed(2)}%
        </div>
      </div>
    </Link>
  );
}
