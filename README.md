# Bank Alert Reconciliation Agent (BARA) v3.0

## BARA Core Specification Compliant

BARA is a production-grade reconciliation service for Nigerian banking that automatically matches bank alert emails with transaction API data using a sophisticated rule-based matching engine.

## 🎯 System Overview

**Current Version:** 3.0.0 (BARA Core)  
**Status:** Production Ready  
**Compliance:** BARA Core Specification (12 Commands)  
**Architecture:** Unified Automation System

### Key Features

- ✅ **Email Ingestion:** IMAP-based fetching with whitelist filtering (118+ Nigerian banks)
- ✅ **Hybrid Parsing:** Rule-based → LLM (Groq) → Regex fallback for resilience
- ✅ **Transaction Polling:** Async API clients with retry policies and circuit breakers
- ✅ **7-Rule Matching Engine:** Weighted scoring (exact, fuzzy, temporal) with confidence ratings
- ✅ **Telex A2A Integration:** JSON-RPC 2.0 protocol with natural language command interface
- ✅ **Unified Automation:** Single orchestration service (email fetch + transaction poll + matching)
- ✅ **Simplified REST API:** 11 endpoints for direct service control

## 📊 Architecture

### Core Components

1. **Email Ingestion Pipeline** (`app/emails/`)

   - IMAP connector with bank whitelist filtering
   - Hybrid parser (rules → LLM → regex)
   - Background fetcher service
   - Metrics tracking

2. **Transaction Polling** (`app/transactions/`)

   - Pluggable client architecture (mock/real API)
   - Resilient polling with exponential backoff
   - Circuit breaker for API protection
   - Metrics tracking

3. **Matching Engine** (`app/matching/`)

   - 7 weighted rules (amount, reference, timestamp, description, currency, bank)
   - Fuzzy matching (rapidfuzz: Levenshtein + token_sort_ratio)
   - Candidate retrieval (composite key + range fallback)
   - Confidence scoring (0.0-1.0 scale)

4. **Automation Orchestration** (`app/core/automation.py`)

   - Unified cycle execution (fetch → poll → match)
   - Configurable interval (default: 15 minutes)
   - Start/stop/status control
   - Cycle statistics tracking

5. **A2A/Telex Integration** (`app/a2a/`)

   - JSON-RPC 2.0 endpoint (`/a2a/agent/bara`)
   - 12 BARA Core commands (natural language + structured)
   - Artifact formatting for rich responses
   - Execute method for automation control

6. **Database Layer** (`app/db/`)
   - Repository + UnitOfWork pattern
   - SQLAlchemy async ORM
   - Models: Email, Transaction, Match, ConfigLog
   - Alembic migrations

### Database Schema

```
emails              # Parsed email alerts
├── id (PK)
├── message_id
├── from_address
├── subject
├── amount
├── reference
├── timestamp
└── matched (bool)

transactions        # API transaction records
├── id (PK)
├── source_id
├── amount
├── reference
├── timestamp
└── matched (bool)

matches             # Matched pairs
├── id (PK)
├── email_id (FK)
├── transaction_id (FK)
├── confidence_score
├── rule_scores (JSON)
└── created_at

config_logs         # Automation configuration history
├── id (PK)
├── interval_seconds
├── changed_at
└── changed_by
```

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL 12+ (production) or SQLite (development)
- IMAP email account (for production)
- Groq API key (optional, for LLM parsing)

### Installation

```powershell
# Clone repository
git clone <repository-url>
cd "Bank Alert Reconciliation Agent"

# Create virtual environment with uv
uv venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
uv sync

# Run database migrations
uv run alembic upgrade head
```

### Configuration

Create `.env` file in project root:

```env
# Environment
ENV=development

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/bara
# Or for SQLite:
# DATABASE_URL=sqlite+aiosqlite:///./bara.db

# IMAP (optional in dev, uses mock data)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-email@gmail.com
IMAP_PASS=your-app-password

# LLM (optional, falls back to regex)
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.3-70b-versatile

# Automation
AUTOMATION_INTERVAL_SECONDS=900  # 15 minutes
AUTOMATION_ENABLED=false  # Set to true to auto-start
```

### Running the Server

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start server
./run_server.bat
# Or manually:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Server runs at `http://localhost:8000`

### Verify Installation

```powershell
# Health check
curl http://localhost:8000/healthz

# Expected response:
# {"status":"ok","env":"development"}
```

## 📡 API Reference

### Health & Monitoring

| Endpoint   | Method | Description                      |
| ---------- | ------ | -------------------------------- |
| `/`        | GET    | Basic health check               |
| `/healthz` | GET    | Detailed health with environment |

### A2A JSON-RPC Endpoint

**Endpoint:** `POST /a2a/agent/bara`

**12 BARA Core Commands:**

1. **help** - List available commands
2. **match_all** - Match all unmatched emails
3. **match_now** - Immediate matching with limit
4. **match_specific** - Match specific email IDs
5. **show_summary** - Reconciliation statistics
6. **list_unmatched** - List unmatched emails
7. **get_match_details** - Match details by ID
8. **start_automation** - Start background automation
9. **stop_automation** - Stop background automation
10. **get_status** - Current automation status
11. **search_matches** - Search matches by criteria
12. **export_report** - Generate reconciliation report

**Methods:**

- `status` - Health check with metrics
- `message/send` - Natural language command or structured params
- `execute` - Direct automation control (get_status, start, stop, run_cycle)

**Example Requests:**

```json
// Natural Language
{
  "jsonrpc": "2.0",
  "id": "nl-001",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "parts": [{"kind": "text", "text": "match 50 emails now"}]
    }
  }
}

// Structured Parameters
{
  "jsonrpc": "2.0",
  "id": "struct-001",
  "method": "message/send",
  "params": {
    "limit": 50,
    "summarize": true
  }
}

// Execute Method
{
  "jsonrpc": "2.0",
  "id": "exec-001",
  "method": "execute",
  "params": {
    "action": "run_cycle"
  }
}
```

### REST API - Automation Control

| Endpoint             | Method | Description                                          |
| -------------------- | ------ | ---------------------------------------------------- |
| `/automation/status` | GET    | Get automation status and metrics                    |
| `/automation/start`  | POST   | Start automation (body: `{"interval_seconds": 900}`) |
| `/automation/stop`   | POST   | Stop automation                                      |
| `/automation/match`  | POST   | Trigger manual matching (body: `{"limit": 50}`)      |

### REST API - Email Management

| Endpoint          | Method | Description                  |
| ----------------- | ------ | ---------------------------- |
| `/emails/fetch`   | POST   | Manually trigger email fetch |
| `/emails/metrics` | GET    | Get email fetcher metrics    |

### REST API - Transaction Management

| Endpoint                | Method | Description                       |
| ----------------------- | ------ | --------------------------------- |
| `/transactions/poll`    | POST   | Manually trigger transaction poll |
| `/transactions/metrics` | GET    | Get transaction poller metrics    |

## 🧪 Testing

### Run Tests

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Run all tests
pytest -q

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_matching.py -v
```

**Current Test Status:** 148 tests passing

### Mock Data for Testing

```powershell
# Seed dynamic mock data (50 transactions, 40 emails, 72-hour window)
python -m app.db.seed_mock 50 40 72

# Clear and reseed
python -m app.db.seed_mock 100 80 48 true

# Seed static test fixtures (for unit tests)
python -m tests.seed_fixtures
```

### Quality Checks

```powershell
# Run all checks (Ruff, Black, mypy)
./run_checks.bat

# Individual tools
ruff check .         # Linting
black .             # Formatting
mypy .              # Type checking
```

## 🛠️ Development Workflows

### Database Migrations

```powershell
# Check current version
alembic current

# Upgrade to latest
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Downgrade one version
alembic downgrade -1
```

### Adding a New Bank

Update `app/normalization/banks.py`:

```python
"moniepoint": {
    "code": "MONIE",
    "name": "Moniepoint MFB",
    "domains": ["moniepoint.com", "teamapt.com"],
    "category": "microfinance"
}
```

Email whitelist auto-updates. No other changes needed.

### Adding a Transaction Source

1. Create client in `app/transactions/clients/new_client.py`
2. Inherit from `BaseTransactionClient`
3. Implement: `fetch_transactions()`, `validate_credentials()`, `get_source_name()`
4. Update factory in poller configuration

### Adding a Matching Rule

1. Add rule function to `app/matching/rules.py`
2. Signature: `def rule_name(email: NormalizedEmail, txn: NormalizedTransaction) -> float`
3. Return: 0.0-1.0 score
4. Update `MatchingConfig.RULES` with weight
5. Scorer auto-executes new rule

## 📈 Monitoring & Metrics

### Automation Metrics

```json
{
  "running": true,
  "interval_seconds": 900,
  "total_cycles": 42,
  "successful_cycles": 40,
  "failed_cycles": 2,
  "last_run": "2025-06-15T10:30:00Z",
  "next_run": "2025-06-15T10:45:00Z"
}
```

### Email Fetcher Metrics

```json
{
  "total_fetches": 120,
  "total_emails_fetched": 450,
  "total_emails_processed": 425,
  "total_emails_stored": 400,
  "last_fetch_at": "2025-06-15T10:30:00Z",
  "last_fetch_duration_seconds": 2.5
}
```

### Transaction Poller Metrics

```json
{
  "total_polls": 120,
  "successful_polls": 118,
  "failed_polls": 2,
  "total_transactions_fetched": 500,
  "circuit_breaker_state": "closed",
  "last_poll_at": "2025-06-15T10:30:00Z"
}
```

## 🔒 Production Deployment

### Environment Variables (Production)

```env
ENV=production
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/bara
IMAP_HOST=imap.company.com
IMAP_USER=alerts@company.com
IMAP_PASS=<secure-password>
GROQ_API_KEY=<secure-key>
AUTOMATION_ENABLED=true
AUTOMATION_INTERVAL_SECONDS=900
LOG_LEVEL=INFO
```

### Docker Deployment

```bash
# Build image
docker build -t bara:3.0.0 -f docker/Dockerfile .

# Run container
docker run -d \
  --name bara \
  -p 8000:8000 \
  --env-file .env.production \
  bara:3.0.0
```

### Health Checks

Configure load balancer/orchestrator to monitor:

- `GET /healthz` (should return 200 with `{"status":"ok"}`)
- `GET /automation/status` (should return 200 with running state)

## 🐛 Troubleshooting

### Common Issues

**1. "relation does not exist" errors**

```powershell
uv run alembic upgrade head
```

**2. Mock data not matching**

- Ensure generators use `app/testing/mock_data_templates.py`
- Reseed data: `python -m app.db.seed_mock 50 40 72`

**3. Email filtering too strict**

- Check `app/normalization/banks.py` for missing bank domains
- Verify IMAP credentials in `.env`

**4. Tests failing**

```powershell
# Clear test database
rm bara_test.db
# Re-run migrations
uv run alembic upgrade head
# Run tests
pytest -q
```

## 📚 Documentation

- **Architecture:** `docs/architecture.md`
- **Telex Integration:** `docs/Telex-Commands-Reference.md`
- **API Tests:** `docs/BARA-Telex-Integration.postman_collection.json`

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Run quality checks (`./run_checks.bat`)
5. Ensure tests pass (`pytest -q`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

## 📄 License

See `LICENSE` file for details.

## 👥 Team

**Project Lead:** KP  
**Architecture:** Reconciliation Engine v3.0  
**Integration:** Telex A2A Protocol

---
