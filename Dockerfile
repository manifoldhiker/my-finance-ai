# Use a modern Python version
FROM python:3.12-slim-bookworm

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# --frozen ensures we stick to the lockfile
# --no-dev because we are running in production-like environment
# --no-install-project (optional, but we likely want to just install deps first for caching)
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the application
COPY . .

# Install the project itself (if needed) or just ensure pythonpath is correct
# Running sync again with project files present installs the root package if defined
RUN uv sync --frozen --no-dev

# Set PYTHONPATH to include the current directory so -m lookups work
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"

# Default command (can be overridden by docker-compose)
CMD ["python", "-m", "mcp.mcp_server"]
