# MenuFinder

Search for a dish, find restaurants near you that serve it.

Most restaurant apps let you search by restaurant name or cuisine. MenuFinder searches the **actual menu items** — type "mac and cheese" or "katsu curry" and get a ranked list of nearby restaurants that have it, with prices and descriptions.

## How It Works

1. **Discovery** — Finds restaurants via the Google Places API across a metro grid.
2. **Scraping** — Visits each restaurant's website and extracts the menu. An 8-tier extraction pipeline tries the cheapest method first (structured data, CSS selectors, price heuristics, PDF parsing) and only falls back to AI (Claude vision/LLM) when free methods fail.
3. **Search** — A TF-IDF / BM25-inspired ranking engine with food-synonym expansion, word-boundary matching, and geographic distance weighting.
4. **iOS App** — SwiftUI client with map-based search and autocomplete.

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12, async) |
| Database | PostgreSQL 16 + PostGIS + pg_trgm |
| Scraping | httpx + Playwright (headless Chromium) |
| Menu extraction | pdfplumber, BeautifulSoup, Claude Haiku (vision + text) |
| Auth | JWT (PyJWT) + bcrypt |
| Frontend | SwiftUI (iOS) |
| Package manager | [uv](https://docs.astral.sh/uv/) |

## Quick Start

### Prerequisites
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker Desktop
- A Google Places API key and an Anthropic API key

### Setup

```bash
cd backend

# Install dependencies (uv creates a virtualenv automatically)
uv sync

# Configure secrets
cp .env.example .env
# edit .env — add your API keys

# Start the database
docker compose up -d

# Install Playwright's browser (one-time)
uv run playwright install chromium

# Run the API server
uv run uvicorn app.main:app --port 8000
```

The API is now at `http://localhost:8000` — interactive docs at `http://localhost:8000/docs`.

### Populate the database

In a separate terminal:

```bash
cd backend

# See available metro areas
uv run python scripts/scrape_worker.py --list-metros

# Scrape a metro (budget mode — free extraction only, stays in Google's free tier)
uv run python scripts/scrape_worker.py --grid san_diego --free-only --monthly-budget 8000
```

### Run tests

```bash
cd backend
uv run pytest -v
```

## Project Structure

```
restaurant searcher/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI endpoints (search, auth, favorites, ...)
│   │   ├── services/
│   │   │   ├── scraper/      # 8-tier menu extraction pipeline
│   │   │   ├── search.py     # TF-IDF ranking engine
│   │   │   └── places.py     # Google Places integration
│   │   ├── models/           # SQLAlchemy ORM models
│   │   └── data/             # Metro grid definitions
│   ├── scripts/
│   │   ├── scrape_worker.py  # Standalone scraping worker
│   │   └── run_all_metros.py # Multi-metro orchestrator
│   └── tests/                # pytest suite (89 tests)
├── MenuFinder/               # SwiftUI iOS app
└── docs/                     # Architecture, costs, operations, philosophy
```

## Documentation

| Document | Covers |
|---|---|
| [docs/philosophy.md](docs/philosophy.md) | Core principles: cost consciousness, lifecycle thinking, testing |
| [docs/architecture.md](docs/architecture.md) | Components, DB schema, scraping pipeline, search ranking |
| [docs/operations.md](docs/operations.md) | Running the system, scraper commands, admin ops, prod checklist |
| [docs/costs.md](docs/costs.md) | API pricing, multi-metro projections, break-even analysis |

## Key Design Decisions

- **Scraping is decoupled from the API server.** The worker runs as a standalone process — heavy browser/AI workloads would crash uvicorn.
- **Cheapest extraction method first.** ~70% of restaurants are handled with zero AI cost. AI is a last resort, gated behind a `--free-only` flag for budget runs.
- **Resumable scraping.** A checkpoint table lets the worker stop and resume mid-metro. Budget limits keep Google Places usage within the free tier.
- **No Alembic (yet).** New tables auto-create on startup; column changes need manual `ALTER TABLE`. See [docs/operations.md](docs/operations.md).

## Status

This is a work-in-progress side project. Backend is functional with 89 passing tests and ~5,700 San Diego restaurants scraped. Premium subscription scaffolding exists but Apple IAP receipt validation is stubbed — see [docs/architecture.md](docs/architecture.md) before any production deploy.

## License

Not yet licensed — all rights reserved.
