# Minimal image for optional Control Plane smoke (not for Zeabur deploy this sprint).
FROM python:3.11-slim
WORKDIR /app
ENV EXCHANGE_WRITE=false MAINNET=false REAL_MONEY=false CONTROL_PLANE_READ_ONLY=true
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt flask
COPY backend ./backend
COPY tools ./tools
CMD ["python", "tools/ci/control_plane_docker_smoke.py"]
