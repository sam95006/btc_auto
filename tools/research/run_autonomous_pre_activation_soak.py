#!/usr/bin/env python3
"""Pre-activation 30-minute soak sampler (no deploy/restart)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app"
OUT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "NEXUS_AUTONOMOUS_PRE_ACTIVATION_SOAK.jsonl"
REPORT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "NEXUS_AUTONOMOUS_PRE_ACTIVATION_SOAK.txt"
DURATION_SEC = 30 * 60
INTERVAL_SEC = 60

ENDPOINTS = [
    "/api/nexus/demo/autonomous/status",
    "/api/nexus/demo/autonomous/account",
    "/api/nexus/demo/autonomous/candidates",
    "/api/nexus/demo/autonomous/position",
    "/api/nexus/demo/autonomous/recent-trades",
    "/api/nexus/demo/autonomous/risk",
    "/api/nexus/demo/autonomous/health",
    "/api/nexus/paper/status",
    "/api/nexus/storage/status",
]


def get_json(path: str, timeout: float = 45.0) -> tuple[bool, dict | None, str | None]:
    url = BASE + path
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, json.loads(body), None
    except Exception as exc:  # noqa: BLE001
        return False, None, type(exc).__name__


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    started = time.time()
    start_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    samples = 0
    endpoint_ok = 0
    endpoint_total = 0
    scan_times: list[int] = []
    owners: list[int] = []
    boots: set[str] = set()
    transient = 0
    hard_fail = 0

    while True:
        elapsed = time.time() - started
        if samples > 0 and elapsed >= DURATION_SEC:
            break
        row: dict = {
            "sample": samples + 1,
            "wall_ms": int(time.time() * 1000),
            "elapsed_sec": round(elapsed, 1),
            "endpoints": {},
        }
        sample_ok = True
        for path in ENDPOINTS:
            endpoint_total += 1
            ok, data, err = get_json(path)
            row["endpoints"][path] = {"ok": ok, "error": err}
            if ok:
                endpoint_ok += 1
            else:
                sample_ok = False
                transient += 1
            if path.endswith("/health") and ok and data:
                row["health"] = {
                    "opsState": data.get("opsState"),
                    "scannerStatus": data.get("scannerStatus"),
                    "lastScanAtMs": data.get("lastScanAtMs"),
                    "lastScanTimeProgressing": data.get("lastScanTimeProgressing"),
                    "controllerOwnerCount": data.get("controllerOwnerCount"),
                    "bootId": data.get("bootId"),
                    "paperStatus": data.get("paperStatus"),
                    "ledgerValid": data.get("ledgerValid"),
                    "sessionStatus": data.get("sessionStatus"),
                }
                if data.get("lastScanAtMs"):
                    scan_times.append(int(data["lastScanAtMs"]))
                owners.append(int(data.get("controllerOwnerCount") or 0))
                if data.get("bootId"):
                    boots.add(str(data["bootId"]))
            if path.endswith("/status") and path.endswith("autonomous/status") and ok and data:
                row["status"] = {
                    "positionCount": data.get("positionCount"),
                    "openOrderCount": data.get("openOrderCount"),
                    "mainnetUsed": data.get("mainnetUsed"),
                    "realMoneyUsed": data.get("realMoneyUsed"),
                    "secretSafe": data.get("secretSafe"),
                }
            if path == "/api/nexus/paper/status" and ok and data:
                sess = data.get("activationSession") or {}
                row["paper"] = {
                    "state": sess.get("state"),
                    "maxLeverage": sess.get("maxLeverage"),
                    "maxMarginUsd": sess.get("maxMarginUsd"),
                    "maxOpenPositions": sess.get("maxOpenPositions"),
                }
        if not sample_ok:
            # classify: if next sample recovers, soak can still pass
            hard_fail += 0
        samples += 1
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"sample={samples} elapsed={elapsed:.0f}s "
            f"scan={row.get('health', {}).get('lastScanAtMs')} "
            f"owners={row.get('health', {}).get('controllerOwnerCount')} "
            f"ok={sample_ok}",
            flush=True,
        )
        if samples == 1:
            # ensure we take at least one more after interval
            pass
        time.sleep(INTERVAL_SEC)

    end_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    duration_min = (time.time() - started) / 60.0
    success_rate = (endpoint_ok / endpoint_total * 100.0) if endpoint_total else 0.0
    scan_progressing = len(scan_times) >= 2 and scan_times[-1] > scan_times[0]
    owner_ok = all(o == 1 for o in owners) and len(owners) > 0
    # Read last status snapshot fields from final sample
    last = {}
    try:
        last_line = OUT.read_text(encoding="utf-8").strip().splitlines()[-1]
        last = json.loads(last_line)
    except Exception:
        last = {}
    st = last.get("status") or {}
    paper = last.get("paper") or {}
    health = last.get("health") or {}

    pass_ok = (
        success_rate >= 99.0
        and health.get("scannerStatus") == "RUNNING"
        and scan_progressing
        and owner_ok
        and int(st.get("positionCount") or 0) == 0
        and int(st.get("openOrderCount") or 0) == 0
        and paper.get("state") == "ACTIVE"
        and health.get("ledgerValid") is True
        and st.get("mainnetUsed") is False
        and st.get("secretSafe") is True
        and len(boots) == 1
    )
    # Allow one transient network blip if core still ok
    if not pass_ok and success_rate >= 95.0 and scan_progressing and owner_ok:
        transient_note = "TRANSIENT_NETWORK_RESET"
    else:
        transient_note = "none"

    report = f"""NEXUS_AUTONOMOUS_PRE_ACTIVATION_SOAK

開始時間：{start_iso}
結束時間：{end_iso}
持續分鐘：{duration_min:.1f}
樣本數：{samples}
端點成功率：{success_rate:.2f}% ({endpoint_ok}/{endpoint_total})
Scanner狀態：{health.get('scannerStatus')}
Last Scan是否前進：{scan_progressing}
Controller Owners：{owners[-1] if owners else None}（全程皆1={owner_ok}）
重複Controller：{False if owner_ok and len(boots) == 1 else True}
重複訂單：{(int(st.get('openOrderCount') or 0) > 0)}
position_count：{st.get('positionCount')}
open_order_count：{st.get('openOrderCount')}
PAPER狀態：{paper.get('state')}
Ledger狀態：{health.get('ledgerValid')}
Boot唯一：{len(boots) == 1} ({next(iter(boots), '')[:8]})
Mainnet：{st.get('mainnetUsed')}
SecretSafe：{st.get('secretSafe')}
暫時網路分類：{transient_note}
Pre-activation soak通過：{pass_ok}
"""
    REPORT.write_text(report, encoding="utf-8")
    print(report, flush=True)
    return 0 if pass_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
