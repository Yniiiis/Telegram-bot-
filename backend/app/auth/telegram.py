import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from app.config import settings


class TelegramAuthError(ValueError):
    pass


def validate_telegram_init_data(init_data: str, *, max_age_seconds: int = 86400) -> dict[str, Any]:
    if not settings.telegram_bot_token:
        raise TelegramAuthError("TELEGRAM_BOT_TOKEN is not configured")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(
        b"WebAppData",
        settings.telegram_bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramAuthError("Invalid init data signature")

    auth_date_raw = parsed.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError as exc:
            raise TelegramAuthError("Invalid auth_date") from exc
        if time.time() - auth_date > max_age_seconds:
            raise TelegramAuthError("initData is too old")

    user_raw = parsed.get("user")
    if not user_raw:
        raise TelegramAuthError("Missing user in initData")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Invalid user JSON") from exc

    if "id" not in user:
        raise TelegramAuthError("Missing user id")

    return {"query": parsed, "user": user}
