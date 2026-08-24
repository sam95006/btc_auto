# Demo Validation Dockerfile (minimal / disarmed health boundary)
#
# REQUIRED BUILD CONTEXT = repository root (NOT this subdirectory).
# Example:
#   docker build \
#     -f deploy/zeabur_bybit_demo_validation/Dockerfile \
#     --build-arg GITHUB_SHA="$(git rev-parse HEAD)" \
#     -t nexus-demo-val .
#
# Zeabur pin (health-only):
#   ZBPACK_DOCKERFILE_PATH=deploy/zeabur_bybit_demo_validation/Dockerfile

FROM python:3.11-slim-bookworm

ARG GITHUB_SHA=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BYBIT_DEMO=true \
    MAINNET=false \
    REAL_MONEY=false \
    DEMO_AUTONOMOUS_ENABLED=false \
    AUTONOMOUS_SEND=false \
    EXCHANGE_WRITE=false \
    NEXUS_ZEABUR_CLEAN_OBSERVER=false \
    NEXUS_WEB_ONLY=true \
    NEXUS_EMBEDDED_WORKER=false \
    FIXED_LEVERAGE=25 \
    NEXUS_DATA_ROOT=/app/data/nexus_demo_validation \
    NEXUS_DATA_DIR=/app/data/nexus_demo_validation \
    NEXUS_VALIDATION_BOOT=health \
    PORT=8080

WORKDIR /app

# Prefer persistent mount path; entrypoint may fall back if unwritable.
RUN mkdir -p /app/data/nexus_demo_validation /data/nexus_demo_validation || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# P1 recovery/qualification dependencies + packaging from deploy/ folder.
COPY backend/ backend/
COPY config/ config/
COPY deploy/zeabur_bybit_demo_validation/entrypoint.sh ./entrypoint.sh
COPY deploy/zeabur_bybit_demo_validation/validation_health_server.py ./validation_health_server.py
COPY deploy/zeabur_bybit_demo_validation/demo_founder_gate.env ./demo_founder_gate.env

ARG GITHUB_SHA
RUN chmod +x entrypoint.sh \
 && if [ -n "$GITHUB_SHA" ]; then \
      printf '%s' "$GITHUB_SHA" > DEPLOYMENT_COMMIT \
      && printf '%s' "$GITHUB_SHA" > SOURCE_COMMIT; \
    else \
      : > DEPLOYMENT_COMMIT \
      && : > SOURCE_COMMIT; \
    fi \
 && test -f entrypoint.sh \
 && test -f validation_health_server.py \
 && test -f demo_founder_gate.env \
 && test -f backend/nexus_demo_execution/p1_recovery.py \
 && test -f backend/nexus_demo_execution/p1_qualification.py

EXPOSE 8080
CMD ["/bin/sh", "./entrypoint.sh"]
