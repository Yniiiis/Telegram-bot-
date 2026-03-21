from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., min_length=10)


class AuthUserOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut
