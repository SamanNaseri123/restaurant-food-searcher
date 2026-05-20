from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://menufinder:menufinder@localhost:5433/menufinder"
    database_url_sync: str = "postgresql://menufinder:menufinder@localhost:5433/menufinder"

    google_places_api_key: str = ""
    anthropic_api_key: str = ""

    # Search defaults
    default_search_radius_meters: int = 5000
    max_search_radius_meters: int = 25000
    max_results: int = 50

    # Scraping
    menu_cache_days: int = 30
    llm_model: str = "claude-haiku-4-5-20251001"
    max_concurrent_scrapes: int = 5

    # App
    app_name: str = "MenuFinder API"
    debug: bool = False

    # Auth
    jwt_secret: str = "dev-secret-CHANGE-IN-PRODUCTION-needs-32+-chars"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 30  # 30 days

    # Premium
    trial_days: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("database_url")
    @classmethod
    def _ensure_async_driver(cls, v: str) -> str:
        """Normalize the DB URL: strip whitespace and use the asyncpg driver.

        Hosted Postgres providers (Railway, Render, Heroku) hand out URLs like
        `postgres://...` or `postgresql://...`. SQLAlchemy's async engine needs
        the `postgresql+asyncpg://` form, so rewrite the scheme if needed.

        Also strips surrounding whitespace — a stray trailing newline pasted
        into a dashboard env var otherwise corrupts the database name.
        """
        v = v.strip()
        if v.startswith("postgresql+asyncpg://"):
            return v
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()
