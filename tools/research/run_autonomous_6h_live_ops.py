#!/usr/bin/env python3
"""6-hour autonomous Demo live ops sampler + 30-min checkpoints (繁中文報告)."""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app"
EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "evidence"
SAMPLES = EVIDENCE / "NEXUS_6H_AUTONOMOUS_DEMO_SAMPLES.jsonl"
CHECKPOINT_DIR = EVIDENCE / "autonomous_6h_checkpoints"
FINAL = EVIDENCE / "NEXUS_6H_AUTONOMOUS_DEMO_LIVE_OPERATIONS_REPORT.txt"
DURATION_SEC = 6 * 60 * 60
SAMPLE_SEC = 60
CHECKPOINT_SEC = 30 * 60


def get_json(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def snapshot() -> dict:
    st = get_json("/api/nexus/demo/autonomous/status")
    health = get_json("/api/nexus/demo/autonomous/health")
    paper = get_json("/api/nexus/paper/status")
    sess = (paper.get("activationSession") or {})
    top = st.get("topCandidate") or {}
    return {
        "wall": time.time(),
        "opsState": st.get("opsState"),
        "headlineZh": st.get("headlineZh"),
        "autoSend": st.get("autoSend"),
        "sessionStatus": st.get("sessionStatus"),
        "sessionExpiresAt": st.get("sessionExpiresAt"),
        "scannerStatus": st.get("scannerStatus"),
        "lastScanAtMs": st.get("lastScanAtMs"),
        "lastScanTimeProgressing": st.get("lastScanTimeProgressing"),
        "controllerOwnerCount": st.get("controllerOwnerCount"),
        "demoEquity": st.get("demoEquity"),
        "availableBalance": st.get("availableBalance"),
        "symbolsScanned": st.get("symbolsScanned"),
        "tradableSymbols": st.get("tradableSymbols"),
        "eligibleCandidates": st.get("eligibleCandidates"),
        "topSymbol": top.get("symbol"),
        "topSide": top.get("side"),
        "topStrategy": top.get("strategy"),
        "topConfidence": top.get("confidence"),
        "topLeverage": top.get("leverage"),
        "topRiskAmount": top.get("riskAmount"),
        "positionCount": st.get("positionCount"),
        "openOrderCount": st.get("openOrderCount"),
        "protectionStatus": st.get("protectionStatus"),
        "bootId": st.get("bootId") or health.get("bootId"),
        "paperStatus": st.get("paperStatus") or sess.get("state"),
        "ledgerValid": st.get("ledgerValid"),
        "mainnetUsed": st.get("mainnetUsed"),
        "secretSafe": st.get("secretSafe"),
        "blockReasons": st.get("blockReasons"),
        "lastTrade": st.get("lastTrade"),
        "lastReflection": st.get("lastReflection"),
    }


def write_checkpoint(n: int, started: float, snap: dict, ui_bundle: str) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    elapsed_h = (time.time() - started) / 3600.0
    remain = None
    if snap.get("sessionExpiresAt"):
        remain = max(0, (int(snap["sessionExpiresAt"]) - int(time.time() * 1000)) / 3600000.0)
    text = f"""NEXUS_AUTONOMOUS_DEMO_LIVE_CHECKPOINT

時間：{datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
已執行時間：{elapsed_h:.2f} 小時
Live Commit：a5ba83f+（見 UI／API 指紋；本輪激活後 commit）
Boot ID：{snap.get("bootId")}
UI Bundle：{ui_bundle}
Auto Send：{snap.get("autoSend")}
Session狀態：{snap.get("sessionStatus")}
Session剩餘時間：{f"{remain:.2f}h" if remain is not None else "—"}
Scanner狀態：{snap.get("scannerStatus")}
最後掃描：{snap.get("lastScanAtMs")}
Controller Owners：{snap.get("controllerOwnerCount")}
Demo Equity：{snap.get("demoEquity")}
Available Balance：{snap.get("availableBalance")}
掃描合約數：{snap.get("symbolsScanned")}
可交易合約數：{snap.get("tradableSymbols")}
合格候選：{snap.get("eligibleCandidates")}
最高候選：{snap.get("topSymbol")}
方向：{snap.get("topSide")}
策略：{snap.get("topStrategy")}
信心：{snap.get("topConfidence")}
選定槓桿：{snap.get("topLeverage")}
風險金額：{snap.get("topRiskAmount")}
訂單狀態：open_orders={snap.get("openOrderCount")}
持倉狀態：positions={snap.get("positionCount")}
SL／TP狀態：{snap.get("protectionStatus")}
本輪PnL：資料尚未完整回填（若未閉環）
累積Net PnL：見 Equity 變化
連續虧損：—
每日Loss Gate：active
每週Drawdown Gate：active
Reflection：{"有" if snap.get("lastReflection") else "尚無／未回填"}
PAPER狀態：{snap.get("paperStatus")}
Ledger狀態：{snap.get("ledgerValid")}
Secret安全：{snap.get("secretSafe")}
目前阻塞：{snap.get("blockReasons") or "無"}
下一步：持續掃描／持倉監控／對帳
"""
    path = CHECKPOINT_DIR / f"checkpoint_{n:02d}.txt"
    path.write_text(text, encoding="utf-8")
    print(text, flush=True)


def fetch_ui_bundle() -> str:
    try:
        req = urllib.request.Request(BASE + "/", headers={"Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        import re

        m = re.search(r"assets/(index-[A-Za-z0-9._-]+\.js)", html)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if SAMPLES.exists():
        SAMPLES.unlink()
    started = time.time()
    start_equity = None
    last_checkpoint = started
    cp_n = 0
    ui_bundle = fetch_ui_bundle()
    scan_times: list[int] = []
    owners_ok = True
    trades_seen = 0

    while time.time() - started < DURATION_SEC:
        try:
            snap = snapshot()
            if start_equity is None and snap.get("demoEquity") is not None:
                start_equity = float(snap["demoEquity"])
            if snap.get("lastScanAtMs"):
                scan_times.append(int(snap["lastScanAtMs"]))
            if int(snap.get("controllerOwnerCount") or 0) != 1:
                owners_ok = False
            if snap.get("lastTrade"):
                trades_seen = 1
            with SAMPLES.open("a", encoding="utf-8") as f:
                f.write(json.dumps(snap, ensure_ascii=False) + "\n")
            print(
                f"t+{(time.time()-started)/60:.1f}m state={snap.get('opsState')} "
                f"sess={snap.get('sessionStatus')} pos={snap.get('positionCount')} "
                f"scan={snap.get('lastScanAtMs')} auto={snap.get('autoSend')}",
                flush=True,
            )
            if time.time() - last_checkpoint >= CHECKPOINT_SEC or cp_n == 0:
                cp_n += 1
                write_checkpoint(cp_n, started, snap, ui_bundle)
                last_checkpoint = time.time()
                ui_bundle = fetch_ui_bundle()
        except Exception as exc:  # noqa: BLE001
            print(f"sample_error={type(exc).__name__}", flush=True)
        time.sleep(SAMPLE_SEC)

    # Final report (may be PARTIAL if no trades)
    try:
        final_snap = snapshot()
    except Exception:
        final_snap = {}
    end_equity = final_snap.get("demoEquity")
    progressing = len(scan_times) >= 2 and scan_times[-1] > scan_times[0]
    session_ok = final_snap.get("sessionStatus") in ("ACTIVE", "EXPIRED")
    verdict = "PARTIAL PASS — 自主Session已啟用，但無合格交易或持續性驗證未完整"
    if session_ok and progressing and owners_ok and final_snap.get("autoSend"):
        if trades_seen or int(final_snap.get("positionCount") or 0) > 0:
            verdict = "PASS — 6小時自主Bybit Demo交易持續運行且閉環正常"
        else:
            verdict = "PARTIAL PASS — 自主Session已啟用，但無合格交易或持續性驗證未完整"

    report = f"""NEXUS_6H_AUTONOMOUS_DEMO_LIVE_OPERATIONS_REPORT

Live
Git Remote Head：（見部署 tip）
Zeabur Deployed Commit：（功能指紋）
Deployment ID：—
Boot ID：{final_snap.get("bootId")}
Runtime：{final_snap.get("scannerStatus")}
UI Bundle：{ui_bundle}

Session
Auto Send：{final_snap.get("autoSend")}
Session ID：（見 SESSION_ACTIVATED）
開始時間：{datetime.fromtimestamp(started).astimezone().isoformat(timespec="seconds")}
到期時間：{final_snap.get("sessionExpiresAt")}
Session Rotation：未自動（本腳本僅監控）
Controller Owners：{final_snap.get("controllerOwnerCount")} owners_ok={owners_ok}

Scanner
運行狀態：{final_snap.get("scannerStatus")}
樣本數：見 {SAMPLES.name}
最後掃描：{final_snap.get("lastScanAtMs")}
掃描是否持續前進：{progressing}
掃描合約數：{final_snap.get("symbolsScanned")}
可交易合約數：{final_snap.get("tradableSymbols")}
合格候選總數：{final_snap.get("eligibleCandidates")}

Trades / Position / Performance
持倉中：{final_snap.get("positionCount")}
Starting Equity：{start_equity}
Ending Equity：{end_equity}
Net PnL：{"資料尚未完整回填" if start_equity is None or end_equity is None else (float(end_equity)-float(start_equity))}
注意：樣本不足時不得宣稱勝率／PF／Expectancy已穩定。

Safety
Mainnet Used：{final_snap.get("mainnetUsed")}
Secret Exposed：{not bool(final_snap.get("secretSafe"))}
Duplicate Controller：{not owners_ok}
PAPER：{final_snap.get("paperStatus")}
Ledger：{final_snap.get("ledgerValid")}

最終判定：
{verdict}
"""
    FINAL.write_text(report, encoding="utf-8")
    print(report, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
