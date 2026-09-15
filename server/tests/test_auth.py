from tests.conftest import CSRF_HEADERS


def test_register_creates_user(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "user_id" in body


def test_register_does_not_require_csrf_header(client):
    response = client.post(
        "/api/v1/auth/register", json={"email": "nocsrf@example.com", "password": "password123"}
    )
    assert response.status_code == 201


def test_register_duplicate_email_returns_409(client):
    payload = {"email": "dup@example.com", "password": "password123"}
    client.post("/api/v1/auth/register", json=payload)
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_success_sets_cookies_and_body_has_no_tokens(client):
    client.post(
        "/api/v1/auth/register", json={"email": "login@example.com", "password": "password123"}
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": "login@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"user_id", "email"}

    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) == 2
    joined = " | ".join(set_cookie_headers)
    assert "access_token=" in joined
    assert "refresh_token=" in joined
    for header in set_cookie_headers:
        assert "HttpOnly" in header
        assert "Secure" in header
        assert "samesite=lax" in header.lower()


def test_login_in_production_sets_samesite_none(client, monkeypatch):
    # 프론트(codecourt-client)와 백엔드(codecourt-api)가 서로 다른 Render 도메인이라
    # SameSite=Lax로는 크로스 사이트 요청에 쿠키가 실리지 않는다 — 운영에서만 None으로
    # 완화한다(항상 Secure와 함께, CSRF는 커스텀 헤더가 별도로 방어).
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "environment", "production")
    client.post(
        "/api/v1/auth/register", json={"email": "prod-samesite@example.com", "password": "password123"}
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": "prod-samesite@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) == 2
    for header in set_cookie_headers:
        assert "samesite=none" in header.lower()
        assert "Secure" in header


def test_login_does_not_require_csrf_header(client):
    client.post(
        "/api/v1/auth/register", json={"email": "login2@example.com", "password": "password123"}
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": "login2@example.com", "password": "password123"}
    )
    assert response.status_code == 200


def test_login_wrong_password_returns_401(client):
    client.post(
        "/api/v1/auth/register", json={"email": "wrongpw@example.com", "password": "password123"}
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "not-it"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_returns_401(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "whatever1"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_refresh_without_cookie_returns_401(client):
    response = client.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_refresh_without_csrf_header_returns_403(client):
    client.post(
        "/api/v1/auth/register", json={"email": "refresh@example.com", "password": "password123"}
    )
    client.post(
        "/api/v1/auth/login", json={"email": "refresh@example.com", "password": "password123"}
    )
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_CHECK_FAILED"


def test_refresh_with_valid_cookie_reissues_access_token(client):
    client.post(
        "/api/v1/auth/register", json={"email": "refresh2@example.com", "password": "password123"}
    )
    client.post(
        "/api/v1/auth/login", json={"email": "refresh2@example.com", "password": "password123"}
    )
    response = client.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(h.startswith("access_token=") for h in set_cookie_headers)


def test_access_token_cookie_alone_cannot_refresh(client):
    # access_token 쿠키만 있고 refresh_token 쿠키가 없으면 재발급이 거부되어야 한다
    # (access_token 쿠키를 요구하면 안 되는 엔드포인트이므로, refresh_token 부재가 곧 실패 사유)
    client.post(
        "/api/v1/auth/register", json={"email": "onlyaccess@example.com", "password": "password123"}
    )
    client.post(
        "/api/v1/auth/login", json={"email": "onlyaccess@example.com", "password": "password123"}
    )
    client.cookies.delete("refresh_token")
    response = client.post("/api/v1/auth/refresh", headers=CSRF_HEADERS)
    assert response.status_code == 401


def test_logout_clears_cookies_and_blocks_further_access(client):
    client.post(
        "/api/v1/auth/register", json={"email": "logout@example.com", "password": "password123"}
    )
    client.post("/api/v1/auth/login", json={"email": "logout@example.com", "password": "password123"})

    response = client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert len(set_cookie_headers) == 2
    for header in set_cookie_headers:
        # 삭제 쿠키는 Max-Age=0(또는 과거 Expires)으로 내려온다 — TestClient의 쿠키 jar도
        # 이를 실제 브라우저처럼 반영해 이후 요청에서 쿠키를 보내지 않는다.
        assert "Max-Age=0" in header

    protected = client.get("/api/v1/cases")
    assert protected.status_code == 401


def test_logout_without_csrf_header_returns_403(client):
    client.post(
        "/api/v1/auth/register", json={"email": "logout2@example.com", "password": "password123"}
    )
    client.post("/api/v1/auth/login", json={"email": "logout2@example.com", "password": "password123"})
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_CHECK_FAILED"


def test_logout_is_idempotent_without_existing_session(client):
    response = client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
