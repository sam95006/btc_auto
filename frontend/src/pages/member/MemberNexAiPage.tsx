import { useState } from "react";
import { Link } from "react-router-dom";
import { MemberPageChrome } from "../../member/MemberPageChrome";

type Turn = { role: "user" | "nex"; text: string };

const STARTER: Turn[] = [
  {
    role: "nex",
    text: "NEX AI (DEMO) — I challenge theses and evidence gaps. I do not place orders or access private Founder Lesson Memory.",
  },
];

export function MemberNexAiPage() {
  const [turns, setTurns] = useState<Turn[]>(STARTER);
  const [draft, setDraft] = useState("");

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    const reply: Turn = {
      role: "nex",
      text: `DEMO challenge: For “${text.slice(0, 120)}”, list supporting evidence, contradicting evidence, invalidation, and whether Outcome Review is owed. No buy/sell command.`,
    };
    setTurns((t) => [...t, { role: "user", text }, reply]);
    setDraft("");
  };

  return (
    <MemberPageChrome
      title="NEX AI"
      subtitle="Conversation assist inside Decision Integrity workflows · not a standalone chat product"
    >
      <section className="member-panel member-nex-panel" aria-label="NEX AI conversation">
        <ul className="member-nex-thread">
          {turns.map((t, i) => (
            <li key={i} className={`member-nex-turn ${t.role}`}>
              <span className="member-nex-role">{t.role === "nex" ? "NEX" : "You"}</span>
              <p>{t.text}</p>
            </li>
          ))}
        </ul>
        <div className="member-nex-compose">
          <label className="sr-only" htmlFor="nex-draft">
            Message
          </label>
          <textarea
            id="nex-draft"
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask for evidence challenges, invalidation prompts, or review structure…"
          />
          <button type="button" className="member-btn primary" onClick={send}>
            Send (DEMO)
          </button>
        </div>
        <p className="muted sm">
          Prefer structured loops: <Link to="/decisions">Decision Feed</Link> ·{" "}
          <Link to="/outcome-review">Outcome Review</Link>
        </p>
      </section>
    </MemberPageChrome>
  );
}
