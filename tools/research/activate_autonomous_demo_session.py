#!/usr/bin/env python3
"""Issue Demo autonomous session + verify post-activation (no secrets)."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app"
OUT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "NEXUS_AUTONOMOUS_SESSION_ACTIVATED.txt"


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    # Reconcile before write grant
    account = get_json("/api/nexus/demo/autonomous/account")
    position = get_json("/api/nexus/demo/autonomous/position")
    health = get_json("/api/nexus/demo/autonomous/health")
    pos_n = int(account.get("positionCount") or 0)
    if position.get("positionOpen"):
        pos_n = max(pos_n, 1)
    open_n = int(account.get("openOrderCount") or 0)
    owners = int(health.get("controllerOwnerCount") or 0)

    if owners != 1:
        raise SystemExit(f"blocked: controller_owners={owners}")
    if open_n > 0 and pos_n == 0:
        # Flat with stray orders needs reconcile attention, but conditional SL leftovers unlikely when flat.
        pass
    if open_n > 1:
        raise SystemExit(f"blocked: open_orders={open_n} (reconcile first)")

    issued = post_json(
        "/api/nexus/demo/autonomous/session/issue",
        {
            "ttlMs": 6 * 60 * 60 * 1000,
            "maxRiskPerTradePct": 0.5,
            "autoSend": True,
            "maxConsecutiveLosses": 3,
            "riskTier": "VALIDATION",
        },
    )
    sess = (issued.get("session") or {})
    time.sleep(2)
    st = get_json("/api/nexus/demo/autonomous/status")
    report = f"""NEXUS_AUTONOMOUS_SESSION_ACTIVATED

時間：{datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
Session ID：{sess.get("sessionId")}
建立時間：{sess.get("createdAtMs")}
到期時間：{sess.get("expiresAtMs")}
Auto Send：{st.get("autoSend")}（env={st.get("autoSendEnv")} session={sess.get("autoSend")}）
Demo-only：{sess.get("environment") == "BYBIT_DEMO"}
風險層級：{sess.get("riskTier")}
每筆風險上限：{sess.get("maxRiskPerTradePct")}%
每日損失上限：{sess.get("maxDailyLossPct")}%
每週回撤上限：{sess.get("maxWeeklyDrawdownPct")}%
最大連續虧損：{sess.get("maxConsecutiveLosses")}
最大持倉：{sess.get("maxOpenPositions")}
最大Pending：{sess.get("maxPendingOrders")}
Controller Owners：{st.get("controllerOwnerCount")}
Reconcile position_count：{st.get("positionCount")}
Reconcile open_order_count：{st.get("openOrderCount")}
Session狀態：{st.get("sessionStatus")}
Session啟用成功：{bool(issued.get("ok") and st.get("sessionStatus") == "ACTIVE")}
MainnetAllowed：{sess.get("mainnetAllowed")}
RealMoneyAllowed：{sess.get("realMoneyAllowed")}
SecretSafe：{issued.get("secretSafe")}
"""
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(json.dumps({"ok": issued.get("ok"), "sessionId": sess.get("sessionId"), "active": st.get("sessionStatus")}, ensure_ascii=False))
    return 0 if st.get("sessionStatus") == "ACTIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
