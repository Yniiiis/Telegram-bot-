import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_tokens import decode_access_token, parse_user_id_from_payload
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)
bearer_scheme_optional = HTTPBearer(auto_error=False)


async def _user_from_jwt(raw_token: str, db: AsyncSession) -> User:
    try:
        payload = decode_access_token(raw_token)
        user_id = parse_user_id_from_payload(payload)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _user_from_jwt(cred.credentials, db)


async def get_current_user_bearer_or_query_token(
    token: str | None = Query(None, description="JWT for <audio src> (no Authorization header)"),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User:
    """HTML5 <audio> cannot send Authorization; allow ?token= for /stream only."""
    raw = cred.credentials if cred else token
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return await _user_from_jwt(raw, db)
