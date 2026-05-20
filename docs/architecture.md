# Architecture

## Components

| Component | Location | Purpose |
|---|---|---|
| API Server | `backend/app/` | FastAPI. Serves search, auth, favorites. Lightweight, no scraping. |
| Scrape Worker | `backend/scripts/scrape_worker.py` | Standalone process. Discovers restaurants, scrapes menus, writes to DB. |
| Multi-Metro Runner | `backend/scripts/run_all_metros.py` | Orchestrates scrape worker across US metros in population order. |
| iOS App | `MenuFinder/` | SwiftUI client. Map search, autocomplete, restaurant detail, favorites. |
| PostgreSQL + PostGIS | Docker, port 5433 | Geospatial data, full-text search, trigram similarity. |

## Database Schema

| Table | Purpose | Key columns |
|---|---|---|
| `restaurants` | Restaurant master records | google_place_id (unique), location (PostGIS POINT), menu_last_scraped_at |
| `menu_items` | Scraped menu items | name, description, price, category, search_vector (TSVECTOR) |
| `scraping_patterns` | Learned CSS selectors by platform | platform_type, selectors (JSONB), success_count |
| `scrape_failures` | Failed scraping for retry | error_type, extractor_version, resolved |
| `scrape_checkpoints` | Resume position per metro grid | metro_name (unique), grid_index, food_type_index |
| `search_cache` | Query result caching | query_hash (SHA256), results (JSONB), expires_at |
| `users` | User accounts | email (unique), password_hash (bcrypt), is_admin |
| `subscriptions` | Premium subscription state | tier (free/trial/lifetime), expires_at, is_active |
| `favorite_items` | Saved menu items (premium) | user_id, menu_item_id |
| `favorite_restaurants` | Saved restaurants (premium) | user_id, restaurant_id |

Required extensions: `postgis`, `uuid-ossp`, `pg_trgm`

## Scraping Pipeline

Priority order (cheapest → most expensive):
1. JSON-LD / Schema.org (free)
2. Platform CSS extractors (free) — Toast, Squarespace, WordPress, Wix, BentoBox, Popmenu
3. Learned CSS patterns (free) — from `scraping_patterns` table
4. Price heuristics (free) — regex for $XX.XX patterns
5. PDF text extraction (free) — pdfplumber
6. PDF vision OCR (~$0.01) — Claude Haiku vision
7. Image menu extraction (~$0.01) — Claude Haiku vision, confidence >= 25
8. LLM HTML extraction (~$0.003) — Claude Haiku, last resort

`--free-only` flag skips steps 6-8.

## Search Ranking

Two-tier relevance with TF-IDF/BM25 scoring:
- **Tier 1:** Perfect name matches within 3 miles, sorted by distance
- **Tier 2:** Everything else, ranked by IDF relevance + distance penalty

Additional features:
- Word boundary matching (prevents "mac" matching "macchiato")
- Co-occurrence boosting (if "mac" appears with "cheese" 70%+ of the time, "Lobster Mac" gets near-perfect score)
- Food synonym expansion (mac ↔ macaroni, bbq ↔ barbecue, etc.)
- Per-restaurant item ranking with `total_matched_items` for "+N more" UI

## Auth / Premium

| Tier | Behavior | Duration |
|---|---|---|
| free | Can search, no favorites | Indefinite |
| trial | All features | 7 days from signup |
| lifetime | All features | Forever ($5 one-time) |

JWT auth (HS256, 30-day expiry). Apple IAP receipt validation is **stubbed** — needs real implementation before production.

## Multi-Metro Scraping

- 40 US metros defined in `app/data/metro_grids.py` as bounding boxes
- Auto-generated grids at configurable spacing (default 5km budget, 2-3km full)
- Checkpoint/resume via `scrape_checkpoints` table
- Budget control: `--monthly-budget N` stops after N Places API calls
- Free tier (8,000 searches/month) covers ~11 metros/month at budget settings
