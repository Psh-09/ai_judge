CSRF_HEADER_NAME = "X-CSRF-Protection"
CSRF_HEADER_VALUE = "1"

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 쿠키 인증 없이 호출되는 엔드포인트는 CSRF 검사 대상이 아니다(위조할 기존 세션이 없음).
CSRF_EXEMPT_PATHS = {"/api/v1/auth/register", "/api/v1/auth/login"}


def requires_csrf_check(method: str, path: str) -> bool:
    return method in STATE_CHANGING_METHODS and path not in CSRF_EXEMPT_PATHS
