FROM python:3.11.6-slim

# Copy uv binaries from official astral image
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/

# Set working directory and environment variables
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Install project dependencies into virtual environment using uv
COPY pyproject.toml .
RUN uv sync --no-install-project

# Copy application source code
COPY . .
RUN uv sync

# Expose Streamlit default port
EXPOSE 8501

# Start Streamlit application
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
