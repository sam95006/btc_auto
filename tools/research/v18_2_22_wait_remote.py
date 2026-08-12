import json
import time
import urllib.request

BASE = "https://nexus-member-preview-v18-2-1.zeabur.app"
MARKER = "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD"
ASSET = "index-Nr1Lvu93.js"


def get(url: str):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read().decode("utf-8", errors="ignore")


def check():
    out = {"preview_url": BASE, "marker": MARKER}
    try:
        st, body = get(f"{BASE}/api/nexus/ui-build")
        out["ui_build_status"] = st
        data = json.loads(body)
        out["remote_marker"] = data.get("build_marker") or data.get("buildMarker")
    except Exception as e:
        out["ui_build_error"] = str(e)
        out["remote_marker"] = None
    try:
        st, html = get(f"{BASE}/")
        out["index_status"] = st
        import re

        m = re.search(r"/assets/(index-[^\"]+\.js)", html)
        out["remote_js"] = m.group(1) if m else None
        if m:
            st2, js = get(f"{BASE}/assets/{m.group(1)}")
            out["js_status"] = st2
            out["marker_in_js"] = MARKER in js
            out["expected_asset"] = ASSET
            out["asset_match"] = m.group(1) == ASSET
    except Exception as e:
        out["index_error"] = str(e)
    # smoke
    smoke = {}
    for path in [
        "/overview",
        "/market/BTCUSDT",
        "/scanner",
        "/alerts",
        "/research",
        "/intelligence",
        "/account",
        "/api/nexus/public/closed-beta/foundation",
        "/api/nexus/public/closed-beta/ops",
        "/api/nexus/public/closed-beta/partner-inventory",
        "/api/nexus/public/analytics/contract",
        "/api/nexus/public/retention/foundation",
    ]:
        try:
            st, _ = get(f"{BASE}{path}")
            smoke[path] = st
        except Exception as e:
            smoke[path] = f"ERR:{e}"
    out["smoke"] = smoke
    out["remote_verified"] = bool(out.get("marker_in_js")) and out.get("remote_marker") == MARKER
    return out


def main():
    last = None
    for i in range(24):
        last = check()
        print(json.dumps({"attempt": i + 1, **{k: last.get(k) for k in ("remote_marker", "remote_js", "marker_in_js", "remote_verified")}}, ensure_ascii=True))
        if last.get("remote_verified"):
            break
        time.sleep(15)
    print(json.dumps(last, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
