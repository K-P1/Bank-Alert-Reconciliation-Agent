# Bank Alert Reconciliation Agent (Telex A2A Agent)

## Overview
The **Bank Alert Reconciliation Agent** is an autonomous backend service that retrieves bank alert emails from a designated mailbox, extracts structured transaction information, and matches those alerts to transactions previously fetched from an external banking or payment API. The goal is to automate the reconciliation process — confirming which bank alerts correspond to valid transactions in the system — and reduce the need for manual verification.

This agent will operate as a **Telex-compatible A2A agent**, exposing a JSON-RPC 2.0 compliant endpoint that can be called by Telex workflows. It will process incoming messages or scheduled triggers to perform reconciliation, returning structured results and confidence scores for matched transactions.

---

## Purpose
Manual reconciliation of bank alerts and transaction logs is time-consuming and error-prone. This agent aims to:
- Automate matching between bank alert emails and internal transaction records.
- Achieve a minimum 80% match accuracy through rule-based and fuzzy comparison.
- Integrate seamlessly into Telex workflows for continuous and autonomous operation.

---

## Objectives
1. **Fetch Bank Alerts:** Retrieve recent unread emails from an IMAP inbox (e.g., `alerts@company.com`).
2. **Parse Email Content:** Extract key data such as amount, sender, transaction reference, and date.
3. **Poll Transactions:** Fetch or read transaction data previously pulled from an external source (API or database).
4. **Perform Matching:** Compare parsed alerts with stored transactions using heuristic and fuzzy matching.
5. **Generate Reconciliation Results:** Return structured matches and confidence scores in JSON-RPC 2.0 format.
6. **Integrate with Telex:** Enable the agent to be triggered via Telex workflows for periodic checks or on-demand reconciliation.

---

## Expected Functionality
- **Input:** A Telex-triggered A2A request to perform reconciliation or fetch results.
- **Process:**
  - Connect to an IMAP inbox and retrieve new emails.
  - Parse each email to extract transaction data.
  - Match parsed alerts against stored transactions within a time window.
  - Generate a confidence score for each potential match.
- **Output:** JSON-RPC response containing:
  - Number of matched and unmatched alerts.
  - Confidence metrics.
  - List of matched transactions with metadata.
- **Accuracy Goal:** ≥ 80% for correctly identified matches.

---

## System Architecture (High-Level)
1. **Email Fetcher:** Connects to IMAP server, retrieves and parses new emails into structured objects.
2. **Transaction Poller:** Runs periodically to fetch transactions and cache them in a local database.
3. **Matching Engine:** Compares parsed alerts against recent transactions using deterministic and fuzzy rules.
4. **Storage Layer:** Persists parsed emails, transactions, and reconciliation results (e.g., in PostgreSQL or Redis).
5. **A2A API Layer:** Exposes a `/a2a/agent/bankMatcher` endpoint following the JSON-RPC 2.0 and Telex A2A specifications.
6. **Telex Integration:** Telex workflows can trigger the agent at intervals (e.g., every 15 minutes) or on-demand.

---

## Technology Stack
| Component | Technology | Purpose |
|------------|-------------|----------|
| **Core Framework** | FastAPI | Lightweight async web framework for A2A API |
| **Language** | Python 3.13+ | Main implementation language |
| **Data Validation** | Pydantic | JSON schema validation and A2A model definitions |
| **Email Handling** | IMAPClient / mailparser | Fetch and parse bank alert emails |
| **Fuzzy Matching** | RapidFuzz | Compare alert and transaction data with similarity scoring |
| **Database** | PostgreSQL or SQLite | Store transactions, parsed alerts, and matches |
| **Scheduling** | Telex Workflow / Cron | Automate periodic reconciliation |
| **Logging** | PinoLogger or Python logging | Monitoring and observability |
| **Protocol Compliance** | JSON-RPC 2.0 (A2A) | Communication layer for Telex integration |

---

## Planned Development Stages
1. **Stage 1:** Design A2A-compliant FastAPI service with health check and placeholder endpoint.
2. **Stage 2:** Implement IMAP email fetcher and parser.
3. **Stage 3:** Build transaction polling module and local storage model.
4. **Stage 4:** Implement matching logic with heuristic and fuzzy comparison.
5. **Stage 5:** Integrate all components into the A2A endpoint for Telex.
6. **Stage 6:** Test and tune accuracy, confidence scoring, and error handling.
7. **Stage 7:** Deploy and connect the agent to a Telex workflow for live testing.

---

## Expected Outcome
At the end of implementation:
- The agent will autonomously reconcile bank alert emails with internal transactions.
- It will operate via Telex as a background worker or callable A2A node.
- It will produce reliable, structured reconciliation results with a target accuracy of 80%.
- It will reduce manual verification workload and improve financial data integrity.
