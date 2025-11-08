from fastapi.testclient import TestClient
from fastapi import Depends
import pytest

from app.main import app
from app.db.base import get_db


def test_jsonrpc_status_ok():
    client = TestClient(app)
    payload = {
        "jsonrpc": "2.0",
        "id": "req-001",
        "method": "status",
        "params": {},
    }
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "req-001"
    assert "result" in body and body["result"]["status"] == "success"


@pytest.mark.asyncio
async def test_jsonrpc_message_send_empty_db(db_session):
    """message/send should succeed even with no data when DB is provided via override."""

    async def _override_get_db():
        async with db_session as s:  # db_session is an AsyncSession from fixture
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    try:
        client = TestClient(app)
        payload = {
            "jsonrpc": "2.0",
            "id": "req-002",
            "method": "message/send",
            "params": {"limit": 5},
        }
        resp = client.post("/a2a/agent/bankMatcher", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "req-002"
        assert "result" in body and body["result"]["status"] == "success"
        # With empty DB, expect no artifacts and batch counts of 0
        result = body["result"]
        assert isinstance(result.get("artifacts", []), list)
        meta = result.get("meta") or {}
        batch = meta.get("batch") or {}
        assert batch.get("total_emails", 0) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_jsonrpc_execute_accepts():
    client = TestClient(app)
    payload = {"jsonrpc": "2.0", "id": "req-003", "method": "execute", "params": {}}
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "req-003"
    assert "result" in body and body["result"]["status"] in ("accepted", "success")


def test_jsonrpc_unknown_method_still_unimplemented():
    client = TestClient(app)
    payload = {"jsonrpc": "2.0", "id": "unknown", "method": "unknown"}
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "unknown"
    assert "error" in body and body["error"]["code"] == -32601
