# Use python 3.12 slim image
FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Install system dependencies
# - curl: for installing uv
# - git: for installing dependencies from git
# - build-essential: for compiling Python extensions
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Copy dependency files first
COPY pyproject.toml uv.lock README.md ./

# Install dependencies (including 'memory' extra)
RUN uv sync --frozen --no-install-project --all-extras

# Install playwright browsers (for WebpageTool)
RUN uv run --no-sync playwright install --with-deps chromium

# Copy application code
COPY src/ src/
COPY config/ config/
COPY skills/ skills/
COPY scripts/ scripts/
COPY .env.example .env

# Install the project itself
RUN uv sync --frozen --all-extras

# Expose port
EXPOSE 8000

# Start command
CMD ["uv", "run", "--no-sync", "python", "src/suzent/server.py"]
