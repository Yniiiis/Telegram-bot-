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

    new_releases_refresh_sec: int = 86400
    new_releases_user_touch_sec: int = 900
    new_releases_max_collect: int = 80
    new_releases_store_limit: int = 35
    discovery_new_seed_query: str = "new music official"

    stream_connect_timeout_sec: float = 5.0
    stream_read_timeout_sec: float = 90.0
    stream_cache_dir: str | None = None

    # httpx: catalog (Hitmotop HTML) — pooled keep-alive, bounded concurrency
    httpx_catalog_max_connections: int = 48
    httpx_catalog_max_keepalive: int = 24
    httpx_catalog_timeout_sec: float = 60.0
    # HTTP/2 + Brotli (smaller HTML, one connection); set false if upstream misbehaves
    httpx_catalog_http2: bool = True
    # One GET at startup to warm TLS + pool (cuts first-user latency)
    hitmotop_warmup_on_startup: bool = True

    # httpx: MP3 relay — separate pool from catalog (avoids starving search vs many streams)
    httpx_stream_max_connections: int = 96
    httpx_stream_max_keepalive: int = 48

    # In-memory search cache (LRU + TTL)
    search_cache_ttl_sec: float = 300.0
    search_cache_max_entries: int = 512

    # API rate limit (0 = off). Applies to /search* and /stream/* per client IP / X-Forwarded-For.
    api_rate_limit_per_minute: int = 0

    # Hitmotop HTTP: retry on 429 / transient errors
    hitmotop_http_max_attempts: int = 3
    hitmotop_http_retry_backoff_sec: float = 0.6

    # Quick search (Mini App): shorter upstream timeout, smaller default cap from router
    hitmotop_search_quick_timeout_sec: float = 12.0
    hitmotop_search_normal_timeout_sec: float = 22.0

    # Observability
    hitmotop_log_parse_ms: bool = True

    allow_dev_auth: bool = False


settings = Settings()
