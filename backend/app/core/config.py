from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://menufinder:menufinder@localhost:5432/menufinder"
    database_url_sync: str = "postgresql://menufinder:menufinder@localhost:5432/menufinder"

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


settings = Settings()
