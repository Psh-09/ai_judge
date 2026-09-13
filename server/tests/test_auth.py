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
