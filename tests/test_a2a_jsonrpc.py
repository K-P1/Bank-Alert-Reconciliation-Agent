from fastapi.testclient import TestClient
from fastapi import Depends
import pytest

from app.main import app
from app.db.base import get_db


def test_jsonrpc_status_ok():
    """Test that status method returns a proper Message response."""
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
    
    # Check for Telex Message format
    assert "result" in body
    result = body["result"]
    assert result["kind"] == "message"
    assert result["role"] == "agent"
    assert "parts" in result
    assert len(result["parts"]) > 0
    
    # First part should be text with status message
    first_part = result["parts"][0]
    assert first_part["kind"] == "text"
    assert "healthy" in first_part["text"].lower()


@pytest.mark.asyncio
async def test_jsonrpc_message_send_empty_db(db_session):
    """message/send should return proper Message format even with no data."""

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
        
        # Check for Telex Message format
        assert "result" in body
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        assert "parts" in result
        
        # Check metadata has batch info
        metadata = result.get("metadata", {})
        batch = metadata.get("batch", {})
        assert batch.get("total_emails", 0) == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_jsonrpc_execute_accepts():
    """Test that execute method returns a proper Task response."""
    client = TestClient(app)
    payload = {"jsonrpc": "2.0", "id": "req-003", "method": "execute", "params": {}}
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "req-003"
    
    # Check for Telex Task format
    assert "result" in body
    result = body["result"]
    assert "id" in result  # Task ID
    assert "status" in result
    status = result["status"]
    assert status["state"] in ("pending", "running", "completed", "failed")
    assert "message" in status or "progress" in status


def test_jsonrpc_unknown_method_still_unimplemented():
    client = TestClient(app)
    payload = {"jsonrpc": "2.0", "id": "unknown", "method": "unknown"}
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "unknown"
    assert "error" in body and body["error"]["code"] == -32601
