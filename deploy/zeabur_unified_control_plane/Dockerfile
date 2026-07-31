# Read-only Unified NEXUS Control Plane
# Build context: repository root on feature/unified-nexus-control-plane
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTROL_PLANE=true \
    CONTROL_PLANE_READ_ONLY=true \
    EXCHANGE_WRITE=false \
    MAINNET=false \
    REAL_MONEY=false \
    DEMO_AUTONOMOUS_ENABLED=false \
    AUTONOMOUS_SEND=false \
    NEXUS_WEB_ONLY=true \
    NEXUS_EMBEDDED_WORKER=false \
    FIXED_LEVERAGE=25 \
    NEXUS_DATA_DIR=/tmp/nexus_control_plane \
    PORT=8080

WORKDIR /app
RUN mkdir -p /tmp/nexus_control_plane

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py run.py gunicorn.conf.py zbpack.json ./
COPY backend/ backend/
COPY config/ config/
COPY static/ static/
COPY templates/ templates/

EXPOSE 8080
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
