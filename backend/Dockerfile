# MenuFinder API server
#
# Builds the FastAPI server only. The scrape worker runs separately (locally or
# as its own service) and is NOT included here — the API never scrapes.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# --- Dependency layer (cached unless pyproject.toml / uv.lock change) ---
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- Application layer ---
COPY app ./app

# Install the project package itself
RUN uv sync --frozen --no-dev

# Run from the project virtualenv
ENV PATH="/app/.venv/bin:$PATH"

# Railway/Render inject $PORT at runtime; 8000 is the local default
ENV PORT=8000
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
