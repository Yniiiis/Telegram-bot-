from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings


def create_access_token(*, user_id: int, telegram_id: int) -> str:
    now = datetime.now(tz=UTC)
    exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def parse_user_id_from_payload(payload: dict[str, Any]) -> int:
    sub = payload.get("sub")
    if sub is None:
        raise jwt.InvalidTokenError("missing sub")
    return int(sub)
