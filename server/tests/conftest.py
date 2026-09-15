import asyncio
import os

# app.main이 모듈 임포트 시점에 settings를 한 번 읽어 CORSMiddleware 등록 여부를 정하므로,
# CORS 관련 테스트가 가능하려면 app.main을 임포트하기 전에 값을 심어둬야 한다.
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models.base import Base

CSRF_HEADERS = {"X-CSRF-Protection": "1"}


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    asyncio.run(_create_tables(engine))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    # base_url을 https로 둬야 Secure 쿠키(access_token/refresh_token)를 테스트 클라이언트가
    # 실제 브라우저처럼 저장하고 재전송한다 (http://testserver 기본값이면 Secure 쿠키가 버려짐).
    with TestClient(app, base_url="https://testserver") as test_client:
        test_client.session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def register_and_login(client, email="user@example.com", password="password123"):
    client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}, headers=CSRF_HEADERS
    )
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=CSRF_HEADERS
    )
    assert response.status_code == 200
    return response.json()["user_id"]
