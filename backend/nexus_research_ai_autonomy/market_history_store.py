"""Bounded persistence for market summary / breadth / regime / risk / radar counts.

Agent A support: JSONL primary + optional SQLite mirror. Caps file growth.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def _default_market_history_root() -> Path:
    try:
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import data_root

        return data_root() / "campaigns" / "research_market_history"
    except Exception:  # noqa: BLE001
        return Path("/data/campaigns/research_market_history")


DEFAULT_ROOT = _default_market_history_root()
MAX_JSONL_LINES = 5000
MAX_SQLITE_ROWS = 5000


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class MarketHistoryStore:
    root: Path = DEFAULT_ROOT
    jsonl_name: str = "market_state_history.jsonl"
    sqlite_name: str = "market_state_history.sqlite"
    max_jsonl_lines: int = MAX_JSONL_LINES
    max_sqlite_rows: int = MAX_SQLITE_ROWS

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

    @property
    def jsonl_path(self) -> Path:
        return self.root / self.jsonl_name

    @property
    def sqlite_path(self) -> Path:
        return self.root / self.sqlite_name

    def _init_sqlite(self) -> None:
        con = sqlite3.connect(str(self.sqlite_path))
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS market_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_market_history_ts ON market_history(ts_ms)"
            )
            con.commit()
        finally:
            con.close()

    def append(self, kind: str, payload: dict[str, Any], *, ts_ms: int | None = None) -> dict[str, Any]:
        ts = int(ts_ms or _now_ms())
        row = {"ts_ms": ts, "kind": str(kind), **dict(payload)}
        line = json.dumps(row, default=str, ensure_ascii=False)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._trim_jsonl()
        con = sqlite3.connect(str(self.sqlite_path))
        try:
            con.execute(
                "INSERT INTO market_history(ts_ms, kind, payload) VALUES (?,?,?)",
                (ts, str(kind), json.dumps(payload, default=str)),
            )
            con.commit()
            self._trim_sqlite(con)
        finally:
            con.close()
        return row

    def record_market_cycle(
        self,
        *,
        market_summary: dict[str, Any] | None = None,
        breadth: dict[str, Any] | float | None = None,
        regime: str | dict[str, Any] | None = None,
        risk: dict[str, Any] | None = None,
        radar_count: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "market_summary": market_summary,
            "breadth": breadth,
            "regime": regime,
            "risk": risk,
            "radar_count": radar_count,
            **dict(extra or {}),
        }
        return self.append("market_cycle", payload)

    def _trim_jsonl(self) -> None:
        if not self.jsonl_path.exists():
            return
        lines = self.jsonl_path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= self.max_jsonl_lines:
            return
        keep = lines[-self.max_jsonl_lines :]
        self.jsonl_path.write_text("\n".join(keep) + "\n", encoding="utf-8")

    def _trim_sqlite(self, con: sqlite3.Connection) -> None:
        n = con.execute("SELECT COUNT(*) FROM market_history").fetchone()[0]
        if n <= self.max_sqlite_rows:
            return
        drop = int(n) - self.max_sqlite_rows
        con.execute(
            "DELETE FROM market_history WHERE id IN (SELECT id FROM market_history ORDER BY id ASC LIMIT ?)",
            (drop,),
        )
        con.commit()

    def recent(self, *, kind: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        con = sqlite3.connect(str(self.sqlite_path))
        try:
            if kind:
                cur = con.execute(
                    "SELECT ts_ms, kind, payload FROM market_history WHERE kind=? ORDER BY id DESC LIMIT ?",
                    (kind, int(limit)),
                )
            else:
                cur = con.execute(
                    "SELECT ts_ms, kind, payload FROM market_history ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                )
            out = []
            for ts_ms, k, payload in cur.fetchall():
                body = json.loads(payload) if payload else {}
                out.append({"ts_ms": ts_ms, "kind": k, **body})
            return out
        finally:
            con.close()

    def stats(self) -> dict[str, Any]:
        con = sqlite3.connect(str(self.sqlite_path))
        try:
            n = con.execute("SELECT COUNT(*) FROM market_history").fetchone()[0]
            kinds = dict(
                con.execute(
                    "SELECT kind, COUNT(*) FROM market_history GROUP BY kind"
                ).fetchall()
            )
        finally:
            con.close()
        jsonl_n = 0
        if self.jsonl_path.exists():
            jsonl_n = len(self.jsonl_path.read_text(encoding="utf-8").splitlines())
        return {
            "sqlite_rows": int(n),
            "jsonl_lines": jsonl_n,
            "kinds": kinds,
            "jsonl_path": str(self.jsonl_path),
            "sqlite_path": str(self.sqlite_path),
            "bounded": True,
            "max_jsonl_lines": self.max_jsonl_lines,
            "max_sqlite_rows": self.max_sqlite_rows,
        }
