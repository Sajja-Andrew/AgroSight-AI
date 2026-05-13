# syntax=docker/dockerfile:1.7

# ═══════════════════════════════════════════════════════════
# AgroSight AI — Production-Ready Dockerfile
# Multi-stage optimized build for CPU inference
# ═══════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────
# Stage 1 — Builder (compile deps, create venv)
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        gfortran \
        libopenblas-dev \
        liblapack-dev \
        libpq-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip/setuptools
RUN pip install --upgrade pip setuptools wheel

# Copy requirements
COPY backend/requirements.txt .

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir \
    --compile \
    --no-binary :all: \
    -r requirements.txt 2>&1 | grep -v "already satisfied" | tail -20

# Clean unnecessary files from venv
RUN find /opt/venv -type d \( -name "__pycache__" -o -name "tests" -o -name "*.egg-info" \) -exec rm -rf {} + 2>/dev/null || true
RUN find /opt/venv -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.so.debug" \) -delete 2>/dev/null || true

# ──────────────────────────────────────────────────────────
# Stage 2 — Runtime (minimal production image)
# ──────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS production

LABEL maintainer="AgroSight AI Team" \
      version="3.0.0" \
      description="Production-ready disease detection API"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=2 \
    PIP_NO_CACHE_DIR=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    TF_FORCE_GPU_ALLOW_GROWTH=true \
    MALLOC_TRIM_THRESHOLD_=100000 \
    MALLOC_MMAP_THRESHOLD_=131072 \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2 \
    NUMEXPR_NUM_THREADS=2 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PORT=5000

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libblas3 \
        liblapack3 \
        libpq5 \
        curl \
        wget \
        netcat-openbsd \
        libjpeg62-turbo \
        zlib1g \
        ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create non-root user for security
RUN groupadd -r agrosight && useradd -r -g agrosight agrosight

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=agrosight:agrosight /opt/venv /opt/venv

# Copy application code
COPY --chown=agrosight:agrosight backend/ ./backend/
COPY --chown=agrosight:agrosight wsgi.py ./
COPY --chown=agrosight:agrosight scripts/ ./scripts/
COPY --chown=agrosight:agrosight docker/entrypoint.sh /entrypoint.sh

# Make scripts executable
RUN chmod +x /entrypoint.sh ./scripts/*.sh 2>/dev/null || true

# Create runtime directories
RUN mkdir -p \
    /app/backend/uploads \
    /app/backend/instance \
    /tmp/agrosight \
    /var/log/gunicorn \
    && chown -R agrosight:agrosight /app /tmp/agrosight /var/log/gunicorn

# Switch to non-root user
USER agrosight

# Set PATH to use venv
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 5000

# Production health check (increased timeout for TensorFlow model loading)
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD curl -fsSL http://localhost:5000/api/health || exit 1

# Use entrypoint for setup, then run gunicorn
ENTRYPOINT ["/entrypoint.sh"]

CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--worker-class", "gthread", \
     "--threads", "4", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50", \
     "--worker-tmp-dir", "/tmp/agrosight", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "wsgi:app"]
