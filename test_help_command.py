"""
Test script to demonstrate the updated /help command with parameter information.
"""
import httpx
import json

# Test endpoint (assuming server is running on port 8000)
url = "http://localhost:8000/a2a/agent/BARA"

# Test the help command
payload = {
    "jsonrpc": "2.0",
    "id": "test-help",
    "method": "message/send",
    "params": {
        "message": {
            "kind": "message",
            "role": "user",
            "parts": [{"kind": "text", "text": "help"}],
        }
    },
}

try:
    with httpx.Client() as client:
        response = client.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        print("=" * 80)
        print("BARA /help Command Response")
        print("=" * 80)
        print()
        
        if "result" in result:
            message = result["result"]
            
            # Extract text from parts
            for part in message.get("parts", []):
                if part.get("kind") == "text":
                    print(part["text"])
                    print()
            
            print("=" * 80)
            print("Response Format Check:")
            print(f"  ✓ Message kind: {message.get('kind')}")
            print(f"  ✓ Role: {message.get('role')}")
            print(f"  ✓ Parts count: {len(message.get('parts', []))}")
            print("=" * 80)
        else:
            print("Error:", result.get("error"))
        
except httpx.ConnectError:
    print("❌ Error: Could not connect to server.")
    print("Make sure the server is running: uvicorn app.main:app --reload --port 8000")
except Exception as e:
    print(f"❌ Error: {e}")
