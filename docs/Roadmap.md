# Roadmap: Build Bank Alert Reconciliation Agent (0–100)

## Stage 0 — Project Setup & Requirements (0–5%)

**Goal:**  
Lay the groundwork for development by defining what success looks like, setting up the environment, and organizing the project for smooth iteration.

---

### Tasks

1. **Define success criteria and testable goals**

   - Functional goals: achieve ≥ 80% match accuracy, complete each reconciliation run under a reasonable time (e.g., < 10 seconds for 100 emails).
   - Operational goals: ensure error rate is low, and system can recover gracefully from IMAP or API errors.

2. **Finalize technology stack**

   - Confirm programming language (Python), framework (FastAPI), and database (SQLite for local dev, PostgreSQL for production).
   - Decide how credentials will be managed (e.g., `.env` file locally, environment variables in production).

3. **Set up version control**

   - Initialize a Git repository.
   - Create `.gitignore`, `README.md`, and base folder structure using the setup script.
   - Establish a simple branching convention (`main` + `dev`).

4. **Prepare minimal CI/CD**

   - Optional: configure GitHub Actions or local test scripts to run linting and tests automatically.

5. **Document key interfaces**

   - Describe how the agent will communicate through A2A (JSON-RPC 2.0).
   - Outline expected database schema and major data flows in a short architecture note.

6. **Address basic security hygiene**
   - Use `.env` files for secrets (IMAP credentials, DB URL).
   - Note any data that should be treated as sensitive (e.g., email content, account info).

---

### Deliverables

- A clean Git repository with:
  - Initialized folder structure
  - README describing the project scope and goals
  - `.gitignore` and `.env.example`
- A short architecture document showing how components will interact.
- Optional: simple CI job for linting/tests.

---

### Validation / Checkpoint

- The repo builds cleanly, runs `uvicorn app.main:app` without errors.
- Architecture and goals are clearly documented in `docs/architecture.md`.
- You can describe in one sentence what the agent does and what “done” means for this project.

---

## Stage 1 — A2A API skeleton and infrastructure (5–12%)

**Goal:** Build the scaffolding: the JSON-RPC A2A endpoint and basic infrastructure wiring (no matching logic, minimal handlers only).

**Tasks**

1. Design JSON-RPC 2.0 endpoint contract (methods: `message/send`, `execute`, `status`).
2. Build skeleton service with health check, logging, config loader, and error handlers.
3. Create environment configuration for secrets (email creds, DB, API keys).
4. Add basic telemetry: request tracing IDs, structured logs.
5. Prepare deployment artifact (container definition) and local run scripts.

**Deliverables**

- Running service that responds to health checks and returns JSON-RPC error for unimplemented methods.
- Config docs with secure secret handling instructions.
- CI job that builds container and runs basic linter/static checks.

**Validation / Checkpoint**

- Endpoint responds to sample JSON-RPC requests with well-formed error/result objects.
- CI build passes basic checks.

---

## Stage 2 — Storage models and persistence layer (12–20%)

**Goal:** Define and implement the storage layer to persist polled transactions, parsed emails, and match results.

**Tasks**

1. Design DB schema: tables (transactions, emails, matches, logs, config).
2. Implement data access layer (DAL) with read/write and transactional guarantees.
3. Add migrations and seed data for development (sample transactions & email examples).
4. Implement retention and archival policy (how long raw emails are kept).
5. Secure DB access and encryption-at-rest config.

**Deliverables**

- DB schema and migration scripts.
- DAL interface and documentation.
- Sample dataset for testing.

**Validation / Checkpoint**

- Can persist and retrieve sample transactions and parsed-email records.
- Automated migration test passes in CI.

---

## Stage 3 — Transaction poller (20–30%)

**Goal:** Implement the component that fetches transactions on a 15-minute cadence and stores them.

**Tasks**

1. Design poller architecture: whether it runs inside the agent, as a separate worker, or via external scheduler (cron/Telex).
2. Implement API client(s) to fetch transactions and map external fields to internal schema.
3. Implement deduplication and idempotency (so repeated polls don’t duplicate data).
4. Implement retry/backoff and error handling for transient API failures.
5. Add metrics and logs for poll success, latency, and count of new transactions.

**Deliverables**

- Poller module that stores transactions in DB.
- Dashboard/metrics for poll runs.
- Test harness that simulates API responses (including edge cases).

**Validation / Checkpoint**

- Poller successfully runs and stores transactions for multiple runs.
- Deduplication test: re-running poll within same window does not produce duplicates.
- Poller metrics recorded.

---

## Stage 4 — Email Fetcher and Intelligent Parser (30–40%)

**Goal:**  
Build a hybrid email ingestion system that fetches new emails from IMAP and intelligently parses them into structured transaction records using a combination of **rule-based filters** and a **free LLM for semantic classification and extraction**.

---

### Tasks

1. **Set up mailbox access**

   - Use IMAP for secure, read-only access to the designated inbox.
   - Restrict credentials and permissions (use app password if Gmail).
   - Configure environment variables: `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS`.

2. **Implement the IMAP connector**

   - Connect to inbox and fetch only new/unread messages.
   - Retrieve subject, sender, and body (both plain text and HTML).
   - Store message ID and metadata to prevent duplicates.

3. **Build the hybrid parsing pipeline**
   **a. Pre-filtering (rule-based):**

   - Quickly exclude irrelevant messages using:
     - Sender domain whitelist (e.g., `@gtbank.com`, `@accessbankplc.com`).
     - Keyword-based subject filter (`ALERT`, `Credit`, `Debit`, `Transaction`).
     - Blacklist patterns (`Statement`, `Newsletter`, `Password`, `OTP`).
   - This reduces the load on the LLM by discarding obvious non-alerts.

   **b. LLM classification (semantic check):**

   - For messages that pass pre-filtering, call a free LLM (e.g., **Groq Llama 3 8B**) to decide if the email is a genuine transaction alert.
   - Prompt pattern:
     ```
     Determine if the following email is a transaction alert (e.g., credit or debit notification).
     Reply only with "YES" or "NO".
     Subject: {{subject}}
     Body: {{body}}
     ```
   - Only process further if the LLM responds with “YES.”

   **c. Extraction (LLM-assisted + regex fallback):**

   - For classified alerts, use the same or another LLM call to extract structured fields:
     - `amount`, `currency`, `transaction_type`, `sender_name`, `timestamp`, `reference_number`
   - Use a JSON-enforced prompt and validate output against schema.
   - If the LLM fails or returns partial data, fall back to regex-based extraction.

4. **Normalize and tag parsed data**

   - Clean up extracted values:
     - Convert currency symbols to ISO codes (₦ → NGN).
     - Convert amount strings (“₦23,500”) → float.
     - Parse timestamps into ISO format.
   - Tag each record with:
     - Parsing method (`regex`, `llm`, `hybrid`)
     - Confidence score (0–1)
     - Processing timestamp

5. **Handle multiple formats and encodings**

   - Account for both HTML and plain-text emails.
   - Handle Unicode and localized number formats (commas, periods, symbols).
   - Store the raw text in the `emails` table for reference and audit.

6. **Prevent duplication and track states**

   - Use `message_id` to ensure the same email isn’t processed twice.
   - Track message state: `unseen → processed → archived`.

7. **Error handling and observability**
   - Log parsing failures with error context.
   - Maintain metrics: total fetched, filtered, classified, extracted, success rate.
   - Provide a debug mode to print low-confidence cases for review.

---

### Deliverables

- **Email fetcher worker** capable of connecting to IMAP and ingesting emails.
- **Hybrid parser module** combining regex pre-filtering and LLM-assisted classification/extraction.
- **Parsed email dataset** (sample of at least 10–20 test alerts) stored in the `emails` table.
- **Telemetry report** showing success rate, confidence distribution, and classifier accuracy.

---

### Validation / Checkpoint

- The agent successfully fetches and processes new emails from IMAP.
- For a representative sample (10–20 real or mock alerts):
  - At least **90% of valid bank alerts** are correctly identified as such.
  - At least **80% of extracted fields** (amount, sender, reference, timestamp) are accurate.
- System logs show per-email confidence scores and low-confidence alerts are flagged.
- The LLM module can be toggled on/off via config (`USE_LLM=true|false`).

---

### Notes

- This stage creates the “perception” layer of the agent — the part that understands the world.
- The hybrid (regex + LLM) approach keeps costs at zero while dramatically improving precision and recall.
- The LLM should only handle short texts and limited volume to stay within free-tier limits.
- The design remains modular: if an LLM isn’t available, the regex-only pipeline still works with reduced accuracy.

---

## Stage 5 — Data normalization and enrichment (40–48%)

**Goal:** Normalize parsed fields and enrich data to maximize matching accuracy.

**Tasks**

1. Normalize amounts and currencies into canonical formats (number, ISO currency code).
2. Normalize dates into consistent timezone and ISO format.
3. Clean reference strings (strip punctuation, normalize whitespace, extract tokens).
4. Enrich emails and transactions where possible:
   - Map common sender names to known banks or channels.
   - Extract probable customer identifiers from descriptions.
5. Create canonical composite keys that will be used by the matcher (e.g., `amount + date_window + last4_account + cleaned_reference_tokens`).

**Deliverables**

- Normalization module and documentation.
- Enriched datasets for transactions and emails.
- Test cases covering normalization edge cases.

**Validation / Checkpoint**

- Normalization test suite passes (amounts, dates, references are normalized consistently).
- Enrichment increases matchability in a test dataset (confirm via shadow matching).

---

## Stage 6 — Matching engine (48–64%)

**Goal:** Implement the core matching logic using deterministic and fuzzy rules to reach target accuracy.

**Tasks**

1. Design matching strategy:
   - Exact-match rules (amount + exact reference/token + timestamp window).
   - Heuristic rules (amount + last4 account + fuzzy reference).
   - Fallback rules (amount + date proximity).
   - Scoring model that combines signals into a confidence score (0–1).
2. Select tooling for fuzzy matching (e.g., `rapidfuzz` or similar).
3. Implement time-window logic (e.g., only compare transactions within ±48 hours, configurable).
4. Implement candidate retrieval (efficiently find potential matches from DB).
5. Implement scoring and thresholding (e.g., confidence ≥ 0.8 considered a match).
6. Add facilities to mark multiple possible matches and choose best candidate or escalate.
7. Implement deterministic tie-breaking rules (most recent, highest reference similarity, etc.).
8. Add unit tests for individual rule behavior and integration tests combining rules.

**Deliverables**

- Matching engine with configurable rules and thresholds.
- Matching logs with score breakdown per candidate.
- Benchmarks of accuracy using validation dataset.

**Validation / Checkpoint**

- On a labelled validation set, matching engine achieves ≥ 80% accuracy.
- For edge cases, engine outputs candidate list and confidence breakdowns.

---

## Stage 6.5 — Regex-Based Command Interpreter (Natural Command Routing) (64–68%)

**Goal:**
Enable the A2A agent to accept **plain, natural-sounding commands** from Telex (e.g., "Run reconciliation now", "Show unmatched alerts", "Give me confidence stats") without any LLM dependency.
This stage introduces a lightweight, deterministic command-interpreter layer that uses regex and pattern matching to map user messages to specific backend actions.

---

### **Tasks**

1. **Define command registry**

   - Create a fixed mapping of commands to backend functions:

     - `reconcile_now` → trigger full reconciliation immediately
     - `show_summary` → display summary of matched/unmatched results
     - `list_unmatched` → list unpaired or pending alerts
     - `get_confidence_report` → return accuracy and confidence metrics
     - `help` → list all available commands and their usage

   - Store command metadata:

     - regex patterns for detection
     - command description
     - handler reference
     - optional parameter extraction logic (e.g., date range, ID)

2. **Implement regex-based interpreter**

   - Build `command_interpreter.py` that:

     - Scans incoming user text with defined regex patterns.
     - Matches to the appropriate command and extracts any parameters.
     - Falls back to the `help` command when no match is found.

   - Example:

     ```python
     COMMANDS = {
         "reconcile_now": {
             "patterns": [r"\breconcile\b", r"\brun( the)? reconciliation\b"],
             "handler": run_reconciliation
         },
         ...
     }
     ```

3. **Integrate with A2A endpoint**

   - Extend `/a2a/agent/bankMatcher` to:

     - Detect if incoming message is free text.
     - Pass message through the command interpreter.
     - Invoke the mapped handler or return the help message if unrecognized.

   - Maintain compatibility with structured JSON-RPC requests.

4. **Add "help" response**

   - If the message doesn't match any command:

     - Return a structured and user-friendly help response listing all available commands, examples, and explanations.
     - Example:

       ```
       Available Commands:
       - reconcile now → Run reconciliation immediately.
       - show summary → Display matched/unmatched overview.
       - list unmatched → List unpaired alerts.
       - get confidence report → Show accuracy metrics.
       - help → Show this list.
       ```

   - Include command usage notes and common examples.

5. **Testing & validation**

   - Create 3–5 test phrases per command (e.g., "run reconciliation", "get report", "show pending").
   - Validate correct handler invocation and parameter parsing.
   - Confirm fallback to help message on unknown commands.

---

### **Deliverables**

- `command_interpreter.py` module implementing regex-based routing.
- Updated A2A endpoint supporting both structured and free-text commands.
- Automated tests covering all command variations.
- Sample help output documenting available commands and examples.

---

### **Validation / Checkpoint**

- Agent correctly recognizes ≥ 95% of valid command phrases.
- Unknown messages trigger a detailed help response with available commands.
- End-to-end test confirms that "reconcile now" and equivalent phrasing produce identical results to structured JSON requests.
- Zero dependency on LLMs or external APIs; response latency < 100 ms.

---

### **Notes**

- This design prioritizes speed, cost-efficiency, and predictability over semantic flexibility.
- New commands can be added easily by registering new regex patterns and handlers.
- The "help" output doubles as the agent's interactive documentation for Telex users.
- This lightweight interpreter closes the natural-input gap without introducing external dependencies or inference costs.

---

## Stage 7 — Reconciliation workflow & A2A integration (68–74%)

**Goal:** Hook the matching engine into the A2A agent flow so Telex can invoke reconciliation and receive structured results.

**Tasks**

1. Define A2A task payload results: include matched flag, confidence, matched transaction id, match details, unmatched reasons.
2. Implement synchronous `message/send` path for on-demand checks and asynchronous `execute` path for longer runs (if needed).
3. Return artifacts (structured data), plus human-readable summary text.
4. Support pagination and bulk results for runs that process many emails.
5. Implement webhooks or push-notifications (optional) for long-running reconciliation jobs.
6. Add error handling, and ensure idempotent behavior for re-runs.

**Deliverables**

- A2A endpoint that runs reconciliation and returns JSON-RPC results for processed emails.
- Example A2A call/response documentation for Telex integration.

**Validation / Checkpoint**

- Telex (or local A2A test client) can successfully call the endpoint and receive structured reconciliation results.
- End-to-end test: new email → poller + fetcher → match → A2A response contains expected match.

---

## Stage 8 — Post-processing actions & integrations (74–82%)

**Goal:** Implement downstream automation: marking transactions as verified, notifying systems or teams, and creating tickets for ambiguous matches.

**Tasks**

1. Define actions for matched vs unmatched vs ambiguous alerts:
   - Matched: mark transaction as verified, update ledger, notify CRM.
   - Ambiguous (multiple candidates or low confidence): open a review ticket or notify operations.
   - Unmatched: flag as unmatched and optionally forward to operations inbox.
2. Implement connectors to downstream systems (webhooks, database updates, or API calls).
3. Implement retry and transactional guarantees for downstream actions.
4. Add audit trail for every action taken with timestamps and actor (agent/system).

**Deliverables**

- Connector modules for at least one downstream target (e.g., update transaction status in DB and send a notification).
- Audit logs for reconciliation actions.
- Workflow policy document for human-in-the-loop escalation.

**Validation / Checkpoint**

- End-to-end scenario where matched alert updates transaction status and a notification is generated.
- Ambiguous case results in ticket creation and is visible in operations dashboard.

---

## Stage 9 — Testing, tuning, and accuracy improvement (82–90%)

**Goal:** Thorough testing, edge-case handling, and tuning to meet and stabilize the 80% accuracy goal.

**Tasks**

1. Build a rich labelled test set: a mix of positive matches, near-misses, and negative cases.
2. Run cross-validation and error analysis to identify common failure modes (e.g., mis-parsed amounts, timezone mismatches).
3. Tune matching thresholds, scoring weights, and time windows based on analysis.
4. Implement a small ML or heuristic improvement if necessary (e.g., token-level similarity weighting, embedding-based similarity).
5. Implement A/B tests if considering multiple matching strategies.
6. Add end-to-end regression tests to CI with expected accuracy metrics.

**Deliverables**

- Test suite with clear pass/fail criteria and examples of failure cases.
- Report summarizing tuning iterations and final configuration.
- CI job that runs regression tests and asserts minimum accuracy.

**Validation / Checkpoint**

- Regression tests pass and show ≥ 80% accuracy on held-out dataset.
- Failure cases are documented with remediation plans.

---

## Stage 10 — Observability, security, and operational readiness (90–96%)

**Goal:** Harden operational aspects for production: monitoring, alerting, secrets management, and access controls.

**Tasks**

1. Implement monitoring dashboards (request rates, error rates, matches per run, parsing failures).
2. Add alerting rules (e.g., daily match rate drops below threshold, email fetch failures).
3. Secure secrets with a secrets manager and rotate credentials where possible.
4. Implement RBAC for access to logs and operation dashboards.
5. Ensure PII handling rules and data retention enforcement.
6. Create runbooks for common incidents and escalation paths.

**Deliverables**

- Monitoring dashboards and alerting configured.
- Runbooks and security checklist completed.
- Penetration checklist for handling sensitive data.

**Validation / Checkpoint**

- Alerts trigger on simulated failures.
- Security review passed (or checklist completed).

---

## Stage 11 — Deployment & scale testing (96–99%)

**Goal:** Deploy to production-like environment and perform load and resilience testing.

**Tasks**

1. Deploy agent and worker services to staging and production environments.
2. Perform scale tests: simulate email surge and transaction volumes; measure latency and throughput.
3. Test failover behavior: slow bank API, IMAP server downtime, DB unavailability.
4. Run chaos tests that simulate random failures to ensure graceful degradation.
5. Validate backup, restore, and recovery procedures.

**Deliverables**

- Production deployment with versioning and rollback plans.
- Load/performance test reports and capacity plan.

**Validation / Checkpoint**

- Service meets latency and throughput requirements under expected load.
- Failover tests succeed (no silent data loss, proper retry & alerting).

---

## Stage 12 — Release & post-release improvements (99–100%)

**Goal:** Release to production and run iterative improvements based on real data.

**Tasks**

1. Soft launch (limited scope or percentage of emails) to validate behavior with real traffic.
2. Collect production metrics on accuracy, false positives/negatives, and operational errors.
3. Iterate on tuning, parsing rules, and enrichment based on production feedback.
4. Add ML-backed components if needed (e.g., classification of ambiguous alerts).
5. Document lessons learned and update runbooks.

**Deliverables**

- Production release notes and post-launch monitoring dashboard.
- Plan for periodic model/rule retraining (if applicable).

**Validation / Checkpoint**

- After 2–4 weeks of production data, accuracy stabilizes at or above 80%.
- Stakeholders confirm that automation reduces manual reconciliation workload.

---
