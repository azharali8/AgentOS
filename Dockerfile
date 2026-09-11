# ─────────────────────────────────────────────────────────────────────────────
# AgentOS — Multi-stage Production Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder: install Python dependencies
# Stage 2 — Frontend: build Next.js static assets
# Stage 3 — Runtime: minimal non-root image with compiled assets
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Python dependency builder ────────────────────────────────────────
FROM python:3.11-slim AS python-builder

WORKDIR /build

# Install build tools for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Frontend build ───────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --legacy-peer-deps

COPY frontend/ .
RUN npm run build


# ── Stage 3: Production runtime ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="AgentOS Team"
LABEL version="0.3.0"
LABEL description="AgentOS — AI Engineering Operating System"

# Non-root user for security
RUN groupadd -r agentos && useradd -r -g agentos -m -s /bin/false agentos

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=python-builder /install /usr/local

# Copy backend source
COPY --chown=agentos:agentos backend/ ./backend/
COPY --chown=agentos:agentos alembic.ini ./

# Copy built frontend assets
COPY --from=frontend-builder --chown=agentos:agentos /frontend/.next/ ./frontend/.next/
COPY --from=frontend-builder --chown=agentos:agentos /frontend/public/ ./frontend/public/

# Create persistent volume mount points (will be mounted as named volumes)
RUN mkdir -p /app/data /app/workspace /app/artifacts /app/logs && \
    chown -R agentos:agentos /app/data /app/workspace /app/artifacts /app/logs

# Volumes for persistent state — MUST be mounted in production
VOLUME ["/app/data", "/app/workspace", "/app/artifacts"]

# Expose backend API port
EXPOSE 8000

USER agentos

# Health check — liveness probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Entrypoint — run database migrations then start API server
ENTRYPOINT ["sh", "-c", "alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 2 --log-config /dev/null"]
