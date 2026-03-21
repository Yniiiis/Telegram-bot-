import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    webapp_url: str


def _load_settings() -> Settings:
    token = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    url = os.getenv("WEBAPP_URL", "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN or TELEGRAM_BOT_TOKEN is missing. "
            "Copy bot/.env.example to bot/.env (or use root .env with Docker)."
        )
    if not url:
        raise SystemExit("WEBAPP_URL is missing (HTTPS URL of your Mini App).")
    return Settings(bot_token=token, webapp_url=url)


settings = _load_settings()
