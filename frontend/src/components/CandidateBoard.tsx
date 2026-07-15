import { CANDIDATE_MEANINGS } from "../demo/productUx";
import { ReadOnlyNavChip } from "./ReadOnlyNavChip";
import { StatusBadge } from "./StatusBadge";

/** Simplified candidate board with plain-language meaning (MVP-21). */
export function CandidateBoard() {
  return (
    <section id="candidate-board" className="operator-section board-section">
      <div className="section-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          Candidate Board
        </h2>
        <StatusBadge tone="hold">HOLD</StatusBadge>
      </div>
      <p className="muted section-lede">
        What each symbol means right now · Evidence / Gate / Risk only · no Buy / Sell / Quick Order
      </p>

      <div className="table-scroll candidate-desktop">
        <table className="intel-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Status</th>
              <th>Meaning</th>
              <th>Next</th>
            </tr>
          </thead>
          <tbody>
            {CANDIDATE_MEANINGS.map((r) => (
              <tr key={r.symbol}>
                <td className="mono sym-cell">{r.symbol}</td>
                <td>{r.status}</td>
                <td className="muted">{r.meaning}</td>
                <td>
                  <ReadOnlyNavChip label={r.nextLabel} to={r.nextTo} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="candidate-mobile">
        {CANDIDATE_MEANINGS.map((r) => (
          <article key={r.symbol} className="panel-card dense-card">
            <div className="fleet-card-head">
              <h3 className="fleet-symbol">{r.symbol}</h3>
              <StatusBadge tone={r.symbol === "ETH" ? "wait" : "hold"}>
                {r.symbol === "ETH" ? "WAIT" : "HOLD"}
              </StatusBadge>
            </div>
            <p>
              <strong>Status:</strong> {r.status}
            </p>
            <p className="muted">
              <strong>Meaning:</strong> {r.meaning}
            </p>
            <ReadOnlyNavChip label={r.nextLabel} to={r.nextTo} />
          </article>
        ))}
      </div>
    </section>
  );
}
