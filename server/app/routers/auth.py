from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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


def _cookie_samesite() -> str:
    # 운영에서는 프론트/백엔드가 서로 다른 도메인(Render 서비스 두 개)이라 SameSite=Lax면
    # 크로스 사이트 요청에 쿠키가 실리지 않는다. None은 Secure 없이는 브라우저가 거부하므로
    # secure=True와 항상 함께 쓴다 — CSRF 방어는 커스텀 헤더(X-CSRF-Protection)가 맡고
    # 있어(plan.md 참고) SameSite 완화가 CSRF 보호를 약화시키지 않는다.
    return "none" if get_settings().environment == "production" else "lax"


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=True,
        samesite=_cookie_samesite(),
        path="/",
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite=_cookie_samesite(),
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
