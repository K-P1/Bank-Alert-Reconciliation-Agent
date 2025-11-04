from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_jsonrpc_status_ok():
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


def test_jsonrpc_unimplemented_methods():
    for method in ["message/send", "execute", "unknown"]:
        payload = {"jsonrpc": "2.0", "id": method, "method": method}
        resp = client.post("/a2a/agent/bankMatcher", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == method
        assert "error" in body
        assert body["error"]["code"] == -32601
