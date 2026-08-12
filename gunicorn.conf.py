import os

# Single worker so embedded NEXUS runtime is not forked into duplicate trading loops.
workers = int(os.getenv("WEB_CONCURRENCY", "1") or "1")
threads = 4
timeout = 120
graceful_timeout = 30


def _resolve_port() -> str:
    for key in ("PORT", "WEB_PORT"):
        raw = str(os.getenv(key, "") or "").strip()
        if not raw:
            continue
        # Reject unresolved Zeabur templates like ${WEB_PORT}
        if raw.startswith("${") or not raw.isdigit():
            continue
        return raw
    return "8080"


bind = f"0.0.0.0:{_resolve_port()}"


def on_starting(server):  # noqa: ARG001 — gunicorn hook
    print(
        "service_mode=BYBIT_DEMO_VALIDATION "
        f"bind_host=0.0.0.0 bind_port={_resolve_port()} "
        f"demo_autonomous_enabled={os.getenv('DEMO_AUTONOMOUS_ENABLED', 'false')} "
        f"exchange_write={os.getenv('EXCHANGE_WRITE', 'false')} "
        f"mainnet={os.getenv('MAINNET', 'false')} "
        f"real_money={os.getenv('REAL_MONEY', 'false')}",
        flush=True,
    )
