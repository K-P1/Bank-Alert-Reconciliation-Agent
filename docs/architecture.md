# Architecture Overview — Bank Alert Reconciliation Agent

## 1. A2A Communication Interface

### 1.1 Protocol
The agent follows the **Telex A2A (Agent-to-Agent)** communication standard based on **JSON-RPC 2.0**.

All Telex-compatible agents expose an HTTPS/HTTP endpoint:

```

POST /a2a/agent/bankMatcher
Content-Type: application/json

````

### 1.2 Request Format
Incoming Telex messages follow the JSON-RPC 2.0 structure:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "role": "user",
      "parts": [
        { "kind": "text", "text": "Run reconciliation now" }
      ]
    }
  }
}
````

**Meaning**

| Field                         | Description                                                 |
| ----------------------------- | ----------------------------------------------------------- |
| `id`                          | Unique request ID for traceability                          |
| `method`                      | Action requested by Telex (`message/send`, `execute`, etc.) |
| `params.message.parts[].text` | Free-form instruction or payload for the agent              |

### 1.3 Response Format

The agent always returns a JSON-RPC 2.0 object:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "status": "success",
    "summary": "5 alerts processed, 4 matched, 1 unmatched",
    "artifacts": [
      {
        "kind": "data",
        "data": {
          "matched": true,
          "confidence": 0.86,
          "alert_id": "eml_102",
          "transaction_id": "txn_5521",
          "amount": 23500,
          "currency": "NGN",
          "timestamp": "2025-11-04T10:15:00Z"
        }
      }
    ]
  }
}
```

**Response Components**

| Field        | Description                                                    |
| ------------ | -------------------------------------------------------------- |
| `summary`    | Human-readable run summary                                     |
| `artifacts`  | Structured machine-readable results Telex can forward or store |
| `confidence` | 0–1 similarity score between email alert and transaction       |
| `status`     | `success` / `error`                                            |

### 1.4 Supported Methods

| Method         | Purpose                                                       |
| -------------- | ------------------------------------------------------------- |
| `message/send` | On-demand reconciliation (triggered manually or via workflow) |
| `execute`      | Scheduled reconciliation (15-minute interval)                 |
| `status`       | Health / metrics check endpoint                               |

---

## 2. Internal Architecture and Data Flow

### 2.1 Overview

The agent has three main subsystems:

```
[ IMAP Inbox ]
      ↓
 [ Email Fetcher + Parser ]
      ↓
 [ Matching Engine ] ←→ [ Transactions Cache / DB ]
      ↓
 [ A2A Layer → Telex Response ]
```

### 2.2 Data Flow Steps

1. **Email Fetcher**

   * Connects to IMAP inbox.
   * Pulls new (unseen) messages.
   * Parses subject/body with `mailparser`.
   * Extracts structured fields:

     * `amount`, `currency`, `reference`, `sender`, `timestamp`.

2. **Transaction Poller**

   * Fetches recent transactions every 15 minutes from API or mock data.
   * Normalizes data into consistent fields:

     * `transaction_id`, `amount`, `timestamp`, `account_ref`, `description`.

3. **Matching Engine**

   * Compares each parsed email alert to transactions within a time window (±48 hours).
   * Uses deterministic and fuzzy rules:

     * `amount` equality,
     * `date` proximity,
     * `reference` similarity (`rapidfuzz` ratio).
   * Produces a confidence score and selects best match ≥ 0.8.

4. **Reconciliation Service**

   * Records matches and unmatched alerts in the database.
   * Returns structured summary and artifacts.

5. **A2A Layer**

   * Exposes FastAPI route `/a2a/agent/bankMatcher`.
   * Accepts Telex JSON-RPC requests.
   * Invokes reconciliation workflow.
   * Returns Telex-compatible JSON-RPC response.

---

## 3. Database Schema (Conceptual)

| Table            | Key Fields                                                                                                   | Purpose                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------- |
| **emails**       | `id`, `message_id`, `sender`, `subject`, `body`, `amount`, `currency`, `reference`, `timestamp`, `parsed_at` | Stores parsed email alerts                           |
| **transactions** | `id`, `transaction_id`, `amount`, `currency`, `timestamp`, `account_ref`, `description`, `source`            | Stores polled transactions                           |
| **matches**      | `id`, `email_id`, `transaction_id`, `confidence`, `matched_at`, `status`                                     | Links emails to transactions with a confidence score |
| **logs**         | `id`, `event`, `level`, `timestamp`, `details`                                                               | General-purpose logging/audit trail                  |

Foreign-key relationships:

* `matches.email_id → emails.id`
* `matches.transaction_id → transactions.id`

---

## 4. Data Lifecycle

| Stage                    | Source                    | Destination                      | Retention  |
| ------------------------ | ------------------------- | -------------------------------- | ---------- |
| Raw email                | IMAP                      | `emails` table                   | 30 days    |
| Parsed & normalized data | `emails` → `transactions` | Matching engine                  | Persistent |
| Match result             | Matching engine           | `matches` table + Telex artifact | Persistent |
| Logs & metrics           | System events             | `logs` table / stdout            | Rotated    |

---

## 5. Key Design Principles

* **Idempotency:** re-running reconciliation should not duplicate matches.
* **Transparency:** all matches store confidence and rule breakdowns.
* **Isolation:** A2A layer only orchestrates; domain logic lives in internal modules.
* **Extensibility:** later versions can swap rule-based matching for ML models.

---

## 6. Example End-to-End Flow

1. Telex workflow sends `message/send` → agent.
2. Agent fetches new unread emails.
3. Agent loads transactions from DB (already polled).
4. Matching engine compares and scores.
5. Results stored in DB and returned to Telex.
6. Telex logs structured artifacts or triggers next workflow step.

---
