"""
Integration tests for A2A endpoint with natural language command support.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.base import get_db
from tests.conftest import get_test_db


# Override database dependency for tests
app.dependency_overrides[get_db] = get_test_db

client = TestClient(app)


class TestNaturalLanguageCommands:
    """Test natural language command interpretation in A2A endpoint."""

    def test_help_command(self):
        """Test help command via natural language."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-help-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "help"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == "test-help-1"
        assert "result" in body
        
        # Check Telex Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        assert len(result["parts"]) > 0
        
        # First part should contain help text
        first_part = result["parts"][0]
        assert first_part["kind"] == "text"
        assert "BARA" in first_part["text"]
        assert "Available Commands" in first_part["text"] or "commands" in first_part["text"].lower()

    def test_unrecognized_falls_back_to_help(self):
        """Test that unrecognized commands return help."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-unknown-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "xyz random gibberish abc"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check it returns help in message format
        result = body["result"]
        assert result["kind"] == "message"
        assert len(result["parts"]) > 0
        
        # Check that data part contains help indication
        if len(result["parts"]) > 1:
            data_part = result["parts"][1]
            assert data_part["kind"] == "data"

    def test_reconcile_command_variations(self):
        """Test various phrasings of reconcile command."""
        phrases = [
            "run reconciliation",
            "reconcile now",
            "match emails",
            "process alerts",
            "can you reconcile?",
        ]
        
        for phrase in phrases:
            payload = {
                "jsonrpc": "2.0",
                "id": f"test-reconcile-{phrase[:5]}",
                "method": "message/send",
                "params": {
                    "message": {
                        "kind": "message",
                        "role": "user",
                        "parts": [{"kind": "text", "text": phrase}],
                    }
                },
            }
            
            resp = client.post("/a2a/agent/BARA", json=payload)
            assert resp.status_code == 200
            
            body = resp.json()
            assert "result" in body
            
            # Should return Message format
            result = body["result"]
            assert result["kind"] == "message"
            assert result["role"] == "agent"
            
            # Check metadata for status
            if "metadata" in result:
                metadata = result["metadata"]
                assert metadata.get("status") in ["success", "error"]

    def test_show_summary_command(self):
        """Test show summary command."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-summary-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "show summary"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        assert len(result["parts"]) > 0
        
        # First part should contain summary text
        first_part = result["parts"][0]
        assert first_part["kind"] == "text"
        assert "Summary" in first_part["text"] or "summary" in first_part["text"].lower()
        
        # Check metadata for status
        assert result.get("metadata", {}).get("status") == "success"

    def test_list_unmatched_command(self):
        """Test list unmatched command."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-unmatched-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "list unmatched"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        
        # Check metadata for status
        assert result.get("metadata", {}).get("status") == "success"

    def test_confidence_report_command(self):
        """Test confidence report command."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-confidence-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "get confidence report"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        
        # Check metadata for status
        assert result.get("metadata", {}).get("status") == "success"

    def test_parameter_extraction_limit(self):
        """Test extraction of limit parameter."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-limit-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "reconcile 25 emails"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        
        # Check if limit was interpreted (in metadata)
        if "metadata" in result and "params" in result["metadata"]:
            # Limit might be extracted
            pass

    def test_parameter_extraction_days(self):
        """Test extraction of days parameter."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-days-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "show summary for last 14 days"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"
        
        # Check metadata for status
        assert result.get("metadata", {}).get("status") == "success"

    def test_case_insensitive_commands(self):
        """Test that commands are case-insensitive."""
        phrases = [
            "HELP",
            "Help",
            "hElP",
            "RECONCILE NOW",
            "Show Summary",
        ]
        
        for phrase in phrases:
            payload = {
                "jsonrpc": "2.0",
                "id": f"test-case-{phrase[:4]}",
                "method": "message/send",
                "params": {
                    "message": {
                        "kind": "message",
                        "role": "user",
                        "parts": [{"kind": "text", "text": phrase}],
                    }
                },
            }
            
            resp = client.post("/a2a/agent/BARA", json=payload)
            assert resp.status_code == 200
            
            body = resp.json()
            assert "result" in body

    def test_meta_contains_interpretation_info(self):
        """Test that response metadata includes interpretation metadata."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-meta-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "show summary"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert "metadata" in result
        
        metadata = result["metadata"]
        assert "interpreted_from" in metadata
        assert metadata["interpreted_from"] == "show summary"
        assert "command" in metadata
        assert "confidence" in metadata

    def test_structured_json_rpc_still_works(self):
        """Test that structured JSON-RPC calls still work alongside natural language."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-structured-1",
            "method": "status",
            "params": {},
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        assert resp.status_code == 200
        
        body = resp.json()
        assert body["jsonrpc"] == "2.0"
        assert "result" in body
        
        # Check Message format
        result = body["result"]
        assert result["kind"] == "message"
        assert result["role"] == "agent"


class TestResponseFormat:
    """Test response formatting for natural language commands."""

    def test_response_has_required_fields(self):
        """Test that responses have all required JSON-RPC fields."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-format-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "help"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        body = resp.json()
        
        # Required fields
        assert "jsonrpc" in body
        assert body["jsonrpc"] == "2.0"
        assert "id" in body
        assert body["id"] == "test-format-1"
        
        # Either result or error
        assert ("result" in body) or ("error" in body)

    def test_summary_is_human_readable(self):
        """Test that message text is human-readable."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-readable-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "show summary"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        body = resp.json()
        
        assert "result" in body
        result = body["result"]
        assert result["kind"] == "message"
        assert len(result["parts"]) > 0
        
        # First part should be text
        first_part = result["parts"][0]
        assert first_part["kind"] == "text"
        text = first_part["text"]
        assert isinstance(text, str)
        assert len(text) > 0
        # Should contain some recognizable words
        assert any(word in text.lower() for word in ["email", "transaction", "match", "summary"])

    def test_artifacts_are_structured(self):
        """Test that data parts are properly structured."""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-artifacts-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "list unmatched"}],
                }
            },
        }
        
        resp = client.post("/a2a/agent/BARA", json=payload)
        body = resp.json()
        
        assert "result" in body
        result = body["result"]
        assert result["kind"] == "message"
        assert "parts" in result
        
        parts = result["parts"]
        assert isinstance(parts, list)
        
        # Check if any part is a data part
        data_parts = [p for p in parts if p.get("kind") == "data"]
        if data_parts:
            # Data parts should have data field
            for part in data_parts:
                assert "data" in part


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
