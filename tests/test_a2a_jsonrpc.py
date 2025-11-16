from fastapi.testclient import TestClient
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
    """Test that execute method returns automation control response."""
    client = TestClient(app)

    # Test start_automation action
    payload = {
        "jsonrpc": "2.0",
        "id": "req-003",
        "method": "execute",
        "params": {"action": "start_automation"},
    }
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "req-003"

    # Check for Telex Message format
    assert "result" in body
    result = body["result"]
    assert result["kind"] == "message"
    assert "parts" in result
    parts = result["parts"]
    assert len(parts) >= 1

    # First part should be text
    text_part = parts[0]
    assert text_part["kind"] == "text"
    assert "Automation" in text_part["text"]

    # Should have data part with status
    data_parts = [p for p in parts if p.get("kind") == "data"]
    assert len(data_parts) >= 1
    status_data = data_parts[0]["data"]
    assert "running" in status_data


def test_jsonrpc_unknown_method_still_unimplemented():
    client = TestClient(app)
    payload = {"jsonrpc": "2.0", "id": "unknown", "method": "unknown"}
    resp = client.post("/a2a/agent/bankMatcher", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "unknown"
    assert "error" in body and body["error"]["code"] == -32601
