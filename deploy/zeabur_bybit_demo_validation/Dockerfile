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
    FIXED_LEVERAGE=25 \
    PORT=8080

WORKDIR /app
RUN mkdir -p /data/demo_execution /data/artifacts/demo_validation

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY config/ config/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8080
CMD ["/bin/sh", "./entrypoint.sh"]
