from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_tokens import create_access_token
from app.auth.telegram import TelegramAuthError, validate_telegram_init_data
from app.config import settings
from app.db.session import get_db
from app.schemas.auth import AuthUserOut, TelegramAuthRequest, TelegramAuthResponse
from app.services.users import upsert_user_from_telegram

router = APIRouter(tags=["auth"])

_DEV_TELEGRAM_ID = 999_999_999


@router.post("/auth/telegram", response_model=TelegramAuthResponse)
async def auth_telegram(body: TelegramAuthRequest, db: AsyncSession = Depends(get_db)) -> TelegramAuthResponse:
    try:
        parsed = validate_telegram_init_data(body.init_data)
    except TelegramAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    tg_user = parsed["user"]
    user = await upsert_user_from_telegram(db, tg_user)
    token = create_access_token(user_id=user.id, telegram_id=user.telegram_id)
    return TelegramAuthResponse(
        access_token=token,
        user=AuthUserOut(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
        ),
    )


@router.post(
    "/auth/dev",
    response_model=TelegramAuthResponse,
    include_in_schema=False,
)
async def auth_dev(db: AsyncSession = Depends(get_db)) -> TelegramAuthResponse:
    """Mint a real JWT for a fixed local user. Gated by ALLOW_DEV_AUTH=1 in .env."""
    if not settings.allow_dev_auth:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    tg_user = {
        "id": _DEV_TELEGRAM_ID,
        "username": "local_dev",
        "first_name": "Local",
        "last_name": "Dev",
        "language_code": "en",
    }
    user = await upsert_user_from_telegram(db, tg_user)
    token = create_access_token(user_id=user.id, telegram_id=user.telegram_id)
    return TelegramAuthResponse(
        access_token=token,
        user=AuthUserOut(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
        ),
    )
