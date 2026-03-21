from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/music_bot"
    telegram_bot_token: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24 * 7
    jamendo_client_id: str | None = None
    # Zaycev official external API (https://api.zaycev.net/external). Public demo key from go-zaycevnet; override for your app if needed.
    zaycev_static_key: str | None = "kmskoNkYHDnl3ol2"
    hitmotop_base_url: str = "https://rus.hitmotop.com"
    # Comma-separated provider ids from `catalog.SOURCE_REGISTRY` (order = try first … first hit).
    catalog_provider_chain: str = "zaycev,hitmotop,jamendo,mock"
    # Local only: enables POST /auth/dev (synthetic user). Never set in production.
    allow_dev_auth: bool = False


settings = Settings()
