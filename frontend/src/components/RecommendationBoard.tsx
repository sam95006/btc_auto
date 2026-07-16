import type { WatchRow } from "../demo/marketDashboard";
import { formatUsd } from "../market/freshness";
import { useLivePrice } from "../market/useLiveMarketFeed";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

function tone(status: WatchRow["status"]): "hold" | "wait" | "pass" {
  if (status === "WAIT") return "wait";
  if (status === "MONITOR") return "pass";
  return "hold";
}

function RowView({
  r,
  focusSymbol,
}: {
  r: WatchRow;
  focusSymbol?: string;
}) {
  const live = useLivePrice(r.symbol);
  const current = live?.lastPrice;
  const ch = live?.change24hPct ?? r.changePct;
  const ref = r.signalReferencePrice;

  return (
    <>
      <tr className={focusSymbol === r.symbol ? "rec-row-focus" : undefined}>
        <td className="mono sym-cell">
          {r.symbol}
          {focusSymbol === r.symbol ? (
            <span className="focus-mark" aria-label="focus">
              ◀
            </span>
          ) : null}
        </td>
        <td className="mono">
          <div>Live {formatUsd(current)}</div>
          <div className="muted rec-sub">Signal ref {formatUsd(ref)}</div>
        </td>
        <td>
          <div>{r.recommendation}</div>
          <div className="muted rec-sub">
            {r.confidence} · {r.timeframe}
          </div>
        </td>
        <td
          className={ch == null ? "muted" : ch >= 0 ? "price-up" : "price-down"}
        >
          {ch == null ? "—" : `${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%`}
        </td>
        <td>
          <StatusBadge tone={tone(r.status)}>{r.status}</StatusBadge>
          <div className="muted rec-sub">Inv {r.invalidationLevel}</div>
        </td>
        <td>
          <ReadOnlyNavChip label={r.next} to={r.nextTo} />
        </td>
      </tr>
    </>
  );
}

function MobileCard({ r, focusSymbol }: { r: WatchRow; focusSymbol?: string }) {
  const live = useLivePrice(r.symbol);
  const current = live?.lastPrice;
  const ref = r.signalReferencePrice;
  return (
    <article className={`rec-mobile-card${focusSymbol === r.symbol ? " rec-row-focus" : ""}`}>
      <div className="fleet-card-head">
        <strong className="mono">{r.symbol}</strong>
        <StatusBadge tone={tone(r.status)}>{r.status}</StatusBadge>
      </div>
      <div className="rec-mobile-meta mono">
        Live {formatUsd(current)} · Ref {formatUsd(ref)} · {r.recommendation} · {r.timeframe}
      </div>
      <div className="muted rec-sub">
        Analysis {new Date(r.analysisTimestamp).toISOString()} · Inv {r.invalidationLevel}
      </div>
      <ReadOnlyNavChip label={r.next} to={r.nextTo} />
    </article>
  );
}

/** Long / Short watchlist — live lastPrice + signal reference (MVP-22A). */
export function RecommendationBoard({
  title,
  rows,
  emptyNote,
  focusSymbol,
}: {
  title: string;
  rows: WatchRow[];
  emptyNote?: string;
  focusSymbol?: string;
}) {
  return (
    <section className="panel-card rec-board" aria-label={title}>
      <div className="rec-board-head">
        <h2>{title}</h2>
      </div>
      {rows.length === 0 ? (
        <p className="muted rec-empty">{emptyNote ?? "No active short candidate · Monitoring only · Read-only"}</p>
      ) : (
        <>
          <div className="table-scroll rec-desktop">
            <table className="intel-table rec-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Current / Signal Ref</th>
                  <th>Recommendation</th>
                  <th>24h</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <RowView key={r.symbol} r={r} focusSymbol={focusSymbol} />
                ))}
              </tbody>
            </table>
          </div>
          <div className="rec-mobile">
            {rows.map((r) => (
              <MobileCard key={r.symbol} r={r} focusSymbol={focusSymbol} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
