from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/music_bot"
    telegram_bot_token: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24 * 7

    hitmotop_base_url: str = "https://rus.hitmotop.com"
    # Listing page with track links (e.g. year chart).
    hitmotop_charts_path: str = "/2026"
    # JadeMusic-style parsing (github.com/nshib00/jademusic-api): track__info + track__download-btn.
    hitmotop_use_jade_selectors: bool = True
    # /search/start/{48*n}?q= pagination like HitmoData in jademusic-api (faster paging).
    hitmotop_search_start_pagination: bool = True
    hitmotop_page_size: int = 48
    # Optional: https://gde-hitmo.org/ — resolve current mirror (see jademusic hitmo/url.py).
    hitmotop_mirror_lookup_url: str | None = None
    catalog_provider_chain: str = "hitmotop"

    new_releases_refresh_sec: int = 86400
    new_releases_user_touch_sec: int = 900
    new_releases_max_collect: int = 80
    new_releases_store_limit: int = 35
    discovery_new_seed_query: str = "new music official"

    stream_connect_timeout_sec: float = 5.0
    stream_read_timeout_sec: float = 90.0
    stream_cache_dir: str | None = None

    allow_dev_auth: bool = False


settings = Settings()
