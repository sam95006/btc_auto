# Demo Validation Dockerfile
#
# REQUIRED BUILD CONTEXT = repository root (NOT this subdirectory).
# Example:
#   docker build -f deploy/zeabur_bybit_demo_validation/Dockerfile -t nexus-demo-val .
#
# Zeabur CLI `zeabur deploy` from repo root uses RootDirectory="" and this
# path must be selected explicitly if used; otherwise root ./Dockerfile applies.
# This image starts only the dedicated validation health endpoint.

FROM python:3.11-slim-bookworm

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
    PORT=8080

WORKDIR /app

# Prefer persistent mount path; entrypoint may fall back if unwritable.
RUN mkdir -p /app/data/nexus_demo_validation /data/nexus_demo_validation || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only P1 recovery/qualification dependencies and the minimal boot boundary.
COPY backend/ backend/
COPY config/ config/
COPY deploy/zeabur_bybit_demo_validation/entrypoint.sh ./entrypoint.sh
COPY deploy/zeabur_bybit_demo_validation/validation_health_server.py ./validation_health_server.py
RUN chmod +x entrypoint.sh \
 && test -f entrypoint.sh \
 && test -f validation_health_server.py \
 && test -f backend/nexus_demo_execution/p1_recovery.py \
 && test -f backend/nexus_demo_execution/p1_qualification.py

EXPOSE 8080
CMD ["/bin/sh", "./entrypoint.sh"]
