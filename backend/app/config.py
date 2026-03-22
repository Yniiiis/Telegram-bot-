from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/music_bot"
    telegram_bot_token: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24 * 7
    jamendo_client_id: str | None = None
    # SoundCloud api-v2 (soundcloud.com). Same API family as e.g. https://github.com/r-park/soundcloud-ngrx
    soundcloud_client_id: str | None = None
    # Zaycev official external API (https://api.zaycev.net/external). Public demo key from go-zaycevnet; override for your app if needed.
    zaycev_static_key: str | None = "kmskoNkYHDnl3ol2"
    hitmotop_base_url: str = "https://rus.hitmotop.com"
    # Comma-separated provider ids from `catalog.SOURCE_REGISTRY` (order = try first … first hit).
    catalog_provider_chain: str = "zaycev,hitmotop,jamendo,youtube_music,soundcloud,mock"
    # Search merge: drop weak tail after ranking combined multi-provider results.
    search_relevance_min_keep: float = 0.26
    # Extra provider queries: permutations / stripped brackets (bounded by MAX).
    search_deep_variants: bool = True
    search_deep_max_variants: int = 4
    # On fingerprint tie after cross-source dedupe, prefer earlier source in this list.
    search_source_priority: str = "jamendo,soundcloud,youtube_music,zaycev,hitmotop,mock"
    # Home «new releases»: background refresh interval and harvest limits (default 24h).
    new_releases_refresh_sec: int = 86400
    new_releases_max_collect: int = 80
    new_releases_store_limit: int = 35
    discovery_new_seed_query: str = "new music official"
    # Local only: enables POST /auth/dev (synthetic user). Never set in production.
    allow_dev_auth: bool = False


settings = Settings()
