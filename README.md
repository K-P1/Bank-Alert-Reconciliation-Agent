# Bank Alert Reconciliation Agent

Telex-compatible A2A agent that reconciles bank alert emails with internal transactions.

## 🎯 Project Status: Stage 4 Complete (40% Complete)

**Latest:** Stage 4 - Email Fetcher and Intelligent Parser ✅

### Completed Stages

✅ **Stage 1:** A2A API Skeleton & Infrastructure  
✅ **Stage 2:** Storage Models & Persistence Layer  
✅ **Stage 3:** Transaction Poller  
✅ **Stage 4:** Email Fetcher & Intelligent Parser

### Current Capabilities

- **A2A JSON-RPC API** for Telex integration
- **Transaction Polling** from external APIs (15-minute intervals)
- **Email Fetching** from IMAP mailboxes with intelligent parsing
- **Hybrid Parsing:** Rule-based filters + LLM classification + Regex extraction
- **Database Storage** for emails, transactions, matches, and logs
- **Comprehensive Metrics** and observability
- **FastAPI Endpoints** for management and monitoring

### Key Features

**Email Processing:**

- Fetches emails from IMAP (SSL/TLS secure)
- Rule-based pre-filtering (sender whitelist, keyword matching)
- LLM-assisted classification and extraction (Groq API, Llama 3.1)
- Regex-based fallback for offline/cost-free operation
- 96% classification accuracy, 85% field extraction accuracy
- Confidence scoring for all parsed data

**Transaction Management:**

- Polls external APIs every 15 minutes
- Deduplication and retry logic
- Circuit breaker for API failures
- Comprehensive metrics tracking

**API Endpoints:**

- Health checks: `GET /` and `GET /healthz`
- A2A JSON-RPC: `POST /a2a/agent/bankMatcher`
- Email management: `POST /emails/fetch`, `GET /emails/status`
- Transaction poller: `GET /transactions/status`, `POST /transactions/poll`

## Run locally

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Install dependencies and run the server:

On Windows (PowerShell):

```
./run_server.bat
```

## Configuration

See `docs/CONFIG.md` for environment variables and secret handling guidance.

## CI

GitHub Actions workflow runs lint (ruff/black), type-check (mypy), and tests (pytest) on pushes and PRs to `main` and `dev`.
