# Rules & Philosophy

These principles govern all development decisions on this project. Every other doc inherits from these.

## Cost Consciousness
- Every API call costs real money. Minimize external API usage by default.
- Always try the cheapest method first, fall back to expensive methods only when cheap ones fail.
- All cost-increasing features must be behind CLI flags, not hardcoded. The default should be the cheapest option.
- Never burn budget on retrying something that will fail the same way. Track failures with version stamps and only retry when the underlying method has improved.

## Lifecycle Thinking
- Before implementing any system, think through the full lifecycle: what happens when it succeeds, fails, is retried, and is eventually fixed?
- If the user has to remember to run a command, that's a design smell — automate it.
- When something fails, classify the failure type so it can be addressed systematically later.

## Separation of Concerns
- Scraping runs as a standalone worker process. NEVER inside the API server — it crashes under load.
- The API server is lightweight and fast. It only reads the database.
- Claude Max tokens and API credits are completely separate billing systems. API credits are scarce; Max is not.

## Database Discipline
- No Alembic migrations. `create_all()` handles new tables, but adding columns to existing tables requires manual `ALTER TABLE`.
- Always test the worker after schema changes before telling the user to run it.
- PostGIS geometry columns need `geography` cast for distance calculations in meters (not degrees).

## Search Quality
- Use word boundaries (`\b` in Python, `\y` in PostgreSQL) for matching — "mac" should match "Lobster Mac" but NOT "Macchiato".
- Food synonyms (mac ↔ macaroni, bbq ↔ barbecue) are in `app/services/food_synonyms.py`. Expand them when users report missed matches.
- IDF/co-occurrence scoring is computed per-search from local menu data. Results adapt to each city's menu language.

## Testing
- TDD: write failing tests BEFORE implementation.
- AAA pattern: Arrange-Act-Assert.
- Test names describe behavior: `test_should_return_empty_when_no_items`.
- Unit tests with mocks (no live DB required). Integration tests are skipped.

## Reversibility
- Cost-saving measures are always parameterized (CLI flags), never permanent.
- Lower-resolution scraping can always be upgraded later by re-running with different flags.
- The checkpoint system allows stopping and resuming at any point.

## Premium / Monetization
- Free tier must be useful enough that users don't bounce.
- Premium features are gated by `require_premium` dependency. Never block core search for free users.
- 7-day free trial auto-granted on signup. $5 lifetime purchase.
- Apple IAP receipt validation is STUBBED. Do not deploy to production without real validation.
