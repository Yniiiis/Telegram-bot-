from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def upsert_user_from_telegram(session: AsyncSession, tg_user: dict) -> User:
    telegram_id = int(tg_user["id"])
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.username = tg_user.get("username")
        user.first_name = tg_user.get("first_name")
        user.last_name = tg_user.get("last_name")
        user.language_code = tg_user.get("language_code")
        await session.commit()
        await session.refresh(user)
        return user

    user = User(
        telegram_id=telegram_id,
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
        last_name=tg_user.get("last_name"),
        language_code=tg_user.get("language_code"),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
