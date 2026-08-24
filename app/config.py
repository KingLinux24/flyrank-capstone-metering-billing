from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = "dev-only-not-for-production"
    database_url: str = "sqlite+pysqlite:///./data/billing.db"

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_pro_price_id: str = ""
    stripe_success_url: str = "http://localhost:8000/v1/checkout/success"
    stripe_cancel_url: str = "http://localhost:8000/v1/checkout/cancel"
    public_base_url: str = "http://localhost:8000"

    rollup_interval_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
