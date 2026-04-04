"""Authenticated client diagnostics (Telegram WebView cannot reach dev-machine ingest URLs)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["client-debug"])


class ClientDebugIn(BaseModel):
    hypothesis_id: str | None = Field(None, max_length=32)
    location: str = Field(..., max_length=160)
    message: str = Field(..., max_length=500)
    data: dict[str, Any] | None = None


@router.post("/client-debug")
@router.post("/api/client-debug")
async def client_debug(body: ClientDebugIn, user: User = Depends(get_current_user)) -> dict[str, str]:
    logger.info(
        "client_debug user_id=%s hypothesis_id=%s location=%s message=%s data=%s",
        user.id,
        body.hypothesis_id,
        body.location,
        body.message,
        body.data,
    )
    return {"ok": "1"}
