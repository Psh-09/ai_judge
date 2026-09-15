from tests.conftest import CSRF_HEADERS

ORIGIN_HEADERS = {"Origin": "http://localhost:3000"}


def test_preflight_options_gets_cors_header(client):
    response = client.options(
        "/api/v1/cases",
        headers={
            **ORIGIN_HEADERS,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-protection",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_csrf_rejection_response_still_gets_cors_header(client):
    # CSRF 미들웨어가 자체적으로 403을 반환해 call_next를 타지 않는 경로(short-circuit)라도
    # CORSMiddleware가 그 응답을 감싸고 있어야 Access-Control-Allow-Origin이 붙는다.
    # 등록 순서가 바뀌면(CORS를 CSRF보다 먼저 등록하면) 이 헤더가 통째로 사라진다.
    response = client.post(
        "/api/v1/cases",
        json={"code": "x = 1\n", "language": "python"},
        headers=ORIGIN_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_CHECK_FAILED"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_normal_authenticated_request_gets_cors_header(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "cors@example.com", "password": "password123"},
        headers={**CSRF_HEADERS, **ORIGIN_HEADERS},
    )
    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
