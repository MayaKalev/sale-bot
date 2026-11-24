from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_token: str = ""
    anthropic_api_key: str = ""
    imap_user: str = ""
    imap_password: str = ""
    imap_host: str = "imap.gmail.com"

    db_url: str = "sqlite+aiosqlite:///salebot.db"
    newsletter_interval_min: int = 5
    price_check_interval_hours: float = 4
    price_drop_min_pct: float = 1.0
    max_fetch_failures: int = 5
    llm_model: str = "claude-haiku-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
