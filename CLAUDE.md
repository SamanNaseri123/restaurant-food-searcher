# MenuFinder

Restaurant menu search engine — search for food items, find nearby restaurants that serve them.

## Documentation

| Document | What it covers |
|---|---|
| [Philosophy & Rules](docs/philosophy.md) | Core principles that drive all decisions: cost consciousness, lifecycle thinking, testing conventions, monetization strategy |
| [Architecture](docs/architecture.md) | System components, database schema, scraping pipeline, search ranking, auth/premium, multi-metro scraping |
| [Operations](docs/operations.md) | Running locally, scraper commands, resolution tiers, schema changes, DB queries, admin ops, production checklist |
| [Costs](docs/costs.md) | Historical costs, API pricing, multi-metro projections, break-even analysis, ongoing costs |

## Quick Reference

Project uses [uv](https://docs.astral.sh/uv/). All commands run from `backend/`.

**Start everything:**
```bash
cd backend
docker compose up -d
uv run uvicorn app.main:app --port 8000
```

**Run scraper (separate terminal):**
```bash
uv run python scripts/scrape_worker.py --grid new_york --free-only --monthly-budget 8000
```

**Run tests:**
```bash
uv run pytest -v
```

Fallback without uv: Python 3.12 at `C:\Users\amirs\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

## Critical Rules (read [Philosophy](docs/philosophy.md) for full context)

- **Scraping NEVER runs inside uvicorn** — use the standalone worker
- **Schema changes need manual ALTER TABLE** — no Alembic, `create_all()` only handles new tables
- **Default to cheapest option** — all cost-increasing features behind CLI flags
- **Word boundaries for search matching** — `\y` in PostgreSQL, `\b` in Python
- **Apple IAP receipt validation is STUBBED** — do not deploy to production without real verification
- **Python not on PATH** — use `C:\Users\amirs\AppData\Local\Programs\Python\Python312\python.exe`
- **PostgreSQL on port 5433** — not 5432 (local Postgres occupies that)
