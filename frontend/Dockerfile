# Stage 1: base
FROM python:3.11.6-slim@sha256:cc758519481092eb5a4a5ab0c1b303e288880d59afc601958d19e95b300bc86b AS base

# Prevent Python from writing .pyc files & enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app --home /home/app app

WORKDIR /app
RUN chown app:app /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

# Stage 2: dependencies
FROM base AS dependencies

# Copy dependency files and assign ownership to 'app'
COPY --chown=app:app pyproject.toml uv.lock* ./

USER app

# Sync dependencies (prod only, no project code yet)
RUN uv sync --frozen --no-install-project --no-editable

# Stage 3: tools
FROM dependencies AS tools

# Install dev dependencies
RUN uv sync --frozen --no-install-project --no-editable --group dev || true

# Stage 4: build
FROM dependencies AS build

# Copy the application code with correct ownership
COPY --chown=app:app . .

# Final install of project (prod only)
RUN uv sync --frozen --no-editable --no-dev

# Stage 5: runtime
FROM base AS runtime

COPY --from=build --chown=app:app /app /app
USER app

EXPOSE 8501

CMD ["/app/.venv/bin/streamlit", "run", "app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
