from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ApiError
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserSummary
from app.services.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(tags=["auth"])


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", operation_id="registerUser", status_code=201, response_model=UserSummary)
async def register_user(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(409, "EMAIL_ALREADY_REGISTERED", "이미 가입된 이메일입니다.") from exc
    return UserSummary(user_id=user.id, email=user.email)


@router.post("/auth/login", operation_id="loginUser", response_model=UserSummary)
async def login_user(body: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)):
    user = (await session.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.")

    _set_access_cookie(response, create_access_token(user.id))
    _set_refresh_cookie(response, create_refresh_token(user.id))
    return UserSummary(user_id=user.id, email=user.email)


@router.post("/auth/refresh", operation_id="refreshToken")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if token is None:
        raise ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    try:
        user_id = decode_token(token, expected_type="refresh")
    except TokenError as exc:
        raise ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.") from exc

    _set_access_cookie(response, create_access_token(user_id))
    return {"ok": True}
