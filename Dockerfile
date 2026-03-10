# ─── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=2.2.1
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Configure Poetry: no venv inside container (we install directly)
ENV POETRY_VIRTUALENVS_CREATE=false

COPY pyproject.toml poetry.lock* ./

# Install production dependencies only (no dev, no MetaTrader5 on Linux)
RUN poetry install --only main --no-root 2>&1 || true

# ─── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN addgroup --system brocker && adduser --system --ingroup brocker brocker

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Application source
COPY src/ ./src/
COPY config/ ./config/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create model and knowledge directories
RUN mkdir -p models docs/knowledge && chown -R brocker:brocker /app

USER brocker

# PYTHONPATH so all bounded contexts are importable
ENV PYTHONPATH=/app/src

EXPOSE 8000

ENTRYPOINT ["python", "-m", "brocker"]
CMD ["trade", "--dry-run"]
