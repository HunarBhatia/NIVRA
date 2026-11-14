# Nivra API + worker image (section 21.8). Build from the REPOSITORY ROOT
# (it needs shared/platforms.json):  docker build -f backend/Dockerfile .
# The same image runs both:
#   API:    uvicorn app.main:app   (default command)
#   worker: python -m app.discovery.worker
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
# The shared platform directory, read by app/platforms.py.
COPY shared/platforms.json /shared/platforms.json

# Run as an unprivileged user; data lives in /data (a mounted volume).
RUN useradd --create-home --uid 10001 nivra && mkdir -p /data/evidence && chown -R nivra /data
USER nivra

ENV NIVRA_ENVIRONMENT=production \
    NIVRA_PLATFORMS_FILE=/shared/platforms.json \
    NIVRA_EVIDENCE_DIR=/data/evidence \
    NIVRA_AGENT_CHECKPOINT_PATH=/data/agents.db \
    NIVRA_LOG_FORMAT=json \
    NIVRA_INLINE_WORKER=false

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Proxy headers: the app runs behind the website/reverse proxy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips=*"]
