# Telex Commands Reference - BARA Core

**Document Version:** 3.0 (BARA Core Specification)  
**Last Updated:** 2025-01-16  
**System:** Bank Alert Reconciliation Agent (BARA)  
**Total Active Commands:** 12

---

## Overview

BARA's A2A endpoint supports natural language command interpretation through a regex-based command interpreter. This allows Telex users to interact with the system using plain English instead of JSON-RPC method calls.

**Endpoint:** `POST /a2a/agent/bara`  
**Method:** `message/send`  
**Latency:** <100ms average response time  
**Interpreter:** Zero-LLM, deterministic pattern matching

**Changes in v3.0 (BARA Core):**

- Simplified from 22 to 12 core commands
- Removed workflow/action system (not in core specification)
- Removed individual service control commands (replaced with unified automation)
- Consolidated status/metrics commands
- All commands fully implemented and tested

---

## Command Categories

### Data Operations (5 commands)

1. `match_now` - Run reconciliation matching
2. `fetch_emails_now` - Fetch new bank alert emails
3. `fetch_transactions_now` - Poll for new transactions
4. `show_summary` - Display reconciliation summary
5. `list_unmatched` - Show unmatched items

### Automation Control (3 commands)

6. `get_status` - Get automation service status
7. `start_automation` - Start automated cycles
8. `stop_automation` - Stop automated cycles

### Analytics & Diagnostics (3 commands)

9. `show_metrics` - Display performance metrics
10. `show_logs` - Show recent activity logs
11. `manual_match` - Manually match specific items

### Utility (1 command)

12. `help` - Show available commands

---

## Command Details

### 1. `match_now` ✅

**Purpose:** Run reconciliation matching immediately to match bank alerts with transactions

**Handler:** `CommandHandlers.match_now()`  
**Renamed from:** `reconcile_now` (v2.0)

#### Recognized Patterns

```regex
\bmatch\s+(now|emails?|alerts?|transactions?)\b
\brun\s+(the\s+)?(reconciliation|matching)\b
\breconcile\b
\bstart\s+matching\b
\bprocess\s+(emails?|alerts?)\b
```

#### Examples

```text
"match now"
"run reconciliation"
"match 50 emails"
"process alerts"
"reconcile emails"
"start matching"
```

#### Extracted Parameters

| Parameter | Type   | Description                 | Example                |
| --------- | ------ | --------------------------- | ---------------------- |
| `limit`   | `int`  | Number of emails to process | "match 50 emails" → 50 |
| `rematch` | `bool` | Force re-matching           | "rematch all" → true   |

#### Example Request

```json
{
  "jsonrpc": "2.0",
  "id": "cmd-001",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "parts": [{ "text": "match 100 emails" }]
    }
  }
}
```

#### Example Response

```json
{
  "jsonrpc": "2.0",
  "id": "cmd-001",
  "result": {
    "success": true,
    "artifacts": [
      {
        "type": "text",
        "content": "✓ Matched 45/100 emails\n\nMatches created: 45\n..."
      }
    ]
  }
}
```

---

### 2. `fetch_emails_now` ✅

**Purpose:** Manually trigger email fetching from IMAP server

**Handler:** `CommandHandlers.fetch_emails_now()`  
**Renamed from:** `fetch_emails` (v2.0)

#### Recognized Patterns

```regex
\bfetch\s+(new\s+)?(emails?|alerts?)\b
\bget\s+(new\s+)?(emails?|alerts?)\b
\bcheck\s+(for\s+)?(new\s+)?(emails?|alerts?)\b
\bretrieve\s+emails?\b
```

#### Examples

```text
"fetch emails now"
"get new alerts"
"check for emails"
"retrieve emails"
"fetch new bank alerts"
```

---

### 3. `fetch_transactions_now` ✅

**Purpose:** Manually trigger transaction polling from API

**Handler:** `CommandHandlers.fetch_transactions_now()`  
**Renamed from:** `poll_transactions` (v2.0)

#### Recognized Patterns

```regex
\bfetch\s+(new\s+)?transactions?\b
\bpoll\s+transactions?\b
\bget\s+(new\s+)?transactions?\b
\bcheck\s+(for\s+)?(new\s+)?transactions?\b
\bretrieve\s+transactions?\b
```

---

### 4. `show_summary` ✅

**Purpose:** Display reconciliation summary with match statistics

**Handler:** `CommandHandlers.show_summary()`

#### Recognized Patterns

```regex
\b(show|display|get)\s+(the\s+)?(summary|overview|stats|statistics)\b
\bsummar(y|ize)\b
\bhow\s+(are\s+)?(things|we)\s+doing\b
\bwhat'?s\s+the\s+status\b
```

---

### 5. `list_unmatched` ✅

**Purpose:** Show unmatched emails and transactions

**Handler:** `CommandHandlers.list_unmatched()`

#### Recognized Patterns

```regex
\b(show|list|display|get)\s+(all\s+)?(unmatched|pending|orphan)\b
\bwhat'?s\s+(not\s+)?matched\b
\bunmatched\s+(emails?|transactions?|items?)\b
```

---

### 6. `get_status` ✅

**Purpose:** Get unified automation service status

**Handler:** `CommandHandlers.get_status()`  
**Renamed from:** `get_automation_status` (v2.0)

#### Recognized Patterns

```regex
\b(get|show|check)\s+(automation\s+)?status\b
\b(is\s+)?(automation\s+)?running\b
\bwhat'?s\s+the\s+status\b
\bstatus\s+check\b
```

---

### 7. `start_automation` ✅

**Purpose:** Start unified automation service

**Handler:** `CommandHandlers.start_automation()`

#### Recognized Patterns

```regex
\bstart\s+(the\s+)?automation\b
\benable\s+automation\b
\bturn\s+on\s+automation\b
\bbegin\s+automated\s+(cycles?|processing)\b
```

---

### 8. `stop_automation` ✅

**Purpose:** Stop unified automation service

**Handler:** `CommandHandlers.stop_automation()`

#### Recognized Patterns

```regex
\bstop\s+(the\s+)?automation\b
\bdisable\s+automation\b
\bturn\s+off\s+automation\b
\bhalt\s+automated\s+(cycles?|processing)\b
```

---

### 9. `show_metrics` ⚠️

**Purpose:** Display performance metrics (stub implementation)

**Handler:** `CommandHandlers.show_metrics()`  
**Status:** Registered but returns placeholder data

#### Recognized Patterns

```regex
\b(show|display|get)\s+metrics\b
\bperformance\s+(data|stats)\b
\bhow\s+fast\b
```

---

### 10. `show_logs` ⚠️

**Purpose:** Show recent activity logs (stub implementation)

**Handler:** `CommandHandlers.show_logs()`  
**Status:** Registered but returns placeholder data

#### Recognized Patterns

```regex
\b(show|display|get|view)\s+(recent\s+)?(logs?|activity|history)\b
\bwhat\s+happened\b
```

---

### 11. `manual_match` ⚠️

**Purpose:** Manually match specific email/transaction (stub implementation)

**Handler:** `CommandHandlers.manual_match()`  
**Status:** Registered but returns placeholder data

#### Recognized Patterns

```regex
\bmanual(ly)?\s+match\b
\bmatch\s+(email|transaction|item)\s+\w+\b
\bforce\s+match\b
```

---

### 12. `help` ✅

**Purpose:** Show available commands and usage

**Handler:** Built-in to command interpreter

#### Recognized Patterns

```regex
\bhelp\b
\bcommands?\b
\bwhat\s+can\s+you\s+do\b
\bshow\s+help\b
```

---

## REST API Endpoints (11 Total)

In addition to A2A commands, BARA provides REST endpoints:

### Health (2 endpoints)

- `GET /` - Basic health check
- `GET /healthz` - Detailed health with environment

### A2A (1 endpoint)

- `POST /a2a/agent/{agent_name}` - JSON-RPC A2A interface

### Automation (4 endpoints)

- `GET /automation/status` - Get automation status
- `POST /automation/start` - Start automation service
- `POST /automation/stop` - Stop automation service
- `POST /automation/match` - Manually trigger matching

### Emails (2 endpoints)

- `POST /emails/fetch` - Manually fetch emails
- `GET /emails/metrics` - Get email fetcher metrics

### Transactions (2 endpoints)

- `POST /transactions/poll` - Manually poll transactions
- `GET /transactions/metrics` - Get transaction poller metrics

**Note:** Individual service control endpoints (`/emails/start`, `/emails/stop`, `/transactions/start`, `/transactions/stop`, `/emails/status`, `/transactions/status`) have been removed in BARA Core. Use unified `/automation/start`, `/automation/stop`, and `/automation/status` instead.

---

## Migration Guide (v2.0 → v3.0)

### Command Renames

| Old Command (v2.0)      | New Command (v3.0)       | Status |
| ----------------------- | ------------------------ | ------ |
| `reconcile_now`         | `match_now`              | ✅     |
| `fetch_emails`          | `fetch_emails_now`       | ✅     |
| `poll_transactions`     | `fetch_transactions_now` | ✅     |
| `get_automation_status` | `get_status`             | ✅     |

### Removed Commands (22 → 12)

**Workflow/Action System (7 commands removed):**

- `create_workflow`
- `run_workflow`
- `get_workflow_status`
- `execute_action`
- `get_action_audits`
- `get_action_statistics`
- `set_workflow_policy`

**Individual Service Control (4 commands removed):**

- `start_email_fetcher`
- `stop_email_fetcher`
- `start_transaction_poller`
- `stop_transaction_poller`

**Individual Status (2 commands removed):**

- `get_email_status`
- `get_transaction_status`

**Confidence Reporting (1 command removed):**

- `get_confidence_report`

**Replacement:** Use unified automation commands (`start_automation`, `stop_automation`, `get_status`) or REST endpoints (`/automation/*`).

---

## Command Interpreter Architecture

### Pattern Matching

Commands use compiled regex patterns for fast, deterministic matching:

```python
# Example pattern registration
interpreter.register_command(
    name="match_now",
    patterns=[
        r"\bmatch\s+(now|emails?|alerts?)\b",
        r"\brun\s+(the\s+)?reconciliation\b",
        r"\breconcile\b"
    ],
    handler=command_handlers.match_now,
    description="Run reconciliation matching"
)
```

### Confidence Scoring

- **Exact match**: 1.0 confidence (pattern matches perfectly)
- **Partial match**: 0.7-0.9 confidence (pattern matches with variations)
- **Fuzzy match**: 0.5-0.6 confidence (similar but not exact)
- **No match**: 0.0 confidence (no patterns matched)

---

## Testing

All commands have integration tests in `tests/test_a2a_natural_language.py` and `tests/test_a2a_jsonrpc.py`.

Run tests:

```powershell
.\.venv\Scripts\Activate.ps1
pytest tests/test_a2a_*.py -v
```

---

**End of Document**
