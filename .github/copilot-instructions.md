# Copilot Instructions for Bank Alert Reconciliation Agent (BARA)

## ⚠️ CRITICAL: Virtual Environment Management

**ALWAYS activate virtual environment before running ANY code or tests:**

```powershell
# Check for .venv directory first
if (Test-Path .venv) {
    .\.venv\Scripts\Activate.ps1
} elseif (Test-Path venv) {
    .\venv\Scripts\Activate.ps1
}

# Verify activation (prompt should show (.venv) or (venv))
# Then run your commands
```

**Universal rule for ALL projects:**

- Never run Python commands without checking for and activating a virtual environment
- Always look for `.venv`, `venv`, or `.virtualenv` directories
- Use `uv run` commands which auto-activate the venv, OR manually activate first
- This prevents dependency conflicts and ensures correct package versions

**This project uses `.venv` managed by `uv`:**

- Created with: `uv venv`
- Installed with: `uv sync`
- Activate before: pytest, alembic, python scripts, any manual python commands

## Project Overview

BARA is a production-grade reconciliation service for Nigerian banking that ingests bank alert emails via IMAP, polls transaction APIs, normalizes/enriches both, and matches them using a rule-based engine. It exposes a Telex-compatible JSON-RPC A2A endpoint and REST APIs for worker management.

**Key architectural decisions:**

- **Async-first**: All I/O is async (SQLAlchemy async, aiofiles, async HTTP clients)
- **Repository + UnitOfWork pattern**: Database operations go through repositories accessed via `UnitOfWork` context manager
- **Centralized bank mappings**: `app/normalization/banks.py` contains Nigerian bank/fintech aliases and domains (118+ entries)
- **Hybrid parsing**: Email parsing uses rules → LLM (Groq) → regex fallback for resilience
- **Mock data generators share templates**: `app/testing/mock_data_templates.py` ensures mock emails and transactions match for testing

## Critical Architectural Patterns

### 1. Database Layer (Repository + UnitOfWork)

**Always use UnitOfWork for database operations:**

```python
from app.db.unit_of_work import UnitOfWork

async with UnitOfWork() as uow:
    email = await uow.emails.get_by_message_id(msg_id)
    transaction = await uow.transactions.create(...)
    await uow.commit()  # Explicit commit when needed
```

**Repository filter operators** (critical for queries):

- Double underscore syntax: `field__lt`, `field__gt`, `field__gte`, `field__lte`, `field__ne`
- Example: `await uow.transactions.filter(amount__gt=1000, status="pending")`
- `delete_all()` method: Deletes all records (use with caution), supports filters

**Where repositories live:**

- Base: `app/db/repository.py` (BaseRepository with CRUD + filter operators)
- Specialized: `app/db/repositories/{email,transaction,match,log,config}_repository.py`

### 2. Configuration System

**Pydantic Settings with environment precedence:**

```python
from app.core.config import get_settings

settings = get_settings()  # Cached singleton
# Access: settings.ENV, settings.DATABASE_URL, settings.IMAP_HOST, etc.
```

**Development patterns:**

- Check `settings.ENV == "development"` for dev-only features
- Mock data fallback: Auto-serve mock data when real sources unavailable in dev (see `app/transactions/router.py` and `app/emails/router.py`)
- Configuration files: `app/core/config.py` (global), `app/emails/config.py`, `app/transactions/config.py`, `app/matching/config.py`

### 3. Mock Data Generation (Critical for Testing)

**Shared templates ensure email/transaction matching:**

```python
from app.testing.mock_data_templates import (
    TRANSACTION_TEMPLATES,  # 6 transaction patterns
    NIGERIAN_BANKS,         # 8 banks
    BANK_DETAILS,           # Email configs per bank
    generate_transaction_description,
    generate_realistic_amount,
)
```

**Where generators are used:**

- `app/transactions/clients/mock_client.py`: MockTransactionClient
- `app/emails/mock_email_generator.py`: MockEmailGenerator
- `app/db/seed_mock.py`: Dynamic mock data seeding (for dev/demo)
- `tests/seed_fixtures.py`: Static test fixtures seeding (for unit tests)

**Mock data seeding (dynamic, large volumes):**

```powershell
# Activate venv first!
.\.venv\Scripts\Activate.ps1

# Add 50 transactions, 40 emails over 72 hours
python -m app.db.seed_mock 50 40 72
# or: uv run python -m app.db.seed_mock 50 40 72

# Clear existing data first (prompts for confirmation)
python -m app.db.seed_mock 100 80 48 true
# or: uv run python -m app.db.seed_mock 100 80 48 true
```

**Test fixtures seeding (static, small dataset):**

```powershell
# For unit tests and debugging
python -m tests.seed_fixtures
# or: uv run python -m tests.seed_fixtures
```

### 4. Bank Enrichment System

**Central source of truth: `app/normalization/banks.py`**

- Contains `BANK_MAPPINGS` dict with 118+ Nigerian banks/fintechs
- Structure: `{alias: {code, name, domains, category}}`
- Categories: `commercial | non_interest | fintech | microfinance | holding | dfi`
- Used by: Email whitelist filter, transaction normalizer, matching engine

**When adding new banks:**

1. Update `BANK_MAPPINGS` in `app/normalization/banks.py`
2. Use lowercase alias keys without spaces (e.g., "gtb", "moniepoint", "kuda")
3. Add all known domains for email filtering
4. Email whitelist auto-rebuilds from this source

### 5. Matching Engine Architecture

**Orchestration flow (see `app/matching/engine.py`):**

```
Email → Normalize → Retrieve Candidates → Score (7 rules) → Rank → Store Match
```

**7 weighted matching rules** (see `app/matching/rules.py`):

1. Exact amount match (weight: 0.30)
2. Exact reference match (weight: 0.25)
3. Fuzzy reference similarity (weight: 0.15, uses rapidfuzz)
4. Timestamp proximity (weight: 0.15, ±72 hours window)
5. Fuzzy description similarity (weight: 0.10)
6. Same currency (weight: 0.03)
7. Same bank enrichment (weight: 0.02)

**Retrieval strategy** (see `app/matching/retrieval.py`):

- Primary: Composite key (amount + currency + date)
- Fallback: Amount range ±5% within ±72 hours
- Both return unmatched transactions only

### 6. A2A JSON-RPC Protocol (Telex-Compatible)

**Endpoint pattern:** `POST /a2a/agent/{agent_name}`

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": { "message": { "kind": "message", "parts": [{ "text": "..." }] } }
}
```

**Supported methods:**

- `status`: Health check with metrics
- `message/send`: Synchronous reconciliation run
- Future: `execute` for async job submission

**Implementation:** `app/a2a/router.py` (297 lines, includes artifact formatting)

## Development Workflows

### Database Migrations

```powershell
# ALWAYS activate venv first or use `uv run`
.\.venv\Scripts\Activate.ps1

# Check current version
alembic current
# or: uv run alembic current

# Upgrade to latest
alembic upgrade head
# or: uv run alembic upgrade head

# Create migration after model changes
alembic revision --autogenerate -m "description"
# or: uv run alembic revision --autogenerate -m "description"

# Downgrade one version
alembic downgrade -1
# or: uv run alembic downgrade -1
```

### Running the Server

```powershell
# Activate venv first
.\.venv\Scripts\Activate.ps1

# Dev server with hot reload
./run_server.bat
# or: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# or: uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing

```powershell
# ALWAYS activate venv first or use `uv run`
.\.venv\Scripts\Activate.ps1

# Run all tests
pytest -q
# or: uv run pytest -q

# Run specific test file
pytest tests/test_matching.py -v
# or: uv run pytest tests/test_matching.py -v

# Test with coverage
pytest --cov=app tests/
# or: uv run pytest --cov=app tests/
```

### Formatting & Linting

```powershell
# Activate venv first
.\.venv\Scripts\Activate.ps1

# Format code (Black + isort)
black .
isort .
# or: uv run black . ; uv run isort .

# Lint (Flake8)
flake8 .
# or: uv run flake8 .
```

## Project-Specific Conventions

### Async Patterns

**Always use async/await for I/O:**

- Database queries: `await uow.emails.get_by_id(...)`
- HTTP clients: `await client.fetch_transactions(...)`
- File operations: Use `aiofiles` for async file I/O
- Background workers: Poller and fetcher use `asyncio.create_task()`

**Session management:**

- UnitOfWork auto-commits on successful exit
- Use `async with UnitOfWork() as uow:` for atomic operations
- Repositories are accessed via UnitOfWork properties: `uow.emails`, `uow.transactions`, etc.

### Logging

**Structured logging with structlog:**

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("event.name", field1=value1, field2=value2)
logger.error("error.type", error=str(exc), context=extra_data)
```

**Log naming convention:** `{component}.{action}.{status}`

- Examples: `a2a.request.received`, `poller.fetch.success`, `matching.candidate.found`

### Error Handling

**API resilience patterns (see `app/transactions/retry.py`):**

- Retry with exponential backoff: `RetryPolicy(max_attempts=3, base_delay=1.0)`
- Circuit breaker: `CircuitBreaker(failure_threshold=5, timeout=60.0)`
- Both used in transaction poller for external API calls

### Environment-Aware Behavior

**Development mode features:**

- Smart mock fallback: Serves mock data when IMAP/APIs not configured
- Clear warnings: `⚠️ MOCK DATA` in logs and responses
- Production protection: Raises 503 errors if misconfigured in production
- See: `app/transactions/router.py` (line 56), `app/emails/router.py` (line 50)

## Common Tasks & Examples

### Adding a New Transaction Source

1. Create client in `app/transactions/clients/new_client.py`
2. Inherit from `BaseTransactionClient` (see `app/transactions/clients/base.py`)
3. Implement: `fetch_transactions()`, `validate_credentials()`, `get_source_name()`
4. Update factory in poller to instantiate your client
5. Add configuration to `app/transactions/config.py`

### Adding a New Matching Rule

1. Add rule function to `app/matching/rules.py`
2. Signature: `def rule_name(email: NormalizedEmail, txn: NormalizedTransaction) -> float`
3. Return: 0.0 to 1.0 score
4. Add to `MatchingConfig.RULES` with weight in `app/matching/config.py`
5. Update `app/matching/scorer.py` to call your rule

### Extending Bank Mappings

**Single place to update: `app/normalization/banks.py`**

```python
"moniepoint": {
    "code": "MONIE",
    "name": "Moniepoint MFB",
    "domains": ["moniepoint.com", "teamapt.com"],
    "category": "microfinance"
}
```

Email whitelist auto-updates, no other changes needed.

### Creating Test Fixtures

**Mock data patterns (see `tests/fixtures/`):**

- Email fixtures: `tests/fixtures/sample_emails.py`
- Transaction fixtures: `tests/fixtures/sample_transactions.py`
- Use pytest fixtures from `tests/conftest.py` for database setup

## File Organization by Feature

**Email ingestion:** `app/emails/` (7 files)

- `imap_connector.py`: IMAP connection & message fetching
- `filter.py`: Rule-based filtering (sender whitelist, subject patterns)
- `parser.py`: Orchestrates hybrid parsing (rules → LLM → regex)
- `llm_client.py`: Groq API integration for LLM parsing
- `regex_extractor.py`: Fallback regex patterns
- `fetcher.py`: Background email fetching service
- `router.py`: REST endpoints for email operations

**Transaction polling:** `app/transactions/` (7 files)

- `clients/base.py`: Abstract client interface
- `clients/mock_client.py`: Mock data generator for dev
- `poller.py`: Background polling service with resilience
- `retry.py`: RetryPolicy + CircuitBreaker utilities
- `router.py`: REST endpoints for poller control

**Matching engine:** `app/matching/` (7 files)

- `engine.py`: Main orchestration (retrieve → score → rank → store)
- `retrieval.py`: Candidate retrieval strategies
- `rules.py`: 7 matching rules (exact, fuzzy, temporal)
- `scorer.py`: Rule execution and aggregation
- `fuzzy.py`: Fuzzy matching utilities (rapidfuzz wrappers)

**Database:** `app/db/` (11+ files)

- Models: `models/{email,transaction,match,log,config}.py`
- Repositories: `repositories/{email,transaction,match,log,config}_repository.py`
- Migrations: `migrations/versions/` (Alembic)

**Testing utilities:** `app/testing/` (NEW)

- `mock_data_templates.py`: Shared templates for consistent mock generation

## Key Dependencies & Their Usage

- **FastAPI**: Web framework (`app/main.py` assembles routers)
- **SQLAlchemy 2.0**: Async ORM with declarative models
- **Alembic**: Database migrations
- **Pydantic**: Data validation & settings management
- **structlog**: Structured logging throughout
- **rapidfuzz**: Fuzzy string matching (Levenshtein, token_sort_ratio)
- **asyncpg**: PostgreSQL async driver (production)
- **aiosqlite**: SQLite async driver (tests)
- **uvicorn**: ASGI server

## Integration Points

### External Services

1. **IMAP Email Server**: `app/emails/imap_connector.py`

   - Configured via `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS`
   - Falls back to mock emails in dev if not configured

2. **Transaction API**: `app/transactions/clients/`

   - Mock client used in dev (`mock_client.py`)
   - Real clients inherit from `BaseTransactionClient`

3. **LLM (Groq)**: `app/emails/llm_client.py`
   - Optional: Falls back to regex if unavailable
   - Configured via `GROQ_API_KEY`, `GROQ_MODEL`

### Internal Service Communication

- **Poller → Database**: Stores raw transactions via UnitOfWork
- **Fetcher → Parser → Database**: Stores parsed emails
- **A2A Endpoint → Matching Engine**: Triggers reconciliation on demand
- **Matching Engine → Repositories**: Reads emails/transactions, writes matches

## Health & Monitoring

**Health endpoints:**

- `GET /` → Basic health check
- `GET /healthz` → Detailed status with environment
- `GET /transactions/poller/status` → Poller metrics
- `GET /emails/fetcher/status` → Fetcher metrics

**Metrics tracked (in-memory):**

- Total runs, successful/failed runs
- Items processed, errors encountered
- Last run timestamp, average processing time
- Circuit breaker state (for poller)

## Known Gotchas & Troubleshooting

1. **"relation does not exist" errors**: Run `uv run alembic upgrade head`
2. **Mock data not matching**: Ensure generators use `app/testing/mock_data_templates.py`
3. **Email filtering too strict**: Check `app/normalization/banks.py` for missing domains
4. **Repository filter not working**: Use double underscore operators (`field__gt` not `field>`)
5. **UnitOfWork not committing**: Add explicit `await uow.commit()` before `async with` exit
6. **Structlog import errors**: Module not installed, run `uv sync`

## Documentation References

- Architecture deep-dive: `docs/architecture.md`
- Stage completion reports: `docs/Stage-{1-7}-Completion.md`
- Bank mappings: `app/normalization/banks.py` (inline docs)
- Mock refactoring: `docs/Mock-Data-Refactoring.md`
- Clear data feature: `docs/Clear-Existing-Data.md`

## Windows PowerShell Specifics

- **ALWAYS activate `.venv` before running Python commands** (or use `uv run` prefix)
- Check for venv: `if (Test-Path .venv) { .\.venv\Scripts\Activate.ps1 }`
- Venv activation script: `.\.venv\Scripts\Activate.ps1` (PowerShell) or `.\.venv\Scripts\activate.bat` (CMD)
- Verify activation: Prompt should show `(.venv)` prefix
- Use `uv` for dependency management (not pip)
- Run scripts: `./run_server.bat`, `./run_checks.bat`
- Terminal commands: Use `;` for multi-command lines
- Path separator: `\` (handled by Path objects in code)
- Two command patterns:
  - **Manual:** Activate venv, then run `python`, `pytest`, `alembic`, etc.
  - **Automatic:** Use `uv run <command>` which auto-activates venv
