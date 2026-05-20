# Operations Guide

## Running Locally

The project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
cd backend

# One-time setup
uv sync                              # install deps into .venv
cp .env.example .env                 # then edit .env with API keys
uv run playwright install chromium   # install headless browser

# Start DB (port 5433 — local Postgres uses 5432)
docker compose up -d

# Start API server
uv run uvicorn app.main:app --port 8000

# Run scraper (separate terminal — NEVER inside uvicorn)
uv run python scripts/scrape_worker.py --grid san_diego --free-only

# Run tests
uv run pytest -v
```

`uv run` automatically uses the project's `.venv` — no manual activation needed.

**Fallback without uv:** Python 3.12 lives at
`C:\Users\amirs\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Use that full path with `-m uvicorn` / `-m pytest` if uv is unavailable.

## Scraper Commands

All commands run from `backend/`. Prefix with `uv run` (e.g. `uv run python scripts/...`).

```bash
# Budget mode: free extraction, core food types, with monthly limit
uv run python scripts/scrape_worker.py --grid new_york --free-only --monthly-budget 8000

# Full coverage: all methods, all food types, tight grid
uv run python scripts/scrape_worker.py --grid san_diego --spacing 2.5 --food-types all --include-photos

# List available metros with search counts
uv run python scripts/scrape_worker.py --list-metros

# Run all metros in population order
uv run python scripts/run_all_metros.py --free-only --monthly-budget 8000

# Run specific metros
uv run python scripts/run_all_metros.py --free-only --metros new_york,chicago,austin

# Single location scrape
uv run python scripts/scrape_worker.py --lat 32.8755 --lng -117.2295 --radius 5000

# Resume a stopped run (automatic — just re-run same command)
uv run python scripts/scrape_worker.py --grid new_york --free-only

# Reset checkpoint and start from scratch
uv run python scripts/scrape_worker.py --grid new_york --free-only --reset-checkpoint

# Preview failure counts
uv run python scripts/scrape_worker.py --retry-failures --dry-run

# Retry LLM-skipped restaurants
uv run python scripts/scrape_worker.py --retry-failures --error-type free_only_skip

# Retry all failures
uv run python scripts/scrape_worker.py --retry-failures
```

## Resolution Tiers

| Flag | Budget default | Full coverage |
|---|---|---|
| `--free-only` | Yes | No (uses LLM) |
| `--food-types` | core (12 types) | all (34 types) |
| `--spacing` | 5km (auto) | 2-3km |
| `--include-photos` | No | Yes |
| `--radius` | 5000m | 3000m |

## Schema Changes

No Alembic migrations. When modifying models:
1. **New tables:** handled automatically by `create_all()` on server/worker startup
2. **New columns on existing tables:** must run ALTER TABLE manually:
   ```sql
   docker exec backend-db-1 psql -U menufinder -d menufinder -c "ALTER TABLE tablename ADD COLUMN IF NOT EXISTS colname TYPE DEFAULT value;"
   ```
3. Always test the worker after schema changes before telling the user to run it

## Database Queries

```sql
-- Restaurant + menu item counts
SELECT count(DISTINCT r.id) as restaurants, count(m.id) as items
FROM restaurants r LEFT JOIN menu_items m ON m.restaurant_id = r.id;

-- Failure breakdown
SELECT error_type, count(*), min(extractor_version)
FROM scrape_failures WHERE resolved = 0
GROUP BY error_type ORDER BY count DESC;

-- Checkpoint status
SELECT metro_name, grid_index, total_grid_points, searches_this_run, completed_at
FROM scrape_checkpoints ORDER BY updated_at DESC;

-- Menu search vector trigger check
SELECT name, search_vector IS NOT NULL as has_vector FROM menu_items LIMIT 5;
```

## Admin Operations

```sql
-- Grant admin access
UPDATE users SET is_admin = 1 WHERE email = 'you@example.com';

-- Grant lifetime premium to a user (via SQL, not API)
INSERT INTO subscriptions (id, user_id, tier, source, is_active)
SELECT gen_random_uuid(), id, 'lifetime', 'admin', 1 FROM users WHERE email = 'user@example.com';
```

## Deploying to Railway

The repo ships with `backend/Dockerfile` and `backend/railway.json` for the API
server. The app self-bootstraps PostgreSQL extensions and the search trigger on
startup (`app/core/db_bootstrap.py`), so a fresh hosted database needs no manual SQL.

### 1. Database service
- New project → **Deploy from Docker Image** → `postgis/postgis:16-3.4`
- Set service variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Railway exposes a `DATABASE_URL` reference variable for this service

### 2. API service
- **Deploy from GitHub repo** → select this repo
- Service Settings → **Root Directory** = `backend` (so Railway finds the Dockerfile)
- Set environment variables:
  - `DATABASE_URL` = reference the Postgres service's URL
    (`postgresql://...` is auto-normalized to `asyncpg` by `config.py`)
  - `JWT_SECRET` = a long random string
  - `GOOGLE_PLACES_API_KEY`, `ANTHROPIC_API_KEY`
- Railway injects `$PORT`; the Dockerfile/uvicorn already use it
- Healthcheck `/health` is configured in `railway.json`

### 3. Scrape worker
Not deployed. Run it locally pointed at the hosted DB — set `DATABASE_URL` in your
local `.env` to Railway's **public** Postgres URL, then run the worker as usual.

### Notes
- The `/api/v1/discover` endpoint triggers scraping and will fail on the hosted API
  (no Playwright browser in the image — by design). Use the standalone worker instead.
- Render works too: provision managed Postgres, `CREATE EXTENSION postgis` is handled
  by startup bootstrap; deploy the API with the same Dockerfile.

## Production Checklist

- [ ] Set `JWT_SECRET` env var (32+ char random string)
- [ ] Restrict CORS `allow_origins` from `*` to app bundle ID + domain
- [ ] Replace Apple IAP receipt stub with real verification
- [ ] Set up Alembic for database migrations
- [ ] Add rate limiting (slowapi)
- [ ] Move Google Places API key out of photo URLs (proxy through backend)
- [ ] Configure iOS APIClient base URL for production
- [ ] Set up Sentry for error monitoring
- [x] Deploy DB to Railway (postgis/postgis Docker image)
- [x] Deploy API to Railway (Dockerfile + railway.json)
