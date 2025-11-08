# Telex → BARA: End‑to‑End Operator Workflow (No Code)

## Overview

BARA (Bank Alert Reconciliation Agent) connects Telex to your reconciliation pipeline. Telex users trigger reconciliation actions (status, message/send, optional execute). BARA receives these as JSON‑RPC 2.0 requests, validates them, runs reconciliation (matching bank‑alert emails to transactions), and returns a structured report with per‑email artifacts and a batch summary for operators.

## What the Telex user experiences

- Discover/Enable the agent
  - The BARA workflow is registered in Telex and exposed as an agent (for example, "bankMatcher").
  - The agent’s description explains its capabilities (status check, reconcile unmatched emails, reconcile specific emails).
- Typical actions
  - Check health (status): Confirms the agent is reachable and shows environment info.
  - Reconcile recent unmatched emails (message/send with a limit): Processes a batch and returns a summary plus artifacts for each email matched or reviewed.
  - Reconcile specific alerts (message/send with email_ids): Targets known email IDs (e.g., escalations or rechecks).
  - Retry or re‑evaluate (rematch flag): Forces re‑evaluation of already matched emails if an operator needs a fresh decision.
- Results in Telex
  - A short status/summary text ("Reconciled X emails…").
  - A list of artifacts per email, including match status, confidence, best candidate details, and alternative candidates when relevant.
  - Meta data showing the parameters used and the batch totals.

## How a Telex request reaches BARA

- Telex sends a JSON‑RPC 2.0 request to BARA’s agent endpoint (POST /a2a/agent/BARA).
- BARA validates:
  - The envelope (version "2.0", required fields).
  - The method (status, message/send, execute).
  - Input parameters (e.g., limit, email_ids, rematch, summarize).
- BARA returns:
  - Always 200 OK at the HTTP layer, with JSON‑RPC result on success or error fields on failure.
  - Standard JSON‑RPC errors for malformed requests or unknown methods (−32600, −32601).
  - A 500‑style JSON‑RPC error object if reconciliation fails, with a human‑readable detail.

## Methods exposed to Telex

- status
  - Confirms the agent is healthy and configured.
  - Includes artifacts with metadata (agent name, configured agent in backend, environment).
- message/send (synchronous reconciliation)
  - Parameters:
    - limit: Number of unmatched emails to process (optional).
    - email_ids: Explicit email IDs to reconcile (optional).
    - rematch: True to re‑evaluate even if already matched (default false).
    - summarize: True to include a human‑friendly batch summary (default true).
  - Behavior:
    - If email_ids are supplied: processes exactly those emails (skips already matched unless rematch=true).
    - Else: pulls currently unmatched emails (respecting limit) for reconciliation.
  - Output:
    - summary: Short text (matched count, needs review, rejects, average confidence).
    - artifacts: One artifact per processed email with matching details (see Response semantics below).
    - meta: Batch totals and the request parameters echoed back for traceability.
- execute (async placeholder)
  - Accepts the request and returns a job artifact with a generated job_id.
  - Intended for future async orchestration; by default it does not enqueue a real background job yet.

## Backend processing pipeline

- Request validation
  - FastAPI validates and parses the JSON body into a typed request model.
  - If the jsonrpc version is not "2.0" or the body is malformed, a JSON‑RPC error is returned.
- Database session
  - An async SQLAlchemy session is injected per request.
  - The underlying DB can be Postgres (production) or SQLite (development/test).
- Email ingestion (background)
  - If IMAP is configured, a background fetcher pulls bank alert emails, stores them, and marks them unprocessed initially.
  - Parsing uses a hybrid approach (regex/LLM), then normalization/enrichment prepares the email for matching.
- Transaction ingestion (background)
  - A poller fetches transactions from connected sources/clients and writes them into the transactions table.
- Reconciliation (the core of message/send)
  - Selection: Unmatched emails are selected (or the specific IDs provided).
  - Normalization and enrichment:
    - Amounts, currency, timestamps normalized.
    - References tokenized and cleaned for fuzzy comparison.
    - Bank enrichment: a centralized mapping of Nigerian banks/fintechs/microfinance institutions detects the bank via sender domain, alias, or subject, attaching canonical bank code/name and confidence.
    - Composite keys: amounts + time bucket + reference tokens + account hints to pre‑filter candidates efficiently.
  - Candidate retrieval: Likely transactions are retrieved via repositories using heuristics (amount proximity, time window, reference overlap).
  - Scoring:
    - Multiple rules contribute scores (e.g., exact amount, fuzzy reference, timestamp proximity, account match, composite key).
    - Each rule has a weight; a total score is computed for each candidate.
  - Decision:
    - The best candidate’s score is compared to thresholds to assign a match status:
      - auto_matched (high confidence),
      - needs_review (medium confidence),
      - rejected (low confidence),
      - no_candidates (nothing plausible found).
  - Persistence:
    - A match row is written for each processed email (whether matched, reviewed, or rejected).
    - Transactions can be flagged verified if matched with high confidence.
    - Emails are marked processed to avoid duplicate work unless rematch=true.

## Response semantics (what operators see)

Each result includes:

- status: success or accepted (for async placeholder).
- summary: A single line summarizing the batch outcome (optional, but enabled by default).
- artifacts: A list of items; for reconciliation, each artifact contains:
  - kind: reconciliation_result.
  - data:
    - email_id, email_message_id.
    - matched (boolean), confidence (numeric), status (auto_matched, needs_review, rejected, no_candidates).
    - best_candidate: transaction_id, external_transaction_id, score, and a breakdown of rule_scores (rule, score, weight, weighted, details).
    - alternatives: other candidates with lower scores (with ranks).
    - notes: optional guidance or flags for the operator.
- meta:
  - batch: a machine‑friendly summary (counts, averages).
  - params: echo of the input parameters (limit, email_ids, rematch), aiding traceability.

## Operator workflows in Telex (practical playbook)

- Health check
  - Call status to confirm the agent is reachable and properly configured (agent name, environment).
- Reconcile newest alerts
  - Call message/send with a sensible limit (e.g., 20–50) to process recent unmatched emails.
  - Review the summary; scan artifacts for needs_review items to resolve.
- Reconcile targeted alerts
  - Provide specific email_ids to focus on known issues or escalations.
  - If a previous match looks wrong, set rematch=true to re‑evaluate and produce a fresh decision.
- Iterate
  - Re‑run with another limit batch as needed (pagination‑like behavior via repeated calls).
  - Use artifact details to triage and make manual decisions on needs_review cases.

## Error handling and idempotency

- Request validation
  - Malformed JSON‑RPC: returns error −32600.
  - Unknown method: returns error −32601.
  - Internal reconciliation errors: returns a 500‑style JSON‑RPC error with a human‑readable detail.
- Idempotency behaviors
  - Already‑matched emails are skipped in batch unmatched runs.
  - Targeted runs with email_ids do not rematch unless rematch=true.
  - The JSON‑RPC id can be used for tracking; future versions may add explicit idempotency keys.

## Data lifecycle and retention

- Emails and transactions are stored in normalized tables.
- Matches link emails to transactions with confidence and rule explanations.
- Retention policies (e.g., archiving older records) can be applied to meet operational/regulatory needs.

## Observability

- Structured logs: Key events (status checks, reconciliation starts, errors) are logged with context (request id, batch size).
- Metrics: Counts of processed, matched, review, rejected; average confidence; timing—useful for dashboards and alerting.

## Security and configuration

- Configuration‑driven: ENV, database URL, IMAP settings, thresholds/weights for matching, and agent name.
- Network/deployment: BARA runs behind your chosen ingress (public URL or gateway) with TLS where appropriate.
- Rate limiting/auth: May be applied at the API gateway or inside the app as required.

## In a nutshell

- Telex users interact with BARA by invoking status, message/send, and optionally execute.
- BARA validates and routes requests, then performs robust normalization, enrichment, candidate retrieval, scoring, and decisioning.
- Operators receive a clear batch summary and detailed, per‑email artifacts, enabling quick automated matches and focused human review.
- The system is modular and extensible—built to evolve with your bank mappings, data sources, and matching rules.
