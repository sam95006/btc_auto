import type { WatchRow } from "../demo/marketDashboard";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

function tone(status: WatchRow["status"]): "hold" | "wait" | "pass" {
  if (status === "WAIT") return "wait";
  if (status === "MONITOR") return "pass";
  return "hold";
}

/** Long / Short watchlist tables — read-only actions only (MVP-22). */
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
                  <th>Price</th>
                  <th>AI Score</th>
                  <th>Change</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.symbol}
                    className={focusSymbol === r.symbol ? "rec-row-focus" : undefined}
                  >
                    <td className="mono sym-cell">
                      {r.symbol}
                      {focusSymbol === r.symbol ? (
                        <span className="focus-mark" aria-label="focus">
                          ◀
                        </span>
                      ) : null}
                    </td>
                    <td className="mono">{r.price}</td>
                    <td>{r.aiScore}</td>
                    <td
                      className={
                        r.changePct == null
                          ? "muted"
                          : r.changePct >= 0
                            ? "price-up"
                            : "price-down"
                      }
                    >
                      {r.changePct == null
                        ? "—"
                        : `${r.changePct >= 0 ? "+" : ""}${r.changePct.toFixed(1)}%`}
                    </td>
                    <td>
                      <StatusBadge tone={tone(r.status)}>{r.status}</StatusBadge>
                    </td>
                    <td>
                      <ReadOnlyNavChip label={r.next} to={r.nextTo} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="rec-mobile">
            {rows.map((r) => (
              <article
                key={r.symbol}
                className={`rec-mobile-card${focusSymbol === r.symbol ? " rec-row-focus" : ""}`}
              >
                <div className="fleet-card-head">
                  <strong className="mono">{r.symbol}</strong>
                  <StatusBadge tone={tone(r.status)}>{r.status}</StatusBadge>
                </div>
                <div className="rec-mobile-meta mono">
                  {r.price} · {r.aiScore}
                  {r.changePct != null
                    ? ` · ${r.changePct >= 0 ? "+" : ""}${r.changePct.toFixed(1)}%`
                    : ""}
                </div>
                <ReadOnlyNavChip label={r.next} to={r.nextTo} />
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
