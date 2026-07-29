# Demo Validation Dockerfile
#
# REQUIRED BUILD CONTEXT = repository root (NOT this subdirectory).
# Example:
#   docker build -f deploy/zeabur_bybit_demo_validation/Dockerfile -t nexus-demo-val .
#
# Zeabur CLI `zeabur deploy` from repo root uses RootDirectory="" and this
# path must be selected explicitly if used; otherwise root ./Dockerfile applies.
# Both root and this file start the same Flask entry: gunicorn app:app.

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
    NEXUS_DATA_DIR=/tmp/nexus_demo_validation \
    PORT=8080

WORKDIR /app

RUN mkdir -p /tmp/nexus_demo_validation /data/nexus_demo_validation || true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Full app tree required for Flask entry app:app / run.py
COPY app.py run.py gunicorn.conf.py zbpack.json ./
COPY backend/ backend/
COPY config/ config/
COPY static/ static/
COPY templates/ templates/
COPY tools/ci/ tools/ci/
COPY deploy/zeabur_bybit_demo_validation/entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh \
 && test -f app.py \
 && test -f gunicorn.conf.py \
 && test -f entrypoint.sh

EXPOSE 8080
CMD ["/bin/sh", "./entrypoint.sh"]
