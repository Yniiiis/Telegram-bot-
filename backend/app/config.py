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
    # Last.fm API key: https://www.last.fm/api/account/create (search + charts; playback via Zaycev/Hitmotop).
    lastfm_api_key: str | None = None
    # Comma-separated provider ids from `catalog.SOURCE_REGISTRY` (order = try first … first hit).
    catalog_provider_chain: str = "zaycev,hitmotop,jamendo,lastfm,bandcamp,youtube_music,soundcloud,mock"
    # Search merge: drop weak tail after ranking combined multi-provider results.
    search_relevance_min_keep: float = 0.26
    # Extra provider queries: permutations / stripped brackets (bounded by MAX).
    search_deep_variants: bool = True
    search_deep_max_variants: int = 4
    # On fingerprint tie after cross-source dedupe, prefer earlier source in this list (playback: zaycev/hitmotop first).
    search_source_priority: str = (
        "zaycev,hitmotop,jamendo,lastfm,bandcamp,youtube_music,soundcloud,mock"
    )
    # Home «new releases»: background refresh interval and harvest limits (default 24h).
    new_releases_refresh_sec: int = 86400
    # On app open: re-harvest new-release candidates at most this often (seconds).
    new_releases_user_touch_sec: int = 900
    new_releases_max_collect: int = 80
    new_releases_store_limit: int = 35
    discovery_new_seed_query: str = "new music official"
    # Before returning lists (search, discovery, recommendations), drop tracks whose audio URL cannot be reached.
    track_availability_enabled: bool = True
    track_availability_concurrency: int = 8
    track_availability_timeout_sec: float = 2.5
    # Upstream relay: faster connect for quicker first audio byte.
    stream_connect_timeout_sec: float = 5.0
    stream_read_timeout_sec: float = 90.0
    # Optional: serve `STREAM_CACHE_DIR/{track_uuid}.audio` if present (Range supported). No in-request full download.
    stream_cache_dir: str | None = None
    # YouTube checks run yt-dlp per track — slow; keep off for list endpoints unless you need strict filtering.
    track_probe_youtube: bool = False
    # Optional Netscape cookies.txt for yt-dlp when the server IP is rate-limited / blocked by YouTube.
    youtube_cookies_file: str | None = None
    # Local only: enables POST /auth/dev (synthetic user). Never set in production.
    allow_dev_auth: bool = False


settings = Settings()
