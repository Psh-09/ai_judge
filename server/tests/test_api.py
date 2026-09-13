from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_rules_returns_only_active():
    with TestClient(app) as client:
        response = client.get("/api/v1/rules")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 20
    assert all(rule["active"] is True for rule in body)
    ids = {rule["rule_id"] for rule in body}
    assert "SEC-003" in ids
