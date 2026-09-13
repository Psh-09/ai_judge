import uuid

from fastapi import Request

from app.errors import ApiError
from app.services.auth import TokenError, decode_token

_UNAUTHORIZED = ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.")


async def get_current_user_id(request: Request) -> uuid.UUID:
    token = request.cookies.get("access_token")
    if token is None:
        raise _UNAUTHORIZED
    try:
        return decode_token(token, expected_type="access")
    except TokenError as exc:
        raise ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.") from exc
