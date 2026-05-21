import os

# Single worker so embedded NEXUS runtime is not forked into duplicate trading loops.
workers = int(os.getenv("WEB_CONCURRENCY", "1") or "1")
bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
threads = 4
timeout = 120
graceful_timeout = 30
