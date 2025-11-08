# Bank Alert Reconciliation Agent (BARA)

A production‑oriented service that ingests bank alert emails, normalizes and enriches them, polls external transaction sources, and reconciles matches automatically via a configurable matching engine. It exposes a Telex‑compatible JSON‑RPC A2A endpoint and REST endpoints for worker management.

Status: Work‑in‑progress (Stages 1–7 complete, further stages planned). This README will evolve as new stages land.

## Table of contents

- Overview and goals
- Architecture at a glance
- What’s implemented so far (by stage)
- Project layout and folder guide
- Getting started (uv) — Windows PowerShell
- Configuration
- Database, migrations, and seed data
- Running the app
- Background workers (poller, email fetcher)
- Testing, linting, and formatting
- Docker
- Bank mappings maintenance
- Roadmap and next steps
- License

## Overview and goals

The Bank Alert Reconciliation Agent ingests transactional signals (bank alert emails and API‑polled transactions), transforms them into a canonical form, and reconciles them using an extensible rule‑based matching engine. Primary goals:

- High‑quality normalization and enrichment tailored to the Nigerian banking ecosystem
- Efficient reconciliation with transparent scoring and metrics
- Operational readiness (logging, health checks, metrics, CI hooks)
- Clear extension points for new sources, rules, and data models

## Architecture at a glance

- Ingestion
  - IMAP email fetcher → hybrid parser (rules + LLM + regex fallback)
  - Transaction poller → external API clients (mock in dev)
- Normalization & enrichment
  - Amount, currency, timestamp, reference tokenization
  - Bank enrichment using centralized mappings
- Matching engine
  - Candidate retrieval + 7 weighted rules + tie‑breaking
- Interfaces
  - JSON‑RPC A2A endpoint (Telex‑compatible)
  - REST endpoints for worker control and metrics
- Storage
  - Async SQLAlchemy, repositories, unit‑of‑work, Alembic migrations
- Ops
  - Structured logging, health endpoints, configurable via env

See docs/Overview.md and docs/architecture.md for deeper design notes.

## What’s implemented so far (by stage)

- Stage 1 — A2A API & infrastructure
  - JSON‑RPC 2.0 endpoint (status implemented; others return Not Implemented)
  - Health endpoints, structured logging, configuration loader
- Stage 2 — Storage models & persistence layer
  - 5 models (email, transaction, match, log, config), repositories, UoW
  - Alembic migrations and data retention utilities
- Stage 3 — Transaction poller
  - 15‑minute cadence (configurable), retries, circuit breaker, metrics
  - Mock API client with realistic Nigerian data
- Stage 4 — Email fetcher & intelligent parser
  - IMAP connector, rule‑based filter, LLM assist (Groq), regex fallback
  - Background fetcher with deduplication and metrics
- Stage 5 — Normalization & enrichment
  - Amount, currency, timestamp, reference normalization
  - Bank enrichment via centralized mappings
- Stage 6 — Matching engine
  - 7 weighted rules, fuzzy matching (rapidfuzz), composite keys, thresholds
- Stage 7 — A2A Integration & Telex Workflow
  - JSON‑RPC 2.0 endpoint with `status`, `message/send`, and `execute` methods
  - Synchronous reconciliation with rule-level scoring and batch summaries
  - Mock data refactoring (consolidated into single source of truth, 50% code reduction)
  - Enhanced mock data seeding with matching pairs strategy (70% match rate)
  - Configurable mock data via environment variables
  - Data clearing functionality with safety prompts

Refer to docs/Stage-1-Completion.md … docs/Stage-7-Completion.md for details.

## Project layout and folder guide

```
.
├─ app/
│  ├─ a2a/                # JSON‑RPC A2A endpoint
│  │  └─ router.py
│  ├─ core/               # Cross‑cutting infrastructure
│  │  ├─ config.py        # Pydantic settings loader
│  │  └─ logging.py       # structlog configuration & middleware
│  ├─ db/                 # Persistence layer
│  │  ├─ base.py          # Async SQLAlchemy engine/session
│  │  ├─ init.py          # DB init/reset CLI
│  │  ├─ repository.py    # Base repository
│  │  ├─ unit_of_work.py  # Transaction/UoW
│  │  ├─ retention.py     # Cleanup and retention policies
│  │  ├─ seed_mock.py     # Dynamic mock data seeding (dev/demo)
│  │  ├─ models/          # ORM models (email, transaction, match, log, config)
│  │  ├─ repositories/    # Specialized repositories
│  │  └─ migrations/      # Alembic env & versions
│  ├─ emails/             # Email ingestion & parsing
│  │  ├─ imap_connector.py
│  │  ├─ filter.py
│  │  ├─ llm_client.py
│  │  ├─ regex_extractor.py
│  │  ├─ parser.py
│  │  ├─ fetcher.py
│  │  ├─ metrics.py
│  │  └─ router.py        # REST endpoints
│  ├─ normalization/      # Canonicalization & enrichment
│  │  ├─ models.py
│  │  ├─ banks.py         # Central Nigerian bank/fintech mappings (aliases/domains)
│  │  └─ normalizer.py
│  ├─ matching/           # Matching engine
│  │  ├─ config.py
│  │  ├─ models.py
│  │  ├─ fuzzy.py
│  │  ├─ retrieval.py
│  │  ├─ rules.py
│  │  ├─ scorer.py
│  │  └─ engine.py
│  ├─ testing/            # Shared mock data templates
│  │  ├─ __init__.py
│  │  └─ mock_data_templates.py  # Single source of truth for mock data patterns
│  └─ transactions/       # Poller & API clients
│     ├─ clients/
│     │  ├─ base.py
│     │  └─ mock_client.py
│     ├─ config.py
│     ├─ metrics.py
│     ├─ poller.py
│     └─ router.py        # REST endpoints
├─ docker/
│  └─ Dockerfile          # Slim Python 3.13 image
├─ docs/                  # Architecture, stages, and roadmap
├─ tests/                 # Unit tests and fixtures
│  ├─ seed_fixtures.py    # Load static test data from fixtures
│  ├─ fixtures/           # Hardcoded test data (emails, transactions)
│  └─ test_*.py           # Test files
├─ main.py                # Entrypoint (delegates to app/main.py)
├─ app/main.py            # FastAPI app assembly & health
├─ pyproject.toml         # Project & dependency metadata
├─ run_server.bat         # Windows helper to start dev server
├─ run_checks.bat         # Windows helper for lint/test (if configured)
└─ alembic.ini            # Alembic config
```

Highlights:

- Centralized bank mappings live in `app/normalization/banks.py` (aliases + domains + categories)
- Mock data templates unified in `app/testing/mock_data_templates.py` (single source of truth)
- Two seeding options: `app/db/seed_mock.py` (dynamic, large, 70% match rate) and `tests/seed_fixtures.py` (static, small)
- Configurable mock data via `MOCK_EMAIL_COUNT` and `POLLER_BATCH_SIZE` environment variables
- Tests and documentation accompany each stage

## Getting started (uv) — Windows PowerShell

Prerequisites:

- Python 3.13+
- uv (package/dependency manager): https://docs.astral.sh/uv/
- A running database (PostgreSQL recommended for dev/prod; SQLite used in tests)

Install uv (if needed):

```powershell
# Scoop
scoop install uv
# or, pipx
pipx install uv
```

Create a virtual environment and install dependencies:

```powershell
uv venv
uv sync
```

Set up environment variables:

```powershell
# Copy and edit as needed (if .env.example is present)
Copy-Item .env.example .env
# Then open .env and fill values (see Configuration section below)
```

## Configuration

Configuration is managed by Pydantic Settings (`app/core/config.py`) and environment variables. Key variables (expand as needed):

- Core:
  - `ENV` (development|staging|production)
  - `DEBUG` (true|false)
  - `A2A_AGENT_NAME` (e.g., bankMatcher)
- Database:
  - `DATABASE_URL` (e.g., postgresql+asyncpg://user:pass@host:5432/db)
  - `TEST_DATABASE_URL` (e.g., sqlite+aiosqlite:///./test_bara_db.sqlite3)
- Email / IMAP:
  - `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS`
  - Optional behavior: poll intervals, batch sizes (see `app/emails/config.py`)
- LLM (optional):
  - `LLM_PROVIDER` (e.g., groq)
  - `GROQ_API_KEY`, `GROQ_MODEL`
- Transactions Poller (see `app/transactions/config.py`):
  - Poll interval, batch size, retries, circuit breaker thresholds
- Mock Data (development/testing):
  - `MOCK_EMAIL_COUNT` (default: 10, range: 1-100) — Number of mock emails to generate
  - `POLLER_BATCH_SIZE` (default: 100, range: 1-1000) — Number of mock transactions to generate

Defaults exist for many options; missing secrets should be provided via `.env`.

## Database, migrations, and seed data

Initialize and migrate the database:

```powershell
# Show current version
uv run alembic current
# Upgrade to latest
uv run alembic upgrade head
# Create a new migration (after model changes)
uv run alembic revision --autogenerate -m "your message"
```

Optional: seed data for development/testing:

```powershell
# Dynamic mock data (large volumes, guaranteed 70% match rate)
uv run python -m app.db.seed_mock 50 40 72

# Clear existing data first, then seed (prompts for confirmation)
uv run python -m app.db.seed_mock 100 80 48 true

# Static test fixtures (small dataset, for unit tests)
uv run python -m tests.seed_fixtures
```

Reset (dangerous in production):

```powershell
uv run python -m app.db.init reset
```

## Running the app

Start the FastAPI server (dev hot‑reload):

```powershell
# Helper script
./run_server.bat

# Or directly with uvicorn
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health checks:

- GET `/` → `{ "status": "ok" }`
- GET `/healthz` → `{ "status": "ok", "env": "development|staging|production" }`

A2A JSON‑RPC (Telex‑compatible):

- POST `/a2a/agent/BARA`
- POST `/a2a/agent/bankMatcher`

**Supported methods:**

- `status` — Health & configuration metadata
- `message/send` — Synchronous reconciliation with batch processing
  - Parameters: `limit`, `email_ids`, `rematch`, `summarize`
  - Returns: Detailed artifacts with rule-level scores and batch summaries
- `execute` — Async job submission (placeholder for future queue integration)

Example request:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "limit": 10,
    "summarize": true
  }
}
```

See `docs/Stage-7-Completion.md` and `docs/Telex-BARA-Workflow.md` for detailed specifications.

## Background workers (poller, email fetcher)

Transactions poller endpoints (`app/transactions/router.py`):

- GET `/transactions/poller/status`
- POST `/transactions/poller/start`
- POST `/transactions/poller/stop`
- POST `/transactions/poller/poll` (manual one‑off)

Email fetcher endpoints (`app/emails/router.py`):

- GET `/emails/fetcher/status`
- POST `/emails/fetcher/start`
- POST `/emails/fetcher/stop`
- POST `/emails/fetcher/fetch` (manual one‑off)

Both services collect in‑memory run metrics accessible via their status endpoints. Auto‑start can be configured via their respective configs.

## Testing, linting, and formatting

Run unit tests:

```powershell
uv run pytest -q
```

Formatting and linting (tools are declared in `pyproject.toml` dev group):

```powershell
# Format with Black
uv run black .
# Import sorting with isort
uv run isort .
# Lint with Flake8
uv run flake8 .
```

Optional type checking (mypy config present; install if desired):

```powershell
uv add --group dev mypy
uv run mypy .
```

## Docker

Build and run a container image:

```powershell
# Build
docker build -t bara:dev -f docker/Dockerfile .
# Run
docker run --rm -p 8000:8000 --env-file .env bara:dev
```

## Bank mappings maintenance

Bank/fintech/microfinance alias and domain mappings are centralized in:

- `app/normalization/banks.py` (export: `BANK_MAPPINGS`)

Guidelines:

- Use lowercase alias keys without punctuation (e.g., `gtb`, `gtbank`, `kuda`)
- Provide a concise `code`, canonical `name`, and known `domains`
- Tag `category` (commercial | non_interest | fintech | microfinance)
- Add common aliases and verified email/web domains

## Roadmap and next steps

This project is being implemented in stages. **Completed: 1–7** (A2A integration, matching engine, mock data infrastructure). Coming up:

- Stage 8: Pagination, advanced filtering, and query optimization
- Stage 9: Background job queue & async execution for `execute` method
- Authentication & rate limiting for agent endpoints
- Webhook callback delivery and push notifications
- Rule tuning and adaptive thresholds
- Prometheus metrics export and alerts
- Additional sources (webhooks, MMS/USSD, etc.)
- Broader bank and wallet coverage as needed

See docs/Roadmap.md for the high‑level plan and per‑stage docs for details.

## License

See `LICENSE` for licensing information.

---

Maintainers: contributions are welcome. Please open an issue to propose changes, or submit a PR following the coding conventions, with tests and documentation where appropriate.
