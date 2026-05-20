# Cost Analysis

## Historical Costs (San Diego)

| Service | Amount | Details |
|---|---|---|
| Google Places API | ~$130 | ~5,600 searches at Pro tier ($0.035/call with photos) |
| Anthropic API | ~$12 | LLM extraction, vision OCR, testing |
| **Total** | **~$142** | For 5,771 restaurants, 266K menu items |

## Google Places API Pricing

| Tier | Fields included | Cost per search |
|---|---|---|
| Basic | id, name, address, location | ~$0.017 |
| Advanced | + rating, priceLevel, websiteUri, phone | ~$0.025 |
| Pro | + photos, reviews | ~$0.035 |

**Free credit:** $200/month across all Google Maps APIs. At Advanced tier ($0.025/call), that's ~8,000 free searches/month.

**Our default:** Advanced tier (no photos). Photos fetched on-demand when user views a restaurant.

## Anthropic API Pricing (Claude Haiku)

| Method | Cost per call | When used |
|---|---|---|
| LLM HTML extraction | ~$0.003 | Last resort after all free methods fail |
| PDF vision OCR | ~$0.01 | Image-based PDFs (no extractable text) |
| Image menu extraction | ~$0.01 | Menu photos on pages (confidence >= 25) |
| CSS selector learning | ~$0.001 | After LLM success, once per platform |

## Multi-Metro Cost Projections (40 US metros)

### Google Places API

| Scenario | Searches | Cost | Minus free credit |
|---|---|---|---|
| Budget (core 12 types, 5km grid) | 28,548 | $714 | $514 (1 month) |
| Budget over free tier (4 months) | 28,548 | $0 | $0 |
| Full (all 34 types, 3km grid) | ~80,000 | $2,000 | $1,800 |
| Full with photos (Pro tier) | ~80,000 | $2,800 | $2,600 |

### Anthropic LLM (deferred pass on free_only_skip restaurants)

Assumes ~150,000 total restaurants across 40 metros, ~25% needing LLM.

| Method | Est. calls | Cost |
|---|---|---|
| LLM HTML extraction | ~37,500 | ~$113 |
| PDF vision OCR | ~7,500 | ~$75 |
| Image menu vision | ~4,500 | ~$45 |
| CSS selector learning | ~7,500 | ~$8 |
| **Total Anthropic** | | **~$241** |

### Combined Totals

| Strategy | Places API | Anthropic | Total | Timeline |
|---|---|---|---|---|
| **Free tier + deferred LLM** | $0 | $241 | **$241** | ~4 months + LLM pass |
| Budget rush (1 month) | $514 | $241 | **$755** | ~1 month |
| Full coverage rush | $2,000 | $241 | **$2,241** | ~1 month |
| Full with photos | $2,800 | $241 | **$3,041** | ~1 month |

### Per-Metro Averages (budget mode)

| Metro size | Grid points | Core searches | Places cost | LLM cost |
|---|---|---|---|---|
| Large (NYC, LA) | 100-285 | 1,200-3,420 | $30-85 | ~$5 |
| Medium (Seattle, Denver) | 30-50 | 360-600 | $9-15 | ~$2 |
| Small (Providence, Milwaukee) | 9-20 | 108-240 | $3-6 | ~$1 |

## Break-Even Analysis

| Investment | Lifetime subs needed ($5 each) |
|---|---|
| Free tier approach ($241) | 49 users |
| Budget rush ($755) | 151 users |
| Full coverage ($2,241) | 449 users |
| Full with photos ($3,041) | 609 users |

## Ongoing Costs (post-launch)

| Service | Monthly |
|---|---|
| Menu refresh (30-day cycle) | ~$50-100 (mostly free methods, LLM for new restaurants) |
| Database hosting (Supabase Pro) | $25 |
| API server (Railway) | $10-20 |
| Domain + SSL | $1 |
| **Total monthly** | **~$86-146** |

Monthly break-even at $5 lifetime: need ~17-29 new users/month to sustain.
After initial user base: $0 marginal cost per user (data is shared).
