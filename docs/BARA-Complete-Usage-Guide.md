# BARA Complete Usage Guide

**Bank Alert Reconciliation Agent (BARA) v3.0**  
**Official Complete Usage Guide**  
**Last Updated:** November 16, 2025

---

## Complete Table of Contents
1. [Introduction & Overview](#1-introduction--overview)
2. [What BARA Does](#2-what-bara-does)
3. [System Architecture](#3-system-architecture)
4. [Installation & Local Setup](#4-installation--local-setup)
5. [Project Structure Walkthrough](#5-project-structure-walkthrough)
6. [Configuration & Environment Variables](#6-configuration--environment-variables)
7. [Database Setup & Migrations](#7-database-setup--migrations)
8. [Running BARA](#8-running-bara)
9. [Manual Operations via REST API](#9-manual-operations-via-rest-api)
10. [Automation Mode](#10-automation-mode)
11. [Using the Web Interface](#11-using-the-web-interface)
12. [Health Monitoring](#12-health-monitoring)
13. [Telex A2A Integration Overview](#13-telex-a2a-integration-overview)
14. [JSON-RPC 2.0 Protocol](#14-json-rpc-20-protocol)
15. [Natural Language Commands](#15-natural-language-commands)
16. [Complete Command Reference](#16-complete-command-reference)
17. [Advanced Telex Features](#17-advanced-telex-features)
18. [Complete Automation Flow (Non-Technical)](#18-complete-automation-flow-non-technical)
19. [Technical Deep Dive: How BARA Works](#19-technical-deep-dive-how-bara-works)
20. [Production Deployment](#20-production-deployment)
21. [Troubleshooting Guide](#21-troubleshooting-guide)

---

## 1. Introduction & Overview

### 1.1 What is BARA?

**BARA (Bank Alert Reconciliation Agent)** is a production-grade, open-source reconciliation service designed specifically for Nigerian banking systems. It automates the tedious process of matching bank alert emails with transaction records from banking APIs.

**The Problem BARA Solves:**

In Nigerian banking, customers receive email alerts for every transaction (credits, debits, transfers). Businesses processing hundreds or thousands of transactions daily face a critical challenge: **manually matching these email alerts with actual transaction records from their banking APIs** to ensure accuracy, detect fraud, and maintain proper accounting.

**BARA's Solution:**

BARA automatically:

- Fetches bank alert emails from your inbox via IMAP
- Polls transaction data from your banking API
- Uses a sophisticated 7-rule matching engine to pair alerts with transactions
- Provides confidence scores for each match
- Exposes results via REST API and Telex A2A integration

### 1.2 Key Features

✅ **Email Ingestion:** IMAP-based fetching with intelligent filtering (supports 118+ Nigerian banks)  
✅ **Hybrid Parsing:** Multi-stage parsing (rule-based → LLM → regex fallback) for maximum accuracy  
✅ **Transaction Polling:** Async API clients with retry policies and circuit breakers for reliability  
✅ **7-Rule Matching Engine:** Weighted scoring system combining exact, fuzzy, and temporal matching  
✅ **Telex A2A Integration:** Full JSON-RPC 2.0 protocol support with natural language commands  
✅ **Unified Automation:** Single orchestration service for continuous reconciliation  
✅ **Developer-Friendly:** REST API, mock data generators, comprehensive test suite

### 1.3 Who Should Use BARA?

**Target Users:**

- **Fintech Companies:** Reconciling payment transactions with bank alerts
- **E-commerce Platforms:** Verifying customer payments automatically
- **Accounting Firms:** Automating bank reconciliation for clients
- **Financial Institutions:** Building internal reconciliation tools
- **Developers:** Learning about reconciliation systems, async Python, or agent architectures

**Technical Requirements:**

- Comfortable with Python 3.13+
- Basic understanding of REST APIs
- Access to email server (IMAP) for bank alerts
- Optional: Access to transaction API (mock client available for testing)

### 1.4 System Requirements

**Minimum:**

- Python 3.13 or higher
- 2GB RAM
- 1GB disk space
- PostgreSQL 12+ (production) or SQLite (development)

**Recommended:**

- Python 3.13
- 4GB RAM
- PostgreSQL 14+
- Docker (for containerized deployment)

---

## 2. What BARA Does

### 2.1 Core Functionality

BARA operates in **three primary modes**:

#### Mode 1: Manual Operations (REST API)

Execute individual operations on-demand via HTTP endpoints:

- Fetch emails manually: `POST /emails/fetch`
- Poll transactions: `POST /transactions/poll`
- Run matching: `POST /matching/match`
- Query results: `GET /emails/`, `GET /transactions/`, `GET /matches/`

#### Mode 2: Automated Reconciliation (Automation Service)

Continuous orchestration of the full reconciliation cycle:

- Automatically fetches emails every N minutes (configurable interval)
- Polls transactions from APIs
- Runs matching engine on new data
- Tracks metrics and performance
- Control via `POST /automation/start` and `POST /automation/stop`

#### Mode 3: Telex A2A Integration (Natural Language)

Interact with BARA using natural language commands via Telex:

- `"match now"` - Run reconciliation
- `"show summary"` - View reconciliation statistics
- `"start automation"` - Begin continuous processing
- 12 total commands (see Part 2 for full reference)

### 2.2 The Reconciliation Process (High-Level)

```
┌─────────────────┐
│  Bank Alert     │
│  Emails (IMAP)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌─────────────────┐
│  Email Parsing  │      │  Transaction    │
│  (Hybrid)       │      │  API Polling    │
└────────┬────────┘      └────────┬────────┘
         │                        │
         ▼                        ▼
┌─────────────────────────────────────┐
│      Normalization Layer            │
│  (Standardize formats, enrich data) │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│       Matching Engine               │
│  (7 weighted rules, fuzzy logic)    │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Matched Pairs  │
│  (with scores)  │
└─────────────────┘
```

**Step-by-Step:**

1. **Email Fetching:** Connect to IMAP server, filter for bank emails (whitelist), download new messages
2. **Email Parsing:** Extract transaction details (amount, reference, date, bank) using hybrid parsing
3. **Transaction Polling:** Fetch transaction records from banking API
4. **Normalization:** Convert both emails and transactions to standardized format
5. **Bank Enrichment:** Match bank names/codes using Nigerian bank database (118+ entries)
6. **Candidate Retrieval:** Find potential matches using composite keys and range queries
7. **Rule Scoring:** Apply 7 weighted rules to score each potential match
8. **Match Storage:** Save matches with confidence scores and rule breakdowns
9. **Result Exposure:** Make results available via REST API and A2A endpoint

### 2.3 Matching Rules Explained

BARA uses **7 weighted rules** to calculate match confidence (0.0 to 1.0 scale):

| Rule                           | Weight | Description                                         |
| ------------------------------ | ------ | --------------------------------------------------- |
| **Exact Amount Match**         | 30%    | Transaction amounts match exactly                   |
| **Exact Reference Match**      | 25%    | Reference numbers match exactly                     |
| **Fuzzy Reference Similarity** | 15%    | References are similar (uses Levenshtein distance)  |
| **Timestamp Proximity**        | 15%    | Timestamps within ±72 hours (closer = higher score) |
| **Fuzzy Description Match**    | 10%    | Transaction descriptions are similar                |
| **Same Currency**              | 3%     | Both use same currency (NGN)                        |
| **Same Bank Enrichment**       | 2%     | Both involve the same bank                          |

**Total possible score:** 100% (1.0)  
**Typical good match:** 0.75+ (75%+)  
**Excellent match:** 0.90+ (90%+)

### 2.4 Supported Banks

BARA has **built-in support for 118+ Nigerian financial institutions**, including:

**Commercial Banks:** Access Bank, GTBank, Zenith, First Bank, UBA, Stanbic IBTC, etc.  
**Fintech:** Moniepoint, Kuda, OPay, PalmPay, Carbon, FairMoney, etc.  
**Microfinance:** Renmoney MFB, AB MFB, VFD MFB, etc.  
**Non-Interest Banks:** Jaiz Bank, Taj Bank, Lotus Bank

Each bank has:

- Official name and code
- Multiple domain aliases for email filtering
- Category classification (commercial, fintech, microfinance, etc.)

---

## 3. System Architecture

### 3.1 Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                     BARA Core System                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │           FastAPI Application Layer                     │  │
│  │  - REST API Endpoints (11 routes)                       │  │
│  │  - A2A/Telex JSON-RPC Endpoint                          │  │
│  │  - Health checks & metrics                              │  │
│  └─────────────────┬───────────────────────────────────────┘  │
│                    │                                           │
│  ┌─────────────────┴───────────────────────────────────────┐  │
│  │        Automation Orchestration Service                 │  │
│  │  - Unified cycle execution (fetch → poll → match)       │  │
│  │  - Configurable intervals (default: 15 min)             │  │
│  │  - Start/stop control, metrics tracking                 │  │
│  └─────────────────┬───────────────────────────────────────┘  │
│                    │                                           │
│  ┌────────┬────────┴────────┬──────────┐                      │
│  │        │                 │          │                      │
│  ▼        ▼                 ▼          ▼                      │
│┌──────┐┌─────────┐┌──────────┐┌─────────────┐                │
││Email ││Transaction││Matching  ||Normalization│                │
││Pipeline││ Poller  ││  Engine  ││   Layer     │                │
│└──┬───┘└────┬────┘└────┬─────┘└──────┬──────┘                │
│   │         │           │             │                       │
│   │    ┌────┴───────────┴─────────────┴────┐                 │
│   │    │   Repository + UnitOfWork Layer   │                 │
│   │    │   (Database Abstraction)           │                 │
│   │    └────────────────┬───────────────────┘                 │
│   │                     │                                     │
│   │    ┌────────────────┴───────────────────┐                 │
│   │    │   SQLAlchemy Async ORM             │                 │
│   │    │   - Email, Transaction, Match      │                 │
│   │    │   - ConfigLog models               │                 │
│   │    └────────────────┬───────────────────┘                 │
│   │                     │                                     │
│   │    ┌────────────────┴───────────────────┐                 │
│   │    │   PostgreSQL / SQLite Database     │                 │
│   │    └────────────────────────────────────┘                 │
│   │                                                            │
│   └──────────────────> External Services <───────────────────┘
│                        - IMAP Email Server
│                        - Transaction APIs
│                        - Groq LLM (optional)
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Core Components

#### 3.2.1 Email Ingestion Pipeline (`app/emails/`)

**Components:**

- **IMAP Connector** (`imap_connector.py`): Connects to email server, fetches messages
- **Email Filter** (`filter.py`): Whitelists Nigerian bank emails, blocks spam
- **Hybrid Parser** (`parser.py`): Orchestrates multi-stage parsing
  - **LLM Client** (`llm_client.py`): Groq API integration for intelligent parsing
  - **Regex Extractor** (`regex_extractor.py`): Pattern-based fallback
- **Email Fetcher** (`fetcher.py`): Background service for continuous fetching
- **Mock Generator** (`mock_email_generator.py`): Development mode email simulation

**Flow:**

```
IMAP Server → Fetch Messages → Whitelist Filter → Hybrid Parser → Database
                                                   ↓
                                      (Rules → LLM → Regex)
```

#### 3.2.2 Transaction Polling System (`app/transactions/`)

**Components:**

- **Base Client** (`clients/base.py`): Abstract interface for API clients
- **Mock Client** (`clients/mock_client.py`): Development mode transaction generator
- **Transaction Poller** (`poller.py`): Background polling service
- **Retry Policy** (`retry.py`): Exponential backoff + circuit breaker
- **Metrics Tracker** (`metrics.py`): Performance monitoring

**Features:**

- Pluggable client architecture (easy to add new APIs)
- Resilient error handling (retry with backoff)
- Circuit breaker prevents API overload
- Batch processing for efficiency

#### 3.2.3 Matching Engine (`app/matching/`)

**Components:**

- **Engine** (`engine.py`): Main orchestration (retrieve → score → rank → store)
- **Retrieval** (`retrieval.py`): Candidate selection strategies
  - Composite key lookup (amount + currency + date)
  - Range-based fallback (±5% amount, ±72 hours)
- **Rules** (`rules.py`): 7 weighted matching rules
- **Scorer** (`scorer.py`): Rule execution and aggregation
- **Fuzzy Matcher** (`fuzzy.py`): Levenshtein + token sort ratio utilities

**Matching Algorithm:**

```python
for email in unmatched_emails:
    candidates = retrieve_candidates(email)  # Composite key + range
    for txn in candidates:
        scores = apply_rules(email, txn)     # 7 rules
        total_score = weighted_sum(scores)
    best_match = highest_scoring_candidate
    if best_match.score >= threshold:
        save_match(email, best_match)
```

#### 3.2.4 Normalization Layer (`app/normalization/`)

**Purpose:** Standardize data from different sources into common format

**Components:**

- **Banks Database** (`banks.py`): 118+ Nigerian bank mappings
  ```python
  {
    "alias": {
      "code": "BANK_CODE",
      "name": "Official Name",
      "domains": ["domain1.com", "domain2.com"],
      "category": "commercial|fintech|microfinance"
    }
  }
  ```
- **Normalizer** (`normalizer.py`): Format conversion, enrichment
- **Models** (`models.py`): Pydantic schemas for normalized data

**Normalization Steps:**

1. Parse raw email/transaction
2. Extract amount, reference, timestamp, description
3. Normalize currency (NGN, USD, etc.)
4. Enrich bank information from mapping
5. Validate against schema
6. Return standardized object

#### 3.2.5 Database Layer (`app/db/`)

**Design Pattern:** Repository + UnitOfWork (inspired by Clean Architecture)

**Components:**

- **Base Repository** (`repository.py`): CRUD operations + filter operators
- **Specialized Repositories:**
  - `email_repository.py`: Email-specific queries
  - `transaction_repository.py`: Transaction queries with advanced filtering
  - `match_repository.py`: Match queries with joins
  - `log_repository.py`: Activity logging
  - `config_repository.py`: Configuration history
- **UnitOfWork** (`unit_of_work.py`): Transaction management
- **Models** (`models/*.py`): SQLAlchemy ORM models
- **Migrations** (`migrations/`): Alembic version control

**Usage Pattern:**

```python
from app.db.unit_of_work import UnitOfWork

async with UnitOfWork() as uow:
    email = await uow.emails.get_by_message_id(msg_id)
    transactions = await uow.transactions.filter(amount__gt=1000)
    match = await uow.matches.create(email_id=..., transaction_id=...)
    await uow.commit()  # Explicit commit when needed
```

**Filter Operators:**

- `field__lt`: Less than
- `field__gt`: Greater than
- `field__gte`: Greater than or equal
- `field__lte`: Less than or equal
- `field__ne`: Not equal

#### 3.2.6 Automation Orchestration (`app/core/automation.py`)

**Replaces:** Separate email fetcher + transaction poller services (v2.0)

**Unified Cycle:**

```python
async def run_cycle():
    1. Fetch new emails from IMAP
    2. Poll new transactions from API
    3. Run matching engine on unmatched items
    4. Update metrics
    5. Log cycle completion
```

**Features:**

- Configurable interval (default: 15 minutes)
- Start/stop control via REST API or A2A
- Metrics tracking (total cycles, success/failure rates)
- Error resilience (continues running after failures)

#### 3.2.7 A2A/Telex Integration (`app/a2a/`)

**Components:**

- **Router** (`router.py`): JSON-RPC 2.0 endpoint implementation
- **Command Interpreter** (`command_interpreter.py`): Natural language parsing
- **Command Handlers** (`command_handlers.py`): Business logic for each command

**Supported Methods:**

- `status`: System health check with metrics
- `message/send`: Natural language command execution
- `execute`: Structured command execution (future)

**Example Request:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "parts": [{ "text": "match 50 emails" }]
    }
  }
}
```

**Example Response:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "message": {
      "kind": "message",
      "parts": [
        { "text": "✅ Matched 42 of 50 emails (84%)" },
        {
          "kind": "artifact",
          "identifier": "match-results",
          "type": "application/json",
          "title": "Match Results",
          "content": "{...}"
        }
      ]
    }
  }
}
```

### 3.3 Data Flow Architecture

**Complete reconciliation flow:**

```
┌─────────────────┐
│ 1. EMAIL FETCH  │
│ (IMAP Connector)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. WHITELIST    │
│ (Bank Filter)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. PARSE        │
│ (Hybrid Parser) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────┐
│ 4. NORMALIZE    │    │ 5. TRANSACTION   │
│ (Email)         │    │    POLL (API)    │
└────────┬────────┘    └────────┬─────────┘
         │                      │
         │                      ▼
         │             ┌──────────────────┐
         │             │ 6. NORMALIZE     │
         │             │    (Transaction) │
         │             └────────┬─────────┘
         │                      │
         └──────────┬───────────┘
                    ▼
         ┌────────────────────┐
         │ 7. BANK ENRICHMENT │
         │ (118+ mappings)    │
         └─────────┬──────────┘
                   │
                   ▼
         ┌────────────────────┐
         │ 8. CANDIDATE       │
         │    RETRIEVAL       │
         └─────────┬──────────┘
                   │
                   ▼
         ┌────────────────────┐
         │ 9. RULE SCORING    │
         │    (7 rules)       │
         └─────────┬──────────┘
                   │
                   ▼
         ┌────────────────────┐
         │ 10. MATCH STORAGE  │
         │     (with scores)  │
         └────────────────────┘
```

---

## 4. Installation & Local Setup

### 4.1 Prerequisites

Before installing BARA, ensure you have:

1. **Python 3.13+** installed ([Download](https://www.python.org/downloads/))
2. **Git** installed ([Download](https://git-scm.com/downloads))
3. **uv** package manager installed ([Installation guide](https://docs.astral.sh/uv/))
4. **PostgreSQL 12+** (production) or SQLite (development, auto-configured)
5. **Text editor or IDE** (VS Code recommended)

**Check your installations:**

```powershell
python --version          # Should show 3.13+
git --version
uv --version              # Should show uv package manager
psql --version            # Optional for production
```

### 4.2 Clone the Repository

```powershell
# Clone BARA repository
git clone https://github.com/K-P1/Bank-Alert-Reconciliation-Agent.git

# Navigate to project directory
cd Bank-Alert-Reconciliation-Agent

# Switch to dev branch (recommended for latest features)
git checkout dev
```

### 4.3 Set Up Virtual Environment

**BARA uses `.venv` managed by `uv` for dependency management.**

```powershell
# Create virtual environment
uv venv

# Activate virtual environment (PowerShell)
.\.venv\Scripts\Activate.ps1

# Verify activation - you should see (.venv) in your prompt
# (.venv) PS C:\...\Bank-Alert-Reconciliation-Agent>

# Install dependencies
uv sync
```

**Alternative - Using `uv run` (auto-activates venv):**

```powershell
# Instead of manual activation, prefix commands with `uv run`
uv run python --version
uv run pytest
uv run alembic upgrade head
```

### 4.4 Configure Environment Variables

BARA uses environment variables for configuration. Create a `.env` file:

```powershell
# Copy example environment file
cp .env.example .env

# Edit .env with your preferred editor
notepad .env
# or: code .env (VS Code)
```

**Minimal development configuration:**

```bash
# .env file

# Environment mode
ENV=development
DEBUG=true

# Database (SQLite for dev - auto-created)
DATABASE_URL=sqlite+aiosqlite:///./bara_dev.db

# Agent name
A2A_AGENT_NAME=BARA

# Email settings (optional for dev - uses mock data if not set)
# IMAP_HOST=imap.gmail.com
# IMAP_USER=your-email@gmail.com
# IMAP_PASS=your-app-password

# LLM settings (optional - uses regex fallback if not set)
# GROQ_API_KEY=your-groq-api-key
# GROQ_MODEL=llama-3.1-8b-instant

# Mock data configuration (for development)
MOCK_EMAIL_COUNT=10
POLLER_BATCH_SIZE=100
```

**Production configuration:**

```bash
# .env file (production)

# Environment mode
ENV=production
DEBUG=false

# Database (PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/bara_prod

# Agent name
A2A_AGENT_NAME=BARA

# Email settings (REQUIRED for production)
IMAP_HOST=imap.gmail.com
IMAP_USER=alerts@yourcompany.com
IMAP_PASS=your-secure-app-password

# LLM settings (recommended for production)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.1-8b-instant

# Batch sizes
MOCK_EMAIL_COUNT=0  # Disable mock data
POLLER_BATCH_SIZE=500
```

### 4.5 Database Setup

#### Development (SQLite - Automatic)

SQLite database is auto-created when you run migrations:

```powershell
# Activate venv first
.\.venv\Scripts\Activate.ps1

# Run database migrations
alembic upgrade head
# or: uv run alembic upgrade head

# Verify database file created
dir bara_dev.db  # Should exist now
```

#### Production (PostgreSQL)

**Step 1: Install PostgreSQL**

```powershell
# Download from https://www.postgresql.org/download/windows/
# Or use Chocolatey:
choco install postgresql
```

**Step 2: Create Database**

```powershell
# Connect to PostgreSQL
psql -U postgres

# In psql shell:
CREATE DATABASE bara_prod;
CREATE USER bara_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE bara_prod TO bara_user;
\q  # Exit psql
```

**Step 3: Update `.env`**

```bash
DATABASE_URL=postgresql+asyncpg://bara_user:secure_password@localhost:5432/bara_prod
```

**Step 4: Run Migrations**

```powershell
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

### 4.6 Verify Installation

**Run the test suite:**

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Run all tests
pytest -q
# or: uv run pytest -q

# Expected output:
# ............................  [100%]
# 28 passed in 2.31s
```

**Start the development server:**

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Start server (with hot reload)
./run_server.bat
# or: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# or: uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Test the server:**

```powershell
# In a new terminal, test health endpoint
curl http://localhost:8000/healthz

# Expected response:
# {"status":"healthy","environment":"development","version":"3.0.0"}
```

**Access interactive API docs:**
Open your browser to `http://localhost:8000/docs` to see the Swagger UI.

### 4.7 Seed Mock Data (Development)

For testing and development, populate the database with realistic mock data:

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Seed with 50 transactions, 40 emails over 72 hours
python -m app.db.seed_mock 50 40 72
# or: uv run python -m app.db.seed_mock 50 40 72

# Clear existing data first (prompts for confirmation)
python -m app.db.seed_mock 100 80 48 true

# For unit tests (static fixtures)
python -m tests.seed_fixtures
```

**Mock data features:**

- Realistic Nigerian bank names and references
- Matching transaction/email pairs for testing
- Configurable volume and time spread
- Uses shared templates from `app/testing/mock_data_templates.py`

### 4.8 Common Installation Issues

**Issue 1: `uv` not found**

```powershell
# Install uv package manager
pip install uv
```

**Issue 2: Virtual environment activation fails**

```powershell
# PowerShell execution policy issue
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then retry activation
.\.venv\Scripts\Activate.ps1
```

**Issue 3: Database migration errors**

```powershell
# Check Alembic version
alembic current

# If "can't locate revision", reset migrations
alembic stamp head

# Then retry upgrade
alembic upgrade head
```

**Issue 4: Import errors after `uv sync`**

```powershell
# Reinstall dependencies
uv sync --reinstall

# Verify installation
uv run python -c "import fastapi; import sqlalchemy; print('OK')"
```

**Issue 5: Port 8000 already in use**

```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID)
taskkill /PID <PID> /F

# Or use a different port
uvicorn app.main:app --reload --port 8001
```

---

## 5. Project Structure Walkthrough

### 5.1 Directory Overview

```
Bank-Alert-Reconciliation-Agent/
├── app/                          # Main application code
│   ├── a2a/                      # Telex A2A JSON-RPC integration
│   ├── core/                     # Core services (config, logging, automation)
│   ├── db/                       # Database layer (models, repos, migrations)
│   ├── emails/                   # Email ingestion pipeline
│   ├── matching/                 # Matching engine
│   ├── normalization/            # Data normalization layer
│   ├── testing/                  # Mock data generators & templates
│   ├── transactions/             # Transaction polling system
│   └── main.py                   # FastAPI application entry point
├── docs/                         # Documentation
├── tests/                        # Test suite
├── docker/                       # Docker configuration
├── .env                          # Environment variables (create from .env.example)
├── alembic.ini                   # Alembic configuration
├── pyproject.toml                # Project dependencies (uv/pip)
├── README.md                     # Project README
├── run_server.bat                # Windows server launcher
└── run_checks.bat                # Code quality checks
```

### 5.2 Core Application (`app/`)

#### `app/main.py` - Application Entry Point

**Purpose:** FastAPI application factory with lifespan management

**Key components:**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize services (email fetcher, automation)
    # Shutdown: Cleanup (stop background tasks)

app = FastAPI(
    title="BARA - Bank Alert Reconciliation Agent",
    lifespan=lifespan
)

# Include routers
app.include_router(a2a_router)          # /a2a/agent/bara
app.include_router(automation_router)   # /automation/*
app.include_router(emails_router)       # /emails/*
app.include_router(transactions_router) # /transactions/*
```

**When to modify:**

- Adding new routers
- Changing startup/shutdown behavior
- Adding middleware

#### `app/core/` - Core Services

**Files:**

- `config.py`: Pydantic settings (loads from `.env`)
- `logging.py`: Structured logging configuration (structlog)
- `automation.py`: Unified automation orchestration service
- `automation_router.py`: REST API for automation control

**Configuration pattern:**

```python
from app.core.config import get_settings

settings = get_settings()  # Cached singleton
database_url = settings.DATABASE_URL
env = settings.ENV  # "development" | "staging" | "production"
```

**Automation service usage:**

```python
from app.core.automation import get_automation_service

automation = get_automation_service()
await automation.start(interval_seconds=900)  # 15 min
await automation.stop()
status = automation.get_status()
```

#### `app/db/` - Database Layer

**Architecture:** Repository + UnitOfWork pattern

**Key files:**

- `base.py`: Database engine setup
- `unit_of_work.py`: Transaction management context manager
- `repository.py`: Base CRUD operations + filter operators
- `models/`: SQLAlchemy ORM models
- `repositories/`: Specialized repository classes
- `migrations/`: Alembic migration versions

**Models:**

```python
# app/db/models/
email.py         # Email table (message_id, amount, reference, etc.)
transaction.py   # Transaction table (source_id, amount, reference, etc.)
match.py         # Match table (email_id, transaction_id, confidence_score)
log.py           # Activity log table
config.py        # Configuration history
```

**Repository usage:**

```python
from app.db.unit_of_work import UnitOfWork

async with UnitOfWork() as uow:
    # Get by ID
    email = await uow.emails.get_by_id(1)

    # Filter with operators
    high_value = await uow.transactions.filter(amount__gt=10000)
    recent = await uow.transactions.filter(
        timestamp__gte=datetime(2025, 1, 1)
    )

    # Create
    new_match = await uow.matches.create(
        email_id=1,
        transaction_id=2,
        confidence_score=0.95
    )

    # Commit changes
    await uow.commit()
```

#### `app/emails/` - Email Ingestion

**Components:**

| File                      | Purpose                                      |
| ------------------------- | -------------------------------------------- |
| `imap_connector.py`       | IMAP connection & message fetching           |
| `filter.py`               | Bank whitelist filtering (118+ banks)        |
| `parser.py`               | Hybrid parsing orchestration                 |
| `llm_client.py`           | Groq LLM integration for intelligent parsing |
| `regex_extractor.py`      | Pattern-based fallback extraction            |
| `fetcher.py`              | Background email fetching service            |
| `mock_email_generator.py` | Development mode email simulation            |
| `router.py`               | REST API endpoints                           |
| `config.py`               | Email-specific configuration                 |
| `metrics.py`              | Email fetcher metrics tracking               |
| `models.py`               | Pydantic schemas                             |

**Parsing flow:**

```python
# 1. Rule-based extraction (fast, deterministic)
if can_extract_with_rules(email):
    return rule_extraction(email)

# 2. LLM extraction (intelligent, flexible)
elif groq_api_available:
    return llm_extraction(email)

# 3. Regex fallback (last resort)
else:
    return regex_extraction(email)
```

#### `app/transactions/` - Transaction Polling

**Components:**

| File                     | Purpose                                  |
| ------------------------ | ---------------------------------------- |
| `clients/base.py`        | Abstract client interface                |
| `clients/mock_client.py` | Mock data generator for dev              |
| `poller.py`              | Background polling service               |
| `retry.py`               | Retry policy + circuit breaker utilities |
| `router.py`              | REST API endpoints                       |
| `config.py`              | Transaction-specific configuration       |
| `metrics.py`             | Poller metrics tracking                  |
| `cli.py`                 | Command-line interface (future)          |

**Adding a new API client:**

```python
# 1. Create new client file
# app/transactions/clients/my_bank_client.py

from app.transactions.clients.base import BaseTransactionClient

class MyBankClient(BaseTransactionClient):
    async def fetch_transactions(self, since, until, limit):
        # Implement API call
        pass

    async def validate_credentials(self):
        # Test connection
        pass

    def get_source_name(self):
        return "MyBank API"

# 2. Update poller to use new client
# app/transactions/poller.py
client = MyBankClient(api_key=settings.MY_BANK_API_KEY)
```

#### `app/matching/` - Matching Engine

**Components:**

| File           | Purpose                                       |
| -------------- | --------------------------------------------- |
| `engine.py`    | Main orchestration (retrieve → score → store) |
| `retrieval.py` | Candidate retrieval strategies                |
| `rules.py`     | 7 weighted matching rules                     |
| `scorer.py`    | Rule execution and aggregation                |
| `fuzzy.py`     | Fuzzy matching utilities (rapidfuzz)          |
| `config.py`    | Matching-specific configuration               |
| `metrics.py`   | Matching engine metrics                       |
| `models.py`    | Pydantic schemas                              |

**Rule implementation example:**

```python
# app/matching/rules.py

def rule_exact_amount(email: NormalizedEmail, txn: NormalizedTransaction) -> float:
    """Exact amount match rule (weight: 0.30)."""
    if email.amount == txn.amount:
        return 1.0
    return 0.0

def rule_fuzzy_reference(email: NormalizedEmail, txn: NormalizedTransaction) -> float:
    """Fuzzy reference similarity (weight: 0.15)."""
    if not email.reference or not txn.reference:
        return 0.0

    similarity = fuzz.ratio(email.reference, txn.reference) / 100.0
    return similarity
```

#### `app/normalization/` - Data Normalization

**Purpose:** Convert raw data into standardized format for matching

**Components:**

| File            | Purpose                               |
| --------------- | ------------------------------------- |
| `banks.py`      | Nigerian bank mappings (118+ entries) |
| `normalizer.py` | Format conversion & enrichment        |
| `models.py`     | Pydantic schemas for normalized data  |

**Bank mapping structure:**

```python
# app/normalization/banks.py

BANK_MAPPINGS = {
    "gtb": {
        "code": "GTB",
        "name": "Guaranty Trust Bank",
        "domains": ["gtbank.com", "gtbankplc.com"],
        "category": "commercial"
    },
    "moniepoint": {
        "code": "MONIE",
        "name": "Moniepoint MFB",
        "domains": ["moniepoint.com", "teamapt.com"],
        "category": "microfinance"
    },
    # ... 116+ more banks
}
```

**Usage:**

```python
from app.normalization.normalizer import normalize_email, normalize_transaction

normalized_email = normalize_email(raw_email_data)
normalized_txn = normalize_transaction(raw_api_data)

# Both now have standardized schema:
# - amount: Decimal
# - currency: str
# - reference: str
# - timestamp: datetime
# - bank_code: str
# - bank_name: str
```

#### `app/a2a/` - Telex Integration

**Components:**

| File                     | Purpose                              |
| ------------------------ | ------------------------------------ |
| `router.py`              | JSON-RPC 2.0 endpoint implementation |
| `command_interpreter.py` | Natural language command parsing     |
| `command_handlers.py`    | Business logic for each command      |

**Command flow:**

```
User message → Interpreter → Handler → Database/Services → Response
   "match now"  → "match_now" → match_now() → Matching Engine → Result
```

#### `app/testing/` - Test Utilities

**Components:**

| File                     | Purpose                              |
| ------------------------ | ------------------------------------ |
| `mock_data_templates.py` | Shared templates for mock generation |

**Templates ensure consistency:**

```python
# app/testing/mock_data_templates.py

TRANSACTION_TEMPLATES = [
    "Credit", "Debit", "Transfer", "ATM Withdrawal", "POS Purchase", "Bill Payment"
]

NIGERIAN_BANKS = [
    "GTBank", "Access Bank", "Zenith", "First Bank", "UBA", "Stanbic IBTC",
    "Moniepoint", "Kuda"
]

# Used by both:
# - app/emails/mock_email_generator.py
# - app/transactions/clients/mock_client.py
# - app/db/seed_mock.py
```

### 5.3 Tests (`tests/`)

**Structure:**

```
tests/
├── conftest.py                      # Pytest fixtures (DB, client, test data)
├── seed_fixtures.py                 # Static test data seeding
├── test_a2a_jsonrpc.py              # A2A endpoint tests
├── test_a2a_natural_language.py     # Command interpreter tests
├── test_command_interpreter.py      # Command parsing tests
├── test_database.py                 # Database layer tests
├── test_emails.py                   # Email pipeline tests
├── test_health.py                   # Health endpoint tests
├── test_matching.py                 # Matching engine tests
├── test_normalization.py            # Normalization tests
├── test_poller.py                   # Transaction poller tests
└── fixtures/                        # Sample data
    ├── sample_emails.py
    └── sample_transactions.py
```

**Running tests:**

```powershell
# All tests
pytest -q

# Specific test file
pytest tests/test_matching.py -v

# With coverage
pytest --cov=app tests/

# Only matching tests
pytest -k "matching" -v
```

### 5.4 Documentation (`docs/`)

**Files:**

- `architecture.md`: Deep dive into system architecture
- `Stage-{1-7}-Completion.md`: Development stage reports
- `Telex-Commands-Reference.md`: Complete A2A command documentation
- `BARA-Telex-Integration.postman_collection.json`: Postman collection
- `telex_workflow.json`: Workflow definitions
- `Mock-Data-Refactoring.md`: Mock data system documentation
- `Clear-Existing-Data.md`: Data clearing feature documentation

---

## 6. Configuration & Environment Variables

### 6.1 Complete Environment Variable Reference

| Variable            | Type    | Default       | Description                                              |
| ------------------- | ------- | ------------- | -------------------------------------------------------- |
| `ENV`               | string  | `development` | Environment mode: `development`, `staging`, `production` |
| `DEBUG`             | boolean | `true`        | Enable debug logging and development features            |
| `A2A_AGENT_NAME`    | string  | `BARA`        | Agent name for A2A JSON-RPC protocol                     |
| `DATABASE_URL`      | string  | SQLite auto   | Database connection URL                                  |
| `TEST_DATABASE_URL` | string  | None          | Separate test database URL                               |
| `IMAP_HOST`         | string  | None          | IMAP server hostname (e.g., `imap.gmail.com`)            |
| `IMAP_USER`         | string  | None          | IMAP username/email                                      |
| `IMAP_PASS`         | string  | None          | IMAP password or app-specific password                   |
| `LLM_PROVIDER`      | string  | None          | LLM provider name (e.g., `groq`, `openai`)               |
| `GROQ_API_KEY`      | string  | None          | Groq API key for LLM parsing                             |
| `GROQ_MODEL`        | string  | None          | Groq model name (e.g., `llama-3.1-8b-instant`)           |
| `MOCK_EMAIL_COUNT`  | integer | `10`          | Number of mock emails to generate in dev mode            |
| `POLLER_BATCH_SIZE` | integer | `100`         | Batch size for transaction polling                       |

### 6.2 Environment-Specific Configurations

#### Development Configuration

**Purpose:** Local development, testing, rapid iteration

**Key features:**

- Uses SQLite database (auto-created)
- Mock data fallback when external services unavailable
- Verbose logging
- Hot reload enabled
- No external API requirements

**`.env` file:**

```bash
ENV=development
DEBUG=true
A2A_AGENT_NAME=BARA
DATABASE_URL=sqlite+aiosqlite:///./bara_dev.db
MOCK_EMAIL_COUNT=20
POLLER_BATCH_SIZE=50

# Optional: Enable real services
# IMAP_HOST=imap.gmail.com
# IMAP_USER=test@example.com
# IMAP_PASS=app-password
# GROQ_API_KEY=gsk_test_key
# GROQ_MODEL=llama-3.1-8b-instant
```

#### Staging Configuration

**Purpose:** Pre-production testing, integration testing

**Key features:**

- Uses PostgreSQL database
- Real external services (IMAP, APIs)
- Moderate logging
- Similar to production setup

**`.env` file:**

```bash
ENV=staging
DEBUG=false
A2A_AGENT_NAME=BARA-STAGING
DATABASE_URL=postgresql+asyncpg://bara_staging:password@staging-db:5432/bara_staging
IMAP_HOST=imap.gmail.com
IMAP_USER=staging-alerts@company.com
IMAP_PASS=secure-app-password
GROQ_API_KEY=gsk_staging_key
GROQ_MODEL=llama-3.1-8b-instant
MOCK_EMAIL_COUNT=0
POLLER_BATCH_SIZE=200
```

#### Production Configuration

**Purpose:** Live production environment

**Key features:**

- PostgreSQL database (required)
- All external services configured
- Error logging only
- No mock data
- Performance optimized

**`.env` file:**

```bash
ENV=production
DEBUG=false
A2A_AGENT_NAME=BARA
DATABASE_URL=postgresql+asyncpg://bara_prod:strong_password@prod-db:5432/bara_prod
IMAP_HOST=imap.gmail.com
IMAP_USER=alerts@company.com
IMAP_PASS=secure-app-password
GROQ_API_KEY=gsk_production_key
GROQ_MODEL=llama-3.1-8b-instant
MOCK_EMAIL_COUNT=0
POLLER_BATCH_SIZE=500
```

### 6.3 Email Configuration (IMAP)

**Supported providers:**

- Gmail
- Outlook/Office 365
- Yahoo Mail
- Custom IMAP servers

#### Gmail Setup

**1. Enable IMAP in Gmail:**

- Go to Settings → Forwarding and POP/IMAP
- Enable IMAP access
- Save changes

**2. Create App Password:**

- Go to Google Account → Security
- Enable 2-Step Verification
- Go to App Passwords
- Create new app password for "Mail"
- Copy the 16-character password

**3. Configure BARA:**

```bash
IMAP_HOST=imap.gmail.com
IMAP_USER=your-email@gmail.com
IMAP_PASS=generated-app-password
```

#### Outlook/Office 365 Setup

```bash
IMAP_HOST=outlook.office365.com
IMAP_USER=your-email@outlook.com
IMAP_PASS=your-password
```

#### Yahoo Mail Setup

```bash
IMAP_HOST=imap.mail.yahoo.com
IMAP_USER=your-email@yahoo.com
IMAP_PASS=app-specific-password
```

### 6.4 LLM Configuration (Groq)

**Why Groq?**

- Fast inference (lower latency)
- Cost-effective
- Supports open-source models
- Good for production workloads

**Setup:**

1. **Get API Key:**

   - Sign up at [groq.com](https://groq.com)
   - Go to API Keys section
   - Create new API key
   - Copy the key (starts with `gsk_`)

2. **Configure BARA:**

```bash
GROQ_API_KEY=gsk_your_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

**Supported models:**

- `llama-3.1-8b-instant` (recommended, fast)
- `llama-3.1-70b-versatile` (more accurate, slower)
- `mixtral-8x7b-32768` (alternative)

**Fallback behavior:**
If Groq is not configured, BARA automatically falls back to regex extraction (no LLM needed for basic operation).

### 6.5 Database Configuration

#### SQLite (Development)

**Auto-configured:** No manual setup needed

```bash
DATABASE_URL=sqlite+aiosqlite:///./bara_dev.db
```

**File location:** `./bara_dev.db` (relative to project root)

**Benefits:**

- Zero setup
- Fast for development
- Easy to delete and recreate

**Limitations:**

- Not suitable for production
- No concurrent writes
- Limited performance

#### PostgreSQL (Production)

**Connection string format:**

```
postgresql+asyncpg://username:password@host:port/database
```

**Examples:**

```bash
# Local PostgreSQL
DATABASE_URL=postgresql+asyncpg://bara_user:password@localhost:5432/bara_prod

# Docker PostgreSQL
DATABASE_URL=postgresql+asyncpg://bara_user:password@postgres:5432/bara_prod

# Cloud PostgreSQL (Heroku)
DATABASE_URL=postgresql+asyncpg://user:pass@ec2-host.compute.amazonaws.com:5432/db_name

# Cloud PostgreSQL (Render)
DATABASE_URL=postgresql+asyncpg://user:pass@dpg-xxxxx-a.oregon-postgres.render.com/db_name
```

**Connection pooling (optional):**

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db?max_size=20&min_size=5
```

### 6.6 Configuration Best Practices

**Security:**

1. **Never commit `.env` to git** (already in `.gitignore`)
2. Use strong passwords for production databases
3. Rotate API keys regularly
4. Use app-specific passwords for email (not account password)
5. Restrict database user permissions (no DROP, CREATE USER, etc.)

**Performance:**

1. Use PostgreSQL for production (not SQLite)
2. Increase `POLLER_BATCH_SIZE` for high-volume systems
3. Adjust automation interval based on your needs (default: 15 min)
4. Enable database connection pooling

**Reliability:**

1. Set `DEBUG=false` in production
2. Monitor error logs
3. Use separate test database (`TEST_DATABASE_URL`)
4. Keep backups of production database

**Development:**

1. Use mock data when external services unavailable
2. Enable `DEBUG=true` for verbose logging
3. Use SQLite for faster setup
4. Commit `.env.example` with sample values (no secrets)

---

## 7. Database Setup & Migrations

### 7.1 Database Schema

BARA uses **5 main tables**:

#### `emails` Table

Stores parsed bank alert emails.

| Column         | Type     | Description                            |
| -------------- | -------- | -------------------------------------- |
| `id`           | Integer  | Primary key (auto-increment)           |
| `message_id`   | String   | Unique email message ID                |
| `from_address` | String   | Sender email address                   |
| `subject`      | String   | Email subject line                     |
| `body`         | Text     | Full email body content                |
| `amount`       | Decimal  | Extracted transaction amount           |
| `currency`     | String   | Currency code (NGN, USD, etc.)         |
| `reference`    | String   | Transaction reference number           |
| `description`  | String   | Transaction description                |
| `timestamp`    | DateTime | Transaction timestamp (from email)     |
| `bank_code`    | String   | Enriched bank code (e.g., GTB, ACCESS) |
| `bank_name`    | String   | Enriched bank name                     |
| `matched`      | Boolean  | Whether email has been matched         |
| `created_at`   | DateTime | When record was created                |
| `updated_at`   | DateTime | Last update timestamp                  |

#### `transactions` Table

Stores transaction records from API polling.

| Column        | Type     | Description                           |
| ------------- | -------- | ------------------------------------- |
| `id`          | Integer  | Primary key (auto-increment)          |
| `source_id`   | String   | Unique transaction ID from source API |
| `source_name` | String   | API source name (e.g., "Mock Client") |
| `amount`      | Decimal  | Transaction amount                    |
| `currency`    | String   | Currency code                         |
| `reference`   | String   | Transaction reference number          |
| `description` | String   | Transaction description               |
| `timestamp`   | DateTime | Transaction timestamp (from API)      |
| `bank_code`   | String   | Enriched bank code                    |
| `bank_name`   | String   | Enriched bank name                    |
| `matched`     | Boolean  | Whether transaction has been matched  |
| `metadata`    | JSON     | Additional API-specific data          |
| `created_at`  | DateTime | When record was created               |
| `updated_at`  | DateTime | Last update timestamp                 |

#### `matches` Table

Stores matched email-transaction pairs with scores.

| Column             | Type     | Description                           |
| ------------------ | -------- | ------------------------------------- |
| `id`               | Integer  | Primary key (auto-increment)          |
| `email_id`         | Integer  | Foreign key to `emails.id`            |
| `transaction_id`   | Integer  | Foreign key to `transactions.id`      |
| `confidence_score` | Float    | Overall match confidence (0.0 to 1.0) |
| `rule_scores`      | JSON     | Individual rule scores breakdown      |
| `created_at`       | DateTime | When match was created                |

**Example `rule_scores` JSON:**

```json
{
  "exact_amount": 1.0,
  "exact_reference": 1.0,
  "fuzzy_reference": 0.85,
  "timestamp_proximity": 0.9,
  "fuzzy_description": 0.75,
  "same_currency": 1.0,
  "same_bank": 1.0
}
```

#### `config_logs` Table

Stores automation configuration history.

| Column             | Type     | Description                        |
| ------------------ | -------- | ---------------------------------- |
| `id`               | Integer  | Primary key (auto-increment)       |
| `interval_seconds` | Integer  | Automation interval (seconds)      |
| `started_at`       | DateTime | When automation started            |
| `stopped_at`       | DateTime | When automation stopped (nullable) |
| `created_by`       | String   | User/system that made change       |

#### `activity_logs` Table (future)

Will store detailed activity logs for audit trails.

### 7.2 Alembic Migrations

BARA uses **Alembic** for database version control.

**Migration files location:** `app/db/migrations/versions/`

#### View Current Migration Version

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Check current version
alembic current
# Output: 9d854018b949 (head)
```

#### Apply Migrations (Upgrade)

```powershell
# Upgrade to latest version
alembic upgrade head

# Upgrade to specific version
alembic upgrade 9d854018b949

# Upgrade one version
alembic upgrade +1
```

#### Rollback Migrations (Downgrade)

```powershell
# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade 9d854018b949

# Downgrade to base (empty database)
alembic downgrade base
```

#### Create New Migration

**After modifying SQLAlchemy models:**

```powershell
# Auto-generate migration from model changes
alembic revision --autogenerate -m "add user authentication table"

# Review generated migration in app/db/migrations/versions/
# Edit if needed, then apply:
alembic upgrade head
```

#### Migration Best Practices

1. **Always review auto-generated migrations** before applying
2. **Test migrations on development database first**
3. **Backup production database before major migrations**
4. **Use descriptive migration messages**
5. **Never edit applied migrations** (create new one instead)
6. **Keep migrations small and focused** (one change per migration)

### 7.3 Database Utilities

#### Seed Mock Data

```powershell
# Dynamic mock data (large volumes for testing)
python -m app.db.seed_mock <num_transactions> <num_emails> <hours_spread> [clear_existing]

# Examples:
python -m app.db.seed_mock 100 80 48          # 100 txns, 80 emails, 48 hours
python -m app.db.seed_mock 50 40 72 true      # Clear existing data first

# Static test fixtures (small dataset for unit tests)
python -m tests.seed_fixtures
```

#### Clear All Data

```powershell
# Using seed_mock with 0 records and clear flag
python -m app.db.seed_mock 0 0 0 true

# Or using wipe.py (nuclear option - resets database)
python wipe.py
```

#### Database Backup (PostgreSQL)

```powershell
# Backup
pg_dump -U bara_user -d bara_prod > backup_2025-01-16.sql

# Restore
psql -U bara_user -d bara_prod < backup_2025-01-16.sql
```

#### Database Inspection (SQLite)

```powershell
# Open SQLite CLI
sqlite3 bara_dev.db

# In SQLite shell:
.tables                    # List all tables
.schema emails             # Show table structure
SELECT COUNT(*) FROM emails;
SELECT * FROM matches LIMIT 10;
.exit
```

### 7.4 Database Performance Tips

**Indexing (already configured):**

- `emails.message_id` (unique index)
- `transactions.source_id` (unique index)
- `matches.email_id` (foreign key index)
- `matches.transaction_id` (foreign key index)
- `emails.matched`, `transactions.matched` (query optimization)

**Connection pooling (PostgreSQL):**

```python
# Configured in app/db/base.py
create_async_engine(
    DATABASE_URL,
    pool_size=20,        # Maximum connections
    max_overflow=10,     # Extra connections when needed
    pool_pre_ping=True,  # Check connection health
)
```

**Query optimization:**

```python
# Good: Use filters efficiently
unmatched = await uow.emails.filter(matched=False)

# Better: Add limit
recent_unmatched = await uow.emails.filter(
    matched=False,
    created_at__gte=datetime.now() - timedelta(days=7)
).limit(100)

# Best: Use pagination
page_1 = await uow.emails.paginate(page=1, page_size=50)
```

---

- How to run BARA in automation mode
- Manual commands and workflows
- Telex A2A integration guide
- Complete automation flow (A-Z technical walkthrough)
- Troubleshooting and common errors
- Production deployment guide
- API reference
- Advanced features

---

**Document Information:**

- **Part:** 1 of 2
- **Version:** 3.0
- **Last Updated:** January 16, 2025
- **Next:** [BARA Usage Guide - Part 2](./BARA-Usage-Guide-Part-2.md)

---

## 8. Running BARA

### 1.1 Starting the Server

**Development Mode (Hot Reload):**

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start server with hot reload
./run_server.bat

# Alternative: Direct uvicorn command
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Using uv (auto-activates venv)
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Production Mode (No Hot Reload):**

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Start server (production settings)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# With more workers for high traffic
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 8 --worker-class uvicorn.workers.UvicornWorker
```

**Docker Deployment:**

```powershell
# Build Docker image
docker build -t bara:latest -f docker/Dockerfile .

# Run container
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name bara-production \
  bara:latest
```

### 1.2 Server Startup Sequence

When BARA starts, you'll see this startup sequence:

```
======================================================================
🚀 Starting Bank Alert Reconciliation Agent (BARA)...
Environment: development
Database: bara_dev.db
======================================================================
📧 Initializing email fetcher...
✓ Email fetcher initialized (not auto-started)
🤖 Initializing automation service...
✓ Automation service initialized (not auto-started)
   Use POST /automation/start or A2A 'start automation' command
======================================================================
✓ BARA startup complete - Ready to process requests
======================================================================
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using StatReload
INFO:     Started server process [67890]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**What this means:**

1. **Environment loaded:** Configuration from `.env` is active
2. **Database connected:** Ready to accept queries
3. **Email fetcher initialized:** But NOT running automatically
4. **Automation service initialized:** But NOT running automatically
5. **Server ready:** Accepting HTTP requests on port 8000

**IMPORTANT:** BARA does **NOT** start automation automatically. You must explicitly start it via:

- REST API: `POST /automation/start`
- Telex A2A: `"start automation"` command
- Manual trigger after startup

### 1.3 Accessing the API

Once the server is running:

**Interactive API Documentation (Swagger UI):**

```
http://localhost:8000/docs
```

**Alternative API Documentation (ReDoc):**

```
http://localhost:8000/redoc
```

**Health Check Endpoint:**

```
http://localhost:8000/healthz
```

**OpenAPI JSON Schema:**

```
http://localhost:8000/openapi.json
```

### 1.4 Verifying Installation

**Quick health check:**

```powershell
# Using curl (PowerShell)
curl http://localhost:8000/healthz

# Expected response:
# {"status":"healthy","environment":"development","version":"3.0.0"}
```

**Using browser:**
Open `http://localhost:8000/docs` and you should see the interactive API documentation.

**Running basic test:**

```powershell
# Test email fetch endpoint (mock data in dev mode)
curl -X POST http://localhost:8000/emails/fetch

# Expected response (dev mode with mock data):
# {
#   "status": "success",
#   "run_id": "mock-abc123",
#   "emails_fetched": 10,
#   "emails_processed": 10,
#   "emails_stored": 10,
#   "error": null
# }
```

### 1.5 Stopping the Server

**Graceful Shutdown:**

Press `Ctrl+C` in the terminal where the server is running.

**You'll see:**

```
======================================================================
🛑 Shutting down Bank Alert Reconciliation Agent...
======================================================================
Stopping automation service...
✓ Automation service stopped
Stopping email fetcher...
✓ Email fetcher stopped
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [67890]
```

**Force Stop (if graceful shutdown hangs):**

```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID)
taskkill /PID <PID> /F
```

---

## 9. Manual Operations via REST API

BARA provides **11 REST API endpoints** for direct control. All endpoints return JSON responses.

### 2.1 Email Operations

#### Fetch Emails Manually

**Endpoint:** `POST /emails/fetch`

**Description:** Trigger a one-time email fetch from IMAP server (or generate mock data in dev mode).

**Request:**

```bash
curl -X POST http://localhost:8000/emails/fetch
```

**Response (success):**

```json
{
  "status": "success",
  "run_id": "fetch-abc123",
  "emails_fetched": 25,
  "emails_processed": 25,
  "emails_stored": 23,
  "error": null
}
```

**Response (dev mode with mock data):**

```json
{
  "status": "success",
  "run_id": "mock-abc123",
  "emails_fetched": 10,
  "emails_processed": 10,
  "emails_stored": 10,
  "error": null,
  "warning": "⚠️ Mock data generated for development/testing"
}
```

**Response (error):**

```json
{
  "status": "error",
  "run_id": null,
  "emails_fetched": 0,
  "emails_processed": 0,
  "emails_stored": 0,
  "error": "IMAP connection failed: [Errno -2] Name or service not known"
}
```

#### Get Email Fetcher Status

**Endpoint:** `GET /emails/status`

**Description:** View email fetcher metrics and status.

**Request:**

```bash
curl http://localhost:8000/emails/status
```

**Response:**

```json
{
  "running": false,
  "enabled": true,
  "poll_interval_minutes": 15,
  "llm_enabled": true,
  "last_run": {
    "timestamp": "2025-01-16T10:30:00Z",
    "emails_fetched": 25,
    "emails_stored": 23,
    "success": true
  },
  "aggregate_metrics": {
    "total_runs": 48,
    "total_emails_fetched": 1203,
    "total_emails_stored": 1185,
    "success_rate": 98.5,
    "average_processing_time": 3.2
  }
}
```

#### List Emails

**Endpoint:** `GET /emails/?skip=0&limit=50`

**Description:** Retrieve stored emails with pagination.

**Request:**

```bash
curl "http://localhost:8000/emails/?skip=0&limit=10"
```

**Response:**

```json
{
  "total": 1185,
  "items": [
    {
      "id": 1,
      "message_id": "<abc123@mail.gtbank.com>",
      "from_address": "alerts@gtbank.com",
      "subject": "GTBank Alert: Credit Transaction",
      "amount": 50000.0,
      "currency": "NGN",
      "reference": "GTB/CR/2025/001",
      "description": "Transfer from John Doe",
      "timestamp": "2025-01-16T08:15:00Z",
      "bank_code": "GTB",
      "bank_name": "Guaranty Trust Bank",
      "matched": true,
      "created_at": "2025-01-16T08:16:05Z"
    }
    // ... 9 more emails
  ]
}
```

### 2.2 Transaction Operations

#### Poll Transactions Manually

**Endpoint:** `POST /transactions/poll`

**Description:** Trigger a one-time transaction poll from API (or generate mock data in dev mode).

**Request:**

```bash
curl -X POST http://localhost:8000/transactions/poll
```

**Response (success):**

```json
{
  "run_id": "poll-xyz789",
  "status": "success",
  "message": "Poll completed successfully",
  "details": {
    "transactions_fetched": 45,
    "transactions_stored": 43,
    "duplicates_skipped": 2,
    "source": "BankAPI v2",
    "duration_seconds": 2.3
  }
}
```

**Response (dev mode with mock data):**

```json
{
  "run_id": "mock-xyz789",
  "status": "success",
  "message": "Poll completed successfully (MOCK DATA)",
  "details": {
    "transactions_fetched": 100,
    "transactions_stored": 100,
    "data_source": "mock",
    "warning": "⚠️ Mock data generated for development/testing"
  }
}
```

#### Get Transaction Poller Status

**Endpoint:** `GET /transactions/poller/status`

**Description:** View transaction poller metrics and circuit breaker status.

**Request:**

```bash
curl http://localhost:8000/transactions/poller/status
```

**Response:**

```json
{
  "running": false,
  "enabled": true,
  "last_poll_time": "2025-01-16T10:35:00Z",
  "circuit_breaker": {
    "state": "closed",
    "failure_count": 0,
    "last_failure_time": null
  },
  "current_run": null,
  "last_run": {
    "run_id": "poll-xyz789",
    "status": "success",
    "transactions_fetched": 45,
    "duration_seconds": 2.3
  },
  "metrics_24h": {
    "total_runs": 96,
    "successful_runs": 95,
    "failed_runs": 1,
    "total_transactions": 4320,
    "average_duration": 2.1
  },
  "success_rate_24h": 98.96,
  "config": {
    "poll_interval_minutes": 15,
    "batch_size": 100
  }
}
```

#### List Transactions

**Endpoint:** `GET /transactions/?skip=0&limit=50`

**Description:** Retrieve stored transactions with pagination.

**Request:**

```bash
curl "http://localhost:8000/transactions/?skip=0&limit=10"
```

**Response:**

```json
{
  "total": 4320,
  "items": [
    {
      "id": 1,
      "source_id": "TXN-2025-001",
      "source_name": "BankAPI v2",
      "amount": 50000.0,
      "currency": "NGN",
      "reference": "GTB/CR/2025/001",
      "description": "Inward Transfer",
      "timestamp": "2025-01-16T08:15:00Z",
      "bank_code": "GTB",
      "bank_name": "Guaranty Trust Bank",
      "matched": true,
      "metadata": {
        "account_number": "0123456789",
        "transaction_type": "credit"
      },
      "created_at": "2025-01-16T08:16:10Z"
    }
    // ... 9 more transactions
  ]
}
```

### 2.3 Matching Operations

#### Run Matching Manually

**Endpoint:** `POST /matching/match?limit=50`

**Description:** Run the matching engine on unmatched emails.

**Request:**

```bash
# Match all unmatched emails
curl -X POST http://localhost:8000/matching/match

# Match only 50 emails
curl -X POST "http://localhost:8000/matching/match?limit=50"
```

**Response:**

```json
{
  "total_emails": 50,
  "total_matched": 42,
  "total_needs_review": 5,
  "total_rejected": 2,
  "total_no_candidates": 1,
  "average_confidence": 0.87,
  "matches": [
    {
      "email_id": 1,
      "transaction_id": 1,
      "confidence_score": 0.98,
      "rule_scores": {
        "exact_amount": 1.0,
        "exact_reference": 1.0,
        "fuzzy_reference": 0.95,
        "timestamp_proximity": 0.9,
        "fuzzy_description": 0.85,
        "same_currency": 1.0,
        "same_bank": 1.0
      },
      "status": "auto_matched"
    }
    // ... 41 more matches
  ]
}
```

#### List Matches

**Endpoint:** `GET /matches/?skip=0&limit=50`

**Description:** Retrieve stored matches with pagination.

**Request:**

```bash
curl "http://localhost:8000/matches/?skip=0&limit=10"
```

**Response:**

```json
{
  "total": 1150,
  "items": [
    {
      "id": 1,
      "email_id": 1,
      "transaction_id": 1,
      "confidence_score": 0.98,
      "rule_scores": {
        "exact_amount": 1.0,
        "exact_reference": 1.0,
        "fuzzy_reference": 0.95,
        "timestamp_proximity": 0.9,
        "fuzzy_description": 0.85,
        "same_currency": 1.0,
        "same_bank": 1.0
      },
      "created_at": "2025-01-16T08:16:15Z",
      "email": {
        "id": 1,
        "amount": 50000.0,
        "reference": "GTB/CR/2025/001"
      },
      "transaction": {
        "id": 1,
        "amount": 50000.0,
        "reference": "GTB/CR/2025/001"
      }
    }
    // ... 9 more matches
  ]
}
```

#### Get Match by ID

**Endpoint:** `GET /matches/{match_id}`

**Description:** Retrieve detailed information about a specific match.

**Request:**

```bash
curl http://localhost:8000/matches/1
```

**Response:**

```json
{
  "id": 1,
  "email_id": 1,
  "transaction_id": 1,
  "confidence_score": 0.98,
  "rule_scores": {
    "exact_amount": 1.0,
    "exact_reference": 1.0,
    "fuzzy_reference": 0.95,
    "timestamp_proximity": 0.9,
    "fuzzy_description": 0.85,
    "same_currency": 1.0,
    "same_bank": 1.0
  },
  "created_at": "2025-01-16T08:16:15Z",
  "email": {
    "id": 1,
    "message_id": "<abc123@mail.gtbank.com>",
    "from_address": "alerts@gtbank.com",
    "amount": 50000.0,
    "currency": "NGN",
    "reference": "GTB/CR/2025/001",
    "timestamp": "2025-01-16T08:15:00Z"
  },
  "transaction": {
    "id": 1,
    "source_id": "TXN-2025-001",
    "amount": 50000.0,
    "currency": "NGN",
    "reference": "GTB/CR/2025/001",
    "timestamp": "2025-01-16T08:15:00Z"
  }
}
```

### 2.4 Automation Operations

#### Start Automation

**Endpoint:** `POST /automation/start?interval_seconds=900`

**Description:** Start the unified automation service (fetch → poll → match cycles).

**Request:**

```bash
# Start with default interval (900 seconds = 15 minutes)
curl -X POST http://localhost:8000/automation/start

# Start with custom interval (5 minutes)
curl -X POST "http://localhost:8000/automation/start?interval_seconds=300"
```

**Response:**

```json
{
  "success": true,
  "message": "Automation started (interval: 900s)",
  "running": true,
  "interval_seconds": 900
}
```

#### Stop Automation

**Endpoint:** `POST /automation/stop`

**Description:** Stop the automation service.

**Request:**

```bash
curl -X POST http://localhost:8000/automation/stop
```

**Response:**

```json
{
  "success": true,
  "message": "Automation stopped",
  "running": false,
  "total_cycles": 48,
  "successful_cycles": 47,
  "failed_cycles": 1
}
```

#### Get Automation Status

**Endpoint:** `GET /automation/status`

**Description:** View current automation status and metrics.

**Request:**

```bash
curl http://localhost:8000/automation/status
```

**Response:**

```json
{
  "running": true,
  "interval_seconds": 900,
  "total_cycles": 48,
  "successful_cycles": 47,
  "failed_cycles": 1,
  "last_run": "2025-01-16T10:35:00Z",
  "last_error": null,
  "success_rate": 97.92
}
```

### 2.5 Health & System Operations

#### Basic Health Check

**Endpoint:** `GET /`

**Description:** Simple liveness check.

**Request:**

```bash
curl http://localhost:8000/
```

**Response:**

```json
{
  "status": "ok",
  "message": "BARA is running"
}
```

#### Detailed Health Check

**Endpoint:** `GET /healthz`

**Description:** Detailed system health information.

**Request:**

```bash
curl http://localhost:8000/healthz
```

**Response:**

```json
{
  "status": "healthy",
  "environment": "development",
  "version": "3.0.0",
  "database": "connected",
  "services": {
    "email_fetcher": "initialized",
    "automation": "running"
  }
}
```

---

## 10. Automation Mode

### 3.1 What is Automation Mode?

Automation mode runs a **continuous reconciliation cycle** at regular intervals:

1. **Fetch emails** from IMAP server
2. **Poll transactions** from API
3. **Run matching engine** on new data
4. **Sleep** for configured interval
5. **Repeat**

**Benefits:**

- Hands-free operation
- Continuous reconciliation
- Automatic error recovery
- Performance metrics tracking

**Default interval:** 15 minutes (900 seconds)

### 3.2 Starting Automation

**Via REST API:**

```bash
# Start with default interval (15 minutes)
curl -X POST http://localhost:8000/automation/start

# Start with 5-minute interval
curl -X POST "http://localhost:8000/automation/start?interval_seconds=300"

# Start with 1-hour interval
curl -X POST "http://localhost:8000/automation/start?interval_seconds=3600"
```

**Via Python (for scripts):**

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/automation/start",
        params={"interval_seconds": 600}  # 10 minutes
    )
    print(response.json())
```

**Via Telex A2A (see Part 3):**

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "parts": [{ "text": "start automation" }]
    }
  }
}
```

### 3.3 Monitoring Automation

**Check status:**

```bash
curl http://localhost:8000/automation/status
```

**Response:**

```json
{
  "running": true,
  "interval_seconds": 900,
  "total_cycles": 12,
  "successful_cycles": 12,
  "failed_cycles": 0,
  "last_run": "2025-01-16T11:45:00Z",
  "last_error": null,
  "success_rate": 100.0
}
```

**Server logs (real-time monitoring):**

```
INFO: automation.cycle_start cycle=13 timestamp=2025-01-16T12:00:00Z
INFO: automation.cycle.step_1.fetch_emails
INFO: automation.cycle.step_1.success emails_stored=8
INFO: automation.cycle.step_2.poll_transactions
INFO: automation.cycle.step_2.success status=success
INFO: automation.cycle.step_3.match
INFO: automation.cycle.step_3.success matched=7
INFO: automation.cycle_complete cycle=13 duration_seconds=5.2
```

### 3.4 Stopping Automation

**Via REST API:**

```bash
curl -X POST http://localhost:8000/automation/stop
```

**Response:**

```json
{
  "success": true,
  "message": "Automation stopped",
  "running": false,
  "total_cycles": 13,
  "successful_cycles": 13,
  "failed_cycles": 0
}
```

**Via Telex A2A:**

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "stop automation" }]
    }
  }
}
```

### 3.5 Automation Error Handling

**BARA handles errors gracefully:**

1. **Email fetch fails** → Logs error, continues to transaction polling
2. **Transaction poll fails** → Logs error, continues to matching
3. **Matching fails** → Logs error, continues to next cycle
4. **Critical error** → Logs error, waits for interval, retries

**Error recovery features:**

- Circuit breaker prevents API overload (transaction polling)
- Exponential backoff on retry (transaction polling)
- Error logging for debugging
- Success rate tracking
- Continues running despite individual failures

**Example error log:**

```
ERROR: automation.cycle.step_2.error error='Circuit breaker open'
INFO: automation.cycle.step_3.match
INFO: automation.cycle.step_3.success matched=5
INFO: automation.cycle_complete cycle=14 duration_seconds=3.1
```

**Cycle marked as partial success** (2 of 3 steps succeeded)

### 3.6 Recommended Intervals

| Use Case                | Interval   | Seconds | Reasoning                           |
| ----------------------- | ---------- | ------- | ----------------------------------- |
| **High-volume trading** | 5 minutes  | 300     | Near real-time reconciliation       |
| **Standard operations** | 15 minutes | 900     | Balance between timeliness and load |
| **Low-volume business** | 30 minutes | 1800    | Sufficient for daily operations     |
| **Batch processing**    | 1 hour     | 3600    | Scheduled batch reconciliation      |
| **End-of-day only**     | 24 hours   | 86400   | Once-daily reconciliation           |

**Factors to consider:**

- Email volume (more emails = shorter interval)
- Transaction frequency (high frequency = shorter interval)
- Server resources (shorter interval = more CPU/memory usage)
- IMAP server limits (check rate limits)
- API rate limits (transaction polling)

---

## 11. Using the Web Interface

### 4.1 Swagger UI (Interactive API Docs)

**Access:** `http://localhost:8000/docs`

**Features:**

- **Try it out:** Execute API calls directly from browser
- **Request/response examples:** See sample data
- **Authentication:** Test with API keys (future)
- **Schema explorer:** View all models and types

**How to use:**

1. Open `http://localhost:8000/docs` in browser
2. Expand any endpoint (e.g., `POST /emails/fetch`)
3. Click **"Try it out"** button
4. Modify parameters if needed
5. Click **"Execute"**
6. View response below

**Example walkthrough - Fetch emails:**

1. Navigate to `/emails/fetch` endpoint
2. Click "Try it out"
3. Click "Execute" (no parameters needed)
4. See response:
   ```json
   {
     "status": "success",
     "emails_stored": 10
   }
   ```

### 4.2 ReDoc (Alternative Documentation)

**Access:** `http://localhost:8000/redoc`

**Features:**

- **Clean layout:** Better for reading documentation
- **Search:** Find endpoints quickly
- **Code samples:** Multiple language examples
- **Print-friendly:** Export to PDF

**Better for:**

- Reading API documentation
- Sharing with team members
- Understanding data models
- Learning the API structure

### 4.3 Health Dashboard (Custom - Future Enhancement)

Currently BARA uses JSON endpoints for health checks. A future enhancement would be a web-based dashboard showing:

- Real-time automation status
- Recent matches visualization
- Success rate graphs
- Error logs
- Configuration settings

**Current workaround:** Use tools like:

- **Postman** (import collection from `docs/BARA-Telex-Integration.postman_collection.json`)
- **Insomnia** (REST client)
- **Thunder Client** (VS Code extension)

---

## 12. Health Monitoring

### 5.1 Monitoring Checklist

**Daily checks:**

- [ ] Server is running (`GET /healthz`)
- [ ] Automation is running (`GET /automation/status`)
- [ ] Recent cycles succeeded (check `success_rate`)
- [ ] No critical errors in logs

**Weekly checks:**

- [ ] Database size is manageable
- [ ] Success rate > 95%
- [ ] Email fetcher success rate > 95%
- [ ] Transaction poller success rate > 95%
- [ ] No circuit breaker trips

**Monthly checks:**

- [ ] Review unmatched emails/transactions
- [ ] Audit match confidence scores
- [ ] Update bank mappings if needed
- [ ] Review and archive old data

### 5.2 Key Metrics to Track

#### Automation Metrics

**Endpoint:** `GET /automation/status`

**Key metrics:**

- `success_rate`: Should be > 95%
- `failed_cycles`: Should be < 5% of total
- `last_error`: Should be null or old timestamp
- `running`: Should be true in production

#### Email Fetcher Metrics

**Endpoint:** `GET /emails/status`

**Key metrics:**

- `aggregate_metrics.success_rate`: Should be > 95%
- `aggregate_metrics.total_emails_fetched`: Increasing over time
- `last_run.success`: Should be true

#### Transaction Poller Metrics

**Endpoint:** `GET /transactions/poller/status`

**Key metrics:**

- `success_rate_24h`: Should be > 95%
- `circuit_breaker.state`: Should be "closed" (not "open")
- `metrics_24h.failed_runs`: Should be low

#### Matching Metrics

**Endpoint:** `POST /matching/match` (run manually to check)

**Key metrics:**

- `average_confidence`: Should be > 0.75
- `total_matched / total_emails`: Match rate > 80%
- `total_rejected`: Should be low

### 5.3 Log Monitoring

**Log locations:**

- **Console output:** Standard output (stdout)
- **Structured logs:** JSON format via structlog

**Key log patterns to watch:**

**Successful operations:**

```
INFO: automation.cycle_complete cycle=15 duration_seconds=4.2
INFO: email.fetch.success emails_stored=12
INFO: transaction.poll.success transactions_stored=45
INFO: matching.complete matched=35 total=40
```

**Warnings (investigate but not critical):**

```
WARNING: email.parse.llm_fallback message_id=<abc123>
WARNING: matching.low_confidence email_id=5 score=0.65
WARNING: circuit_breaker.warning failures=3 threshold=5
```

**Errors (require attention):**

```
ERROR: email.fetch.error error='IMAP connection timeout'
ERROR: transaction.poll.error error='API rate limit exceeded'
ERROR: matching.error error='Database connection lost'
ERROR: automation.cycle_failed cycle=16 error='...'
```

**Critical (immediate action required):**

```
CRITICAL: circuit_breaker.open reason='Too many failures'
CRITICAL: database.connection_lost retries_exhausted=true
CRITICAL: automation.stopped reason='Unrecoverable error'
```

### 5.4 Alerting Recommendations

**Set up alerts for:**

1. **Automation stopped unexpectedly**

   - Monitor: `GET /automation/status` → `running: false`
   - Alert: Email/SMS/Slack notification

2. **Success rate drops below 90%**

   - Monitor: `success_rate` field in status endpoints
   - Alert: Daily summary

3. **Circuit breaker opens**

   - Monitor: `/transactions/poller/status` → `circuit_breaker.state: "open"`
   - Alert: Immediate notification

4. **Database errors**

   - Monitor: Log files for "database" errors
   - Alert: Immediate notification

5. **High volume of unmatched items**
   - Monitor: `GET /matches/` vs `GET /emails/` counts
   - Alert: Weekly summary if > 20% unmatched

**Tools for monitoring:**

- **Prometheus + Grafana:** Metrics dashboard (requires custom exporter)
- **Datadog:** Application performance monitoring
- **New Relic:** Full-stack monitoring
- **Sentry:** Error tracking and alerting
- **PagerDuty:** Incident management

### 5.5 Performance Benchmarks

**Expected performance (typical production environment):**

| Operation             | Expected Duration | Warning Threshold | Error Threshold |
| --------------------- | ----------------- | ----------------- | --------------- |
| Email fetch cycle     | 2-5 seconds       | > 10 seconds      | > 30 seconds    |
| Transaction poll      | 1-3 seconds       | > 5 seconds       | > 15 seconds    |
| Matching (100 emails) | 3-8 seconds       | > 15 seconds      | > 30 seconds    |
| Full automation cycle | 5-15 seconds      | > 30 seconds      | > 60 seconds    |

**Database query performance:**

| Query                  | Expected Duration | Warning Threshold |
| ---------------------- | ----------------- | ----------------- |
| List emails (50)       | < 100ms           | > 500ms           |
| List transactions (50) | < 100ms           | > 500ms           |
| List matches (50)      | < 200ms           | > 1000ms          |
| Get match by ID        | < 50ms            | > 200ms           |

**If performance degrades:**

1. Check database indexes
2. Review query complexity
3. Consider database optimization (VACUUM for PostgreSQL)
4. Increase server resources
5. Enable database connection pooling

---

**Continue to:**

- [Part 3: Telex Integration & Commands](./BARA-Usage-Guide-Part-3.md)
- [Part 4: Complete Automation Flow & Troubleshooting](./BARA-Usage-Guide-Part-4.md)

**Previous:**

- [Part 1: Setup, Architecture & Configuration](./BARA-Usage-Guide-Part-1.md)

---

**Document Information:**

- **Part:** 2 of 4
- **Version:** 3.0
- **Last Updated:** January 16, 2025

---

## 13. Telex A2A Integration Overview

### 1.1 What is Telex?

**Telex** is an Agent-to-Agent (A2A) communication protocol that enables AI agents to interact with external services using JSON-RPC 2.0. BARA implements the Telex protocol, allowing users to control the system through natural language commands.

### 1.2 Why Use Telex Instead of REST API?

**Advantages of Telex A2A:**

✅ **Natural language:** Send commands like `"match now"` instead of crafting HTTP requests  
✅ **Structured responses:** Get rich responses with artifacts (JSON, tables, charts)  
✅ **Conversational:** Ask follow-up questions and maintain context  
✅ **Agent-friendly:** Designed for AI agent integration  
✅ **Protocol-standard:** JSON-RPC 2.0 specification

**When to use Telex:**

- Integrating with AI assistants (ChatGPT, Claude, etc.)
- Building conversational interfaces
- Automating workflows with natural language
- Rapid prototyping without API documentation

**When to use REST API:**

- Programmatic integration
- Automated scripts
- Performance-critical operations
- Direct database queries

### 1.3 BARA's A2A Capabilities

**BARA implements:**

- ✅ JSON-RPC 2.0 protocol (full compliance)
- ✅ Natural language command interpretation (12 commands)
- ✅ Artifact formatting (text, JSON, tables, charts)
- ✅ Status method (health check)
- ✅ Message/send method (command execution)
- ✅ Execute method (structured commands - future)

**Endpoint:** `POST /a2a/agent/bara`

**Supported JSON-RPC methods:**

1. `status` - Health check with system metrics
2. `message/send` - Execute natural language command
3. `execute` - Execute structured command (future enhancement)

---

## 14. JSON-RPC 2.0 Protocol

### 2.1 Protocol Basics

**JSON-RPC 2.0** is a stateless, light-weight remote procedure call (RPC) protocol.

**Request format:**

```json
{
  "jsonrpc": "2.0",
  "id": "unique-request-id",
  "method": "method_name",
  "params": {
    /* optional parameters */
  }
}
```

**Response format (success):**

```json
{
  "jsonrpc": "2.0",
  "id": "unique-request-id",
  "result": {
    /* method result */
  }
}
```

**Response format (error):**

```json
{
  "jsonrpc": "2.0",
  "id": "unique-request-id",
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": {
      /* optional error details */
    }
  }
}
```

### 2.2 Status Method

**Purpose:** Health check with system metrics

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "status",
  "params": {}
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "status": "healthy",
    "agent": "BARA",
    "version": "3.0.0",
    "environment": "production",
    "metrics": {
      "automation": {
        "running": true,
        "success_rate": 98.5,
        "total_cycles": 144
      },
      "emails": {
        "total": 3456,
        "matched": 3201,
        "unmatched": 255
      },
      "transactions": {
        "total": 3500,
        "matched": 3201,
        "unmatched": 299
      },
      "matches": {
        "total": 3201,
        "average_confidence": 0.89
      }
    },
    "timestamp": "2025-01-16T12:00:00Z"
  }
}
```

### 2.3 Message/Send Method

**Purpose:** Execute natural language command

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "message/send",
  "params": {
    "message": {
      "kind": "message",
      "parts": [
        {
          "text": "match 50 emails"
        }
      ]
    }
  }
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "result": {
    "message": {
      "kind": "message",
      "parts": [
        {
          "text": "✅ Matching complete!\n\n📊 **Results:**\n  • Total processed: 50\n  • Auto-matched: 42\n  • Needs review: 5\n  • Rejected: 2\n  • No candidates: 1\n  • Avg confidence: 87%"
        },
        {
          "kind": "artifact",
          "identifier": "match-results",
          "type": "application/json",
          "title": "Match Results",
          "content": "{\"total_emails\":50,\"total_matched\":42,\"matches\":[...]}"
        }
      ]
    }
  }
}
```

### 2.4 Error Responses

**Invalid method:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-003",
  "error": {
    "code": -32601,
    "message": "Method not found",
    "data": {
      "method": "invalid_method",
      "available_methods": ["status", "message/send", "execute"]
    }
  }
}
```

**Invalid command:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-004",
  "result": {
    "message": {
      "kind": "message",
      "parts": [
        {
          "text": "❓ Command not recognized: 'do something weird'\n\nAvailable commands:\n  • match now\n  • show summary\n  • start automation\n  ... (see 'help' for full list)"
        }
      ]
    }
  }
}
```

**Note:** Unknown commands return a successful response with helpful error message (not JSON-RPC error).

---

## 15. Natural Language Commands

### 3.1 Command Interpreter Architecture

BARA uses a **zero-LLM, deterministic pattern matching** system for command interpretation:

1. **User sends natural language message** (e.g., "match 50 emails")
2. **Command interpreter scans registered patterns** (compiled regex)
3. **Best matching command is selected** (highest confidence score)
4. **Parameters are extracted** from the message (e.g., limit=50)
5. **Command handler is executed** with extracted parameters
6. **Response is formatted** with artifacts

**Benefits:**

- ⚡ **Fast:** < 1ms pattern matching (no LLM latency)
- 🎯 **Deterministic:** Same input always produces same output
- 💰 **Cost-effective:** No API calls to LLM providers
- 🔒 **Reliable:** No hallucinations or unexpected behavior

### 3.2 Command Structure

**Basic command:**

```
"match now"
```

**Command with parameters:**

```
"match 100 emails"
"show summary for last 30 days"
"start automation with 5 minute interval"
```

**Alternative phrasings (patterns):**

```
"match now" = "run reconciliation" = "reconcile emails" = "process alerts"
```

### 3.3 Parameter Extraction

**Supported parameter types:**

| Parameter Type  | Example                       | Extracted Value |
| --------------- | ----------------------------- | --------------- |
| **Integer**     | "match 50 emails"             | `limit: 50`     |
| **Time period** | "show summary for 30 days"    | `days: 30`      |
| **Interval**    | "start automation with 5 min" | `interval: 300` |
| **Boolean**     | "rematch all emails"          | `rematch: true` |

**Extraction patterns:**

```python
# Integer extraction
r"(\d+)\s+(emails?|items?|records?)"  # "50 emails" → 50

# Time period extraction
r"(last\s+)?(\d+)\s+(days?|hours?)"   # "last 30 days" → 30

# Interval extraction
r"(\d+)\s+(min|minutes?|sec|seconds?|hour|hours?)"  # "5 min" → 300

# Boolean flags
r"\b(re-?match|force)\b"              # "rematch all" → true
```

---

## 16. Complete Command Reference

BARA supports **12 core commands** organized into 4 categories.

### 4.1 Data Operations (5 commands)

#### Command 1: `match_now`

**Purpose:** Run reconciliation matching immediately

**Patterns:**

- `"match now"`
- `"run reconciliation"`
- `"reconcile emails"`
- `"start matching"`
- `"process 50 alerts"`

**Parameters:**

- `limit` (int, optional): Number of emails to process
- `rematch` (bool, optional): Force re-matching of already matched emails

**Examples:**

```json
// Match all unmatched emails
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "match now"}]
    }
  }
}

// Match only 50 emails
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "match 50 emails"}]
    }
  }
}

// Force re-match all emails
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "rematch all emails"}]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "✅ Matching complete!\n\n📊 **Results:**\n  • Total processed: 50\n  • Auto-matched: 42\n  • Needs review: 5\n  • Rejected: 2\n  • No candidates: 1\n  • Avg confidence: 87%"
        },
        {
          "kind": "artifact",
          "identifier": "match-results",
          "type": "application/json",
          "title": "Match Results",
          "content": "{...detailed match data...}"
        }
      ]
    }
  }
}
```

---

#### Command 2: `fetch_emails_now`

**Purpose:** Manually trigger email fetching from IMAP

**Patterns:**

- `"fetch emails now"`
- `"get new alerts"`
- `"check for emails"`
- `"retrieve emails"`

**Parameters:** None

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "fetch emails now" }]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "📧 **Email Fetch Complete**\n\n✓ Fetched: 25 emails\n✓ Processed: 25 emails\n✓ Stored: 23 new emails\n✓ Duration: 3.2 seconds"
        }
      ]
    }
  }
}
```

---

#### Command 3: `fetch_transactions_now`

**Purpose:** Manually trigger transaction polling from API

**Patterns:**

- `"fetch transactions now"`
- `"poll transactions"`
- `"get new transactions"`
- `"retrieve transactions"`

**Parameters:** None

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "poll transactions" }]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "💳 **Transaction Poll Complete**\n\n✓ Fetched: 45 transactions\n✓ Stored: 43 new transactions\n✓ Duplicates skipped: 2\n✓ Duration: 2.1 seconds"
        }
      ]
    }
  }
}
```

---

#### Command 4: `show_summary`

**Purpose:** Display reconciliation summary with match statistics

**Patterns:**

- `"show summary"`
- `"display stats"`
- `"how are things doing"`
- `"what's the status"`
- `"summarize last 30 days"`

**Parameters:**

- `days` (int, optional, default=7): Number of days to look back

**Examples:**

```json
// Default: last 7 days
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "show summary"}]
    }
  }
}

// Last 30 days
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "show summary for last 30 days"}]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "📊 **Reconciliation Summary** (Last 7 days)\n\n**Emails:**\n  • Total: 856\n  • Matched: 802\n  • Unmatched: 54\n\n**Transactions:**\n  • Total: 890\n\n**Match Status:**\n  • Auto-matched: 775\n  • Needs review: 27\n  • Rejected: 15\n  • No candidates: 39"
        },
        {
          "kind": "artifact",
          "identifier": "summary-stats",
          "type": "application/json",
          "title": "Summary Statistics",
          "content": "{...detailed stats...}"
        }
      ]
    }
  }
}
```

---

#### Command 5: `list_unmatched`

**Purpose:** Show unmatched emails and transactions

**Patterns:**

- `"list unmatched"`
- `"show pending items"`
- `"what's not matched"`
- `"display orphan records"`

**Parameters:**

- `limit` (int, optional, default=20): Maximum items to show

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "list unmatched" }]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "📋 **Unmatched Items**\n\n**Emails (54 total):**\n1. GTB Alert - ₦25,000 - Ref: GTB/001 - 2025-01-16\n2. Access Alert - ₦150,000 - Ref: ACC/202 - 2025-01-16\n...(showing 20 of 54)\n\n**Transactions (68 total):**\n1. API Record - ₦30,000 - Ref: TXN/501 - 2025-01-16\n2. API Record - ₦75,000 - Ref: TXN/502 - 2025-01-16\n...(showing 20 of 68)"
        },
        {
          "kind": "artifact",
          "identifier": "unmatched-list",
          "type": "application/json",
          "title": "Unmatched Items",
          "content": "{...detailed unmatched data...}"
        }
      ]
    }
  }
}
```

---

### 4.2 Automation Control (3 commands)

#### Command 6: `get_status`

**Purpose:** Get unified automation service status

**Patterns:**

- `"get status"`
- `"show automation status"`
- `"is automation running"`
- `"status check"`

**Parameters:** None

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "get status" }]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "🤖 **Automation Status**\n\n✓ Running: Yes\n✓ Interval: 900 seconds (15 minutes)\n✓ Total cycles: 144\n✓ Successful: 141 (97.9%)\n✓ Failed: 3 (2.1%)\n✓ Last run: 2025-01-16T11:45:00Z\n✓ Next run: 2025-01-16T12:00:00Z"
        }
      ]
    }
  }
}
```

---

#### Command 7: `start_automation`

**Purpose:** Start unified automation service

**Patterns:**

- `"start automation"`
- `"enable automation"`
- `"turn on automation"`
- `"begin automated cycles"`
- `"start automation with 5 minute interval"`

**Parameters:**

- `interval_seconds` (int, optional, default=900): Automation cycle interval

**Examples:**

```json
// Default interval (15 minutes)
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "start automation"}]
    }
  }
}

// Custom interval (5 minutes)
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{"text": "start automation with 5 minute interval"}]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "✅ Automation started!\n\n⏱️ Interval: 900 seconds (15 minutes)\n📊 Automation will run continuously:\n  1. Fetch emails from IMAP\n  2. Poll transactions from API\n  3. Run matching engine\n  4. Sleep for 15 minutes\n  5. Repeat\n\nUse 'get status' to monitor progress."
        }
      ]
    }
  }
}
```

---

#### Command 8: `stop_automation`

**Purpose:** Stop unified automation service

**Patterns:**

- `"stop automation"`
- `"disable automation"`
- `"turn off automation"`
- `"halt automated cycles"`

**Parameters:** None

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "stop automation" }]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "🛑 Automation stopped!\n\n📊 **Final Statistics:**\n  • Total cycles: 144\n  • Successful: 141 (97.9%)\n  • Failed: 3 (2.1%)\n  • Total runtime: 36 hours\n\nAutomation can be restarted with 'start automation' command."
        }
      ]
    }
  }
}
```

---

### 4.3 Analytics & Diagnostics (3 commands)

#### Command 9: `show_metrics`

**Purpose:** Display performance metrics

**Status:** ⚠️ Stub implementation (returns placeholder data)

**Patterns:**

- `"show metrics"`
- `"display performance stats"`
- `"how fast is the system"`

**Parameters:** None

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "show metrics" }]
    }
  }
}
```

**Response (placeholder):**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "⚠️ Metrics command is registered but returns stub data.\n\nFuture implementation will show:\n  • Average cycle duration\n  • API response times\n  • Database query performance\n  • Matching engine speed\n  • Error rates"
        }
      ]
    }
  }
}
```

---

#### Command 10: `show_logs`

**Purpose:** Show recent activity logs

**Status:** ⚠️ Stub implementation (returns placeholder data)

**Patterns:**

- `"show logs"`
- `"display recent activity"`
- `"what happened"`
- `"view history"`

**Parameters:**

- `limit` (int, optional): Number of log entries to show

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "show logs" }]
    }
  }
}
```

**Response (placeholder):**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "⚠️ Logs command is registered but returns stub data.\n\nFuture implementation will show:\n  • Recent automation cycles\n  • Email fetch operations\n  • Transaction polls\n  • Matching operations\n  • Errors and warnings"
        }
      ]
    }
  }
}
```

---

#### Command 11: `manual_match`

**Purpose:** Manually match specific email/transaction

**Status:** ⚠️ Stub implementation (returns placeholder data)

**Patterns:**

- `"manually match"`
- `"match email 123 to transaction 456"`
- `"force match item 123"`

**Parameters:**

- `email_id` (int): Email ID to match
- `transaction_id` (int): Transaction ID to match

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "match email 123 to transaction 456" }]
    }
  }
}
```

**Response (placeholder):**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "⚠️ Manual match command is registered but returns stub data.\n\nFuture implementation will:\n  • Accept email ID and transaction ID\n  • Create manual match with confidence score\n  • Mark as 'manually_matched' status\n  • Log audit trail"
        }
      ]
    }
  }
}
```

---

### 4.4 Utility (1 command)

#### Command 12: `help`

**Purpose:** Show available commands and usage

**Patterns:**

- `"help"`
- `"commands"`
- `"what can you do"`
- `"show help"`

**Parameters:** None

**Example:**

```json
{
  "method": "message/send",
  "params": {
    "message": {
      "parts": [{ "text": "help" }]
    }
  }
}
```

**Response:**

```json
{
  "result": {
    "message": {
      "parts": [
        {
          "text": "🤖 **BARA Commands**\n\n**Data Operations:**\n  • match now - Run reconciliation matching\n  • fetch emails now - Fetch new bank alerts\n  • fetch transactions now - Poll new transactions\n  • show summary - Display reconciliation stats\n  • list unmatched - Show unmatched items\n\n**Automation Control:**\n  • get status - Get automation status\n  • start automation - Start automated cycles\n  • stop automation - Stop automated cycles\n\n**Analytics:**\n  • show metrics - Display performance metrics\n  • show logs - Show recent activity\n  • manual match - Manually match items\n\n**Utility:**\n  • help - Show this help message\n\nExample: 'match 50 emails' or 'start automation'"
        }
      ]
    }
  }
}
```

---

## 17. Advanced Telex Features

### 5.1 Artifact System

**Artifacts** are structured data objects attached to responses, enabling rich visualization in Telex clients.

**Artifact types:**

| Type                | Description               | Example Use Case          |
| ------------------- | ------------------------- | ------------------------- |
| `application/json`  | JSON data                 | Match results, statistics |
| `text/plain`        | Plain text                | Logs, error messages      |
| `text/markdown`     | Markdown formatted text   | Formatted summaries       |
| `text/csv`          | CSV data                  | Exported match data       |
| `application/chart` | Chart definition (future) | Performance graphs        |

**Artifact structure:**

```json
{
  "kind": "artifact",
  "identifier": "unique-artifact-id",
  "type": "application/json",
  "title": "Human Readable Title",
  "content": "{...actual data...}"
}
```

**Example - Match results with artifact:**

```json
{
  "message": {
    "parts": [
      {
        "text": "✅ Matched 42 emails"
      },
      {
        "kind": "artifact",
        "identifier": "match-results-2025-01-16",
        "type": "application/json",
        "title": "Detailed Match Results",
        "content": "{\"total\":42,\"matches\":[{\"email_id\":1,\"transaction_id\":1,\"score\":0.98},{\"email_id\":2,\"transaction_id\":2,\"score\":0.95}]}"
      }
    ]
  }
}
```

### 5.2 Error Handling

**Command not recognized:**

```json
{
  "message": {
    "parts": [
      {
        "text": "❓ Command not recognized: 'do something weird'\n\n💡 **Did you mean:**\n  • match now\n  • show summary\n  • get status\n\nType 'help' to see all available commands."
      }
    ]
  }
}
```

**Operation failed:**

```json
{
  "message": {
    "parts": [
      {
        "text": "❌ **Error:** Failed to fetch emails\n\n🔍 **Details:**\nIMAP connection timeout after 30 seconds\n\n💡 **Suggestions:**\n  • Check IMAP server status\n  • Verify credentials in .env file\n  • Check network connectivity\n  • Try again in a few minutes"
      }
    ]
  }
}
```

### 5.3 Multi-Step Workflows

Telex enables conversational workflows:

**Step 1: Check status**

```
User: "get status"
BARA: "Automation is running. 144 cycles completed, 97.9% success rate."
```

**Step 2: View summary**

```
User: "show summary"
BARA: "856 emails, 802 matched (93.7%), 54 unmatched"
```

**Step 3: List unmatched**

```
User: "list unmatched"
BARA: "54 unmatched emails, 68 unmatched transactions"
```

**Step 4: Run matching**

```
User: "match now"
BARA: "Matched 42 of 54 emails. 12 still unmatched."
```

**Step 5: Verify improvement**

```
User: "show summary"
BARA: "856 emails, 844 matched (98.6%), 12 unmatched"
```

### 5.4 Using Telex with AI Assistants

**Example: ChatGPT integration**

1. **Configure ChatGPT action:**

   - Add BARA A2A endpoint as custom action
   - Provide OpenAPI schema (from `/openapi.json`)
   - Map natural language to JSON-RPC calls

2. **User asks ChatGPT:**

   ```
   "Check BARA reconciliation status and match any unmatched emails"
   ```

3. **ChatGPT executes:**

   ```json
   // First: Get status
   {"method": "message/send", "params": {"message": {"parts": [{"text": "get status"}]}}}

   // Then: Match emails
   {"method": "message/send", "params": {"message": {"parts": [{"text": "match now"}]}}}
   ```

4. **ChatGPT responds:**
   ```
   "I've checked BARA's status. The automation is running with 97.9% success rate.
   I also ran the matching engine, which successfully matched 42 out of 50 unmatched
   emails. The average confidence score is 87%."
   ```

### 5.5 Postman Collection

BARA includes a **Postman collection** for testing A2A integration:

**Location:** `docs/BARA-Telex-Integration.postman_collection.json`

**How to use:**

1. **Import collection:**

   - Open Postman
   - File → Import
   - Select `BARA-Telex-Integration.postman_collection.json`

2. **Set environment variables:**

   - Create new environment "BARA Dev"
   - Add variable: `base_url` = `http://localhost:8000`

3. **Test commands:**
   - Expand "BARA A2A Commands" folder
   - Select any request (e.g., "Match Now")
   - Click "Send"
   - View response

**Collection includes:**

- All 12 commands with examples
- Status method
- Error handling examples
- Parameter variations
- Expected responses

### 5.6 Custom Command Development

**To add a new command to BARA:**

**Step 1: Create handler in `app/a2a/command_handlers.py`:**

```python
async def my_custom_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Custom command description.

    Params:
        param1: Description
    """
    logger.info("handler.my_custom_command.start", params=params)

    try:
        # Your logic here
        result = await do_something(params)

        return {
            "status": "success",
            "summary": "✅ Command executed!",
            "artifacts": [...],
            "meta": {...}
        }
    except Exception as exc:
        logger.exception("handler.my_custom_command.error", error=str(exc))
        return {
            "status": "error",
            "summary": f"❌ Error: {str(exc)}",
            "artifacts": [],
            "meta": {"error": str(exc)}
        }
```

**Step 2: Register command in `app/a2a/command_interpreter.py`:**

```python
self.register_command(
    name="my_custom_command",
    patterns=[
        r"\bmy\s+custom\s+command\b",
        r"\bdo\s+custom\s+thing\b"
    ],
    handler=self.handlers.my_custom_command,
    description="Execute custom operation"
)
```

**Step 3: Update documentation:**

- Add to `docs/Telex-Commands-Reference.md`
- Update help text in command interpreter
- Add test cases to `tests/test_a2a_natural_language.py`

---

**Continue to:**

- [Part 4: Complete Automation Flow & Troubleshooting](./BARA-Usage-Guide-Part-4.md)

**Previous:**

- [Part 1: Setup, Architecture & Configuration](./BARA-Usage-Guide-Part-1.md)
- [Part 2: Running BARA & Manual Operations](./BARA-Usage-Guide-Part-2.md)

---

**Document Information:**

- **Part:** 3 of 4
- **Version:** 3.0
- **Last Updated:** January 16, 2025

---

## 18. Complete Automation Flow (Non-Technical)

This section explains **exactly what happens** when you start BARA automation, from start to finish, in plain language anyone can understand.

### 1.1 Overview: What Automation Does

When you start BARA automation (via `POST /automation/start` or the command `"start automation"`), BARA begins a **continuous loop** that:

1. **Connects to your email** and downloads new bank alert messages
2. **Connects to your banking API** and downloads new transaction records
3. **Matches emails to transactions** using intelligent rules
4. **Saves the matches** to the database with confidence scores
5. **Waits** for a configured time (default: 15 minutes)
6. **Repeats** steps 1-5 forever (until you stop it)

**Think of it like a robot assistant that:**

- Checks your email inbox every 15 minutes for bank alerts
- Checks your banking system every 15 minutes for new transactions
- Pairs them together automatically
- Never gets tired, never forgets, works 24/7

### 1.2 Step-by-Step: What Happens When You Hit "Start"

#### **Moment 0: Before Automation Starts**

You send a request to start automation:

```bash
curl -X POST http://localhost:8000/automation/start
```

Or via Telex:

```json
{
  "method": "message/send",
  "params": { "message": { "parts": [{ "text": "start automation" }] } }
}
```

**What BARA does:**

1. ✅ Checks if automation is already running (prevents duplicates)
2. ✅ Validates configuration (database connection, settings)
3. ✅ Creates a background task (async process)
4. ✅ Logs startup event with timestamp
5. ✅ Returns success message: _"Automation started (interval: 900s)"_

**Server log output:**

```
INFO: automation.started interval_seconds=900
INFO: automation.loop_started
```

---

#### **Cycle 1: First Automation Run**

Automation immediately begins its first cycle. Here's what happens in detail:

---

##### **STEP 1: Email Fetching (3-5 seconds)**

**What BARA does:**

1. **Connects to your email server** (IMAP)

   - Server: imap.gmail.com (or your configured server)
   - Credentials: From `.env` file (`IMAP_USER`, `IMAP_PASS`)
   - Protocol: Secure IMAP over SSL/TLS

2. **Searches for new messages**

   - Looks in inbox folder
   - Filters by date (only new emails since last run)
   - Searches for emails from Nigerian banks

3. **Downloads matching emails**

   - Example: 12 new emails found
   - Downloads full message (subject, body, headers)
   - Extracts unique message ID

4. **Filters emails through whitelist**

   - **Whitelist:** 118+ Nigerian bank domains (GTB, Access, Zenith, Moniepoint, etc.)
   - **Rejects:** Spam, newsletters, non-bank emails
   - **Result:** 10 of 12 emails pass filter (2 rejected as non-bank)

5. **Parses each email to extract transaction data**

   **Parsing uses 3-stage hybrid system:**

   **Stage 1: Rule-based extraction (fastest, 80% success rate)**

   - Looks for common patterns in Nigerian bank alerts
   - Example patterns:
     - "Amount: NGN 50,000.00"
     - "Reference: GTB/CR/2025/001"
     - "Date: 16-Jan-2025 08:15 AM"
   - If patterns found → ✅ Success, move to next email
   - If patterns not found → Try Stage 2

   **Stage 2: LLM extraction (Groq AI, smart, 95% success rate)**

   - Sends email text to Groq LLM (if configured)
   - LLM intelligently extracts:
     - Transaction amount (even if formatted weirdly)
     - Reference number (even if called "Ref No", "TRN", "Trans ID")
     - Date/time (converts various formats to standard)
     - Bank name (identifies from email address or signature)
   - If LLM succeeds → ✅ Success, move to next email
   - If LLM fails or not configured → Try Stage 3

   **Stage 3: Regex fallback (pattern matching, 60% success rate)**

   - Uses complex regular expressions
   - Searches for numbers that look like amounts
   - Searches for alphanumeric strings that look like references
   - Last resort method
   - If regex succeeds → ✅ Success with lower confidence
   - If regex fails → ⚠️ Email marked as unparseable (manual review needed)

6. **Normalizes extracted data**

   - Converts amounts to standard decimal format (50000.00)
   - Standardizes currency codes (NGN, USD)
   - Converts timestamps to UTC timezone
   - Enriches bank information from database of 118+ banks

7. **Saves parsed emails to database**
   - Inserts into `emails` table
   - Marks as `matched: false` (not yet matched to transactions)
   - Stores extraction metadata (which method was used, confidence)
   - **Result:** 10 new email records in database

**Server log output:**

```
INFO: automation.cycle.step_1.fetch_emails
INFO: email.fetch.start
INFO: email.filter.checked count=12 passed=10 rejected=2
INFO: email.parse.rule_based message_id=<abc123> success=true
INFO: email.parse.llm message_id=<def456> success=true
INFO: email.normalize.complete count=10
INFO: automation.cycle.step_1.success emails_stored=10
```

**What you see in database after Step 1:**

| id  | from_address       | amount    | reference       | timestamp            | matched |
| --- | ------------------ | --------- | --------------- | -------------------- | ------- |
| 1   | alerts@gtbank.com  | 50000.00  | GTB/CR/2025/001 | 2025-01-16T08:15:00Z | false   |
| 2   | noreply@access.com | 150000.00 | ACC/CR/2025/202 | 2025-01-16T08:20:00Z | false   |
| 3   | alerts@zenith.com  | 25000.00  | ZEN/DB/2025/045 | 2025-01-16T08:22:00Z | false   |
| ... | ...                | ...       | ...             | ...                  | ...     |

---

##### **STEP 2: Transaction Polling (2-4 seconds)**

**What BARA does:**

1. **Connects to your banking API**

   - URL: Configured in transaction client
   - Authentication: API key or OAuth token
   - Protocol: HTTPS REST API

2. **Requests new transactions**

   - Sends request: "Give me all transactions since last poll"
   - Date range: Last run time to now
   - Pagination: Fetches in batches (default: 100 per request)

3. **Receives API response**

   - Example: 45 transaction records returned
   - Format: JSON array of transaction objects

4. **Validates each transaction**

   - Checks required fields (amount, reference, timestamp)
   - Rejects malformed records
   - **Result:** 43 of 45 transactions valid (2 rejected as incomplete)

5. **Checks for duplicates**

   - Compares `source_id` against existing database records
   - **Result:** 2 duplicates found (already stored previously)
   - **Net new:** 41 transactions to store

6. **Normalizes transaction data**

   - Converts amounts to decimal
   - Standardizes currency codes
   - Converts timestamps to UTC
   - Enriches bank information

7. **Saves transactions to database**
   - Inserts into `transactions` table
   - Marks as `matched: false`
   - Stores source metadata
   - **Result:** 41 new transaction records

**Server log output:**

```
INFO: automation.cycle.step_2.poll_transactions
INFO: transaction.poll.start
INFO: transaction.api.request batch_size=100
INFO: transaction.api.response count=45
INFO: transaction.validate.complete valid=43 invalid=2
INFO: transaction.deduplicate.complete new=41 duplicates=2
INFO: automation.cycle.step_2.success status=success
```

**What you see in database after Step 2:**

| id  | source_id    | amount    | reference       | timestamp            | matched |
| --- | ------------ | --------- | --------------- | -------------------- | ------- |
| 1   | TXN-2025-001 | 50000.00  | GTB/CR/2025/001 | 2025-01-16T08:15:00Z | false   |
| 2   | TXN-2025-002 | 150000.00 | ACC/CR/2025/202 | 2025-01-16T08:20:00Z | false   |
| 3   | TXN-2025-003 | 30000.00  | ZEN/DB/2025/046 | 2025-01-16T08:25:00Z | false   |
| ... | ...          | ...       | ...             | ...                  | ...     |

---

##### **STEP 3: Matching Engine (4-10 seconds)**

**What BARA does:**

1. **Retrieves all unmatched emails from database**

   - Query: `SELECT * FROM emails WHERE matched = false`
   - **Result:** 54 unmatched emails (10 new + 44 from previous cycles)

2. **For each unmatched email, finds candidate transactions**

   **Retrieval Strategy (2 methods):**

   **Method 1: Composite key lookup (fast, exact matching)**

   - Builds search key: `{amount}_{currency}_{date}`
   - Example: Email has ₦50,000 on 2025-01-16
   - Searches transactions: `amount=50000 AND currency=NGN AND date=2025-01-16`
   - **Result:** 1 candidate found (exact match)

   **Method 2: Range-based fallback (slower, fuzzy matching)**

   - If Method 1 finds no candidates, try broader search
   - Amount range: ±5% (₦47,500 to ₦52,500)
   - Time range: ±72 hours (3 days before/after email timestamp)
   - **Result:** 3 candidates found in range

3. **For each candidate, calculates match score using 7 rules**

   **Rule 1: Exact Amount Match (weight: 30%)**

   - Email amount: ₦50,000.00
   - Transaction amount: ₦50,000.00
   - Score: 1.0 (perfect match)
   - Weighted: 1.0 × 0.30 = 0.30

   **Rule 2: Exact Reference Match (weight: 25%)**

   - Email reference: "GTB/CR/2025/001"
   - Transaction reference: "GTB/CR/2025/001"
   - Score: 1.0 (perfect match)
   - Weighted: 1.0 × 0.25 = 0.25

   **Rule 3: Fuzzy Reference Similarity (weight: 15%)**

   - Uses Levenshtein distance algorithm
   - Email: "GTB/CR/2025/001"
   - Transaction: "GTB/CR/2025/001"
   - Similarity: 100% (identical strings)
   - Score: 1.0
   - Weighted: 1.0 × 0.15 = 0.15

   **Rule 4: Timestamp Proximity (weight: 15%)**

   - Email timestamp: 2025-01-16 08:15:00
   - Transaction timestamp: 2025-01-16 08:15:00
   - Time difference: 0 seconds (perfect match)
   - Score: 1.0 (closer timestamps = higher score)
   - Weighted: 1.0 × 0.15 = 0.15

   **Rule 5: Fuzzy Description Match (weight: 10%)**

   - Email description: "Transfer from John Doe"
   - Transaction description: "Inward Transfer"
   - Token sort ratio: 65% similarity
   - Score: 0.65
   - Weighted: 0.65 × 0.10 = 0.065

   **Rule 6: Same Currency (weight: 3%)**

   - Email: NGN
   - Transaction: NGN
   - Score: 1.0 (same)
   - Weighted: 1.0 × 0.03 = 0.03

   **Rule 7: Same Bank Enrichment (weight: 2%)**

   - Email bank: GTB (Guaranty Trust Bank)
   - Transaction bank: GTB
   - Score: 1.0 (same)
   - Weighted: 1.0 × 0.02 = 0.02

   **Total Confidence Score:**

   - Sum of weighted scores: 0.30 + 0.25 + 0.15 + 0.15 + 0.065 + 0.03 + 0.02 = **0.965 (96.5%)**

4. **Ranks candidates by confidence score**

   - Candidate 1: 0.965 (96.5%) ← Best match
   - Candidate 2: 0.450 (45.0%) ← Poor match
   - Candidate 3: 0.320 (32.0%) ← Poor match

5. **Applies decision thresholds**

   - **Auto-match threshold:** ≥ 0.75 (75%)
   - **Needs review threshold:** 0.50 - 0.74 (50-74%)
   - **Rejected threshold:** < 0.50 (< 50%)

   **Decision for this email:**

   - Best score: 0.965
   - Status: **Auto-matched** ✅ (above 75% threshold)

6. **Saves match to database**

   - Inserts into `matches` table
   - Links email ID to transaction ID
   - Stores confidence score and rule breakdown
   - Updates email: `matched = true`
   - Updates transaction: `matched = true`

7. **Repeats for all 54 unmatched emails**
   - **Results:**
     - 42 auto-matched (≥ 75% confidence)
     - 5 need review (50-74% confidence)
     - 2 rejected (< 50% confidence)
     - 5 no candidates found (no transactions to match)

**Server log output:**

```
INFO: automation.cycle.step_3.match
INFO: matching.start unmatched_count=54
INFO: matching.candidate.retrieval email_id=1 candidates=3
INFO: matching.score.calculated email_id=1 txn_id=1 score=0.965
INFO: matching.decision.auto_match email_id=1 txn_id=1
INFO: matching.save.success match_id=1
INFO: matching.complete total=54 matched=42 review=5 rejected=2 no_candidates=5
INFO: automation.cycle.step_3.success matched=42
```

**What you see in database after Step 3:**

**emails table (updated):**

| id  | amount    | reference       | matched  | match_id |
| --- | --------- | --------------- | -------- | -------- |
| 1   | 50000.00  | GTB/CR/2025/001 | **true** | 1        |
| 2   | 150000.00 | ACC/CR/2025/202 | **true** | 2        |
| 3   | 25000.00  | ZEN/DB/2025/045 | false    | null     |

**transactions table (updated):**

| id  | amount    | reference       | matched  | match_id |
| --- | --------- | --------------- | -------- | -------- |
| 1   | 50000.00  | GTB/CR/2025/001 | **true** | 1        |
| 2   | 150000.00 | ACC/CR/2025/202 | **true** | 2        |
| 3   | 30000.00  | ZEN/DB/2025/046 | false    | null     |

**matches table (new records):**

| id  | email_id | transaction_id | confidence_score | status       | created_at           |
| --- | -------- | -------------- | ---------------- | ------------ | -------------------- |
| 1   | 1        | 1              | 0.965            | auto_matched | 2025-01-16T11:00:15Z |
| 2   | 2        | 2              | 0.920            | auto_matched | 2025-01-16T11:00:16Z |
| ... | ...      | ...            | ...              | ...          | ...                  |

---

##### **STEP 4: Cycle Completion & Sleep (900 seconds)**

**What BARA does:**

1. **Calculates cycle statistics**

   - Duration: 5.2 seconds
   - Emails processed: 10 new
   - Transactions processed: 41 new
   - Matches created: 42
   - Success: Yes

2. **Logs cycle completion**

   ```
   INFO: automation.cycle_complete cycle=1 duration_seconds=5.2
   ```

3. **Updates internal metrics**

   - `total_cycles`: 1
   - `successful_cycles`: 1
   - `failed_cycles`: 0
   - `last_run`: 2025-01-16T11:00:20Z

4. **Sleeps for configured interval**

   - Default: 900 seconds (15 minutes)
   - BARA is idle but still running
   - Server resources freed up
   - Waiting for next cycle

5. **Wakes up after 15 minutes**
   - New cycle begins at 2025-01-16T11:15:20Z
   - Repeats STEP 1 → STEP 2 → STEP 3 → STEP 4
   - Continues forever until stopped

---

#### **Cycle 2, 3, 4... Continuous Operation**

Every 15 minutes, BARA repeats the same cycle:

- Fetch new emails
- Poll new transactions
- Match unmatched items
- Sleep 15 minutes
- Repeat

**Over 24 hours:**

- **Cycles run:** 96 (24 hours × 4 cycles per hour)
- **Emails processed:** ~1,000 (varies by volume)
- **Transactions processed:** ~1,200
- **Matches created:** ~950
- **Success rate:** Typically 95-99%

---

### 1.3 Error Handling: What Happens When Things Go Wrong

BARA is designed to **continue running even when errors occur**.

#### **Scenario 1: Email Server Unavailable**

**What happens:**

1. STEP 1 (Email Fetch) fails with error: "IMAP connection timeout"
2. BARA logs the error but **continues to STEP 2**
3. STEP 2 (Transaction Poll) succeeds
4. STEP 3 (Matching) succeeds with available data
5. Cycle marked as "partial success"
6. Next cycle retries email fetch (usually succeeds)

**Server log:**

```
ERROR: automation.cycle.step_1.error error='IMAP connection timeout'
INFO: automation.cycle.step_2.poll_transactions
INFO: automation.cycle.step_2.success
INFO: automation.cycle.step_3.match
INFO: automation.cycle.step_3.success matched=15
INFO: automation.cycle_complete cycle=5 duration_seconds=3.1
```

**Result:** Automation keeps running, transaction matching continues, email fetch retried next cycle.

---

#### **Scenario 2: Banking API Rate Limit Exceeded**

**What happens:**

1. STEP 2 (Transaction Poll) fails: "API rate limit exceeded"
2. **Circuit breaker activates** (prevents hammering API)
3. BARA logs error and **continues to STEP 3**
4. STEP 3 (Matching) runs with emails only
5. Next cycle: Circuit breaker checks if API recovered
6. If recovered: Resume polling
7. If still down: Keep circuit open, skip polling for X minutes

**Server log:**

```
ERROR: automation.cycle.step_2.error error='API rate limit exceeded'
WARNING: circuit_breaker.open reason='Too many failures' timeout=300
INFO: automation.cycle.step_3.match
INFO: automation.cycle_complete cycle=12
```

**Result:** BARA protects API from overload, continues matching with available data, auto-recovers when API is healthy.

---

#### **Scenario 3: Database Connection Lost**

**What happens:**

1. Mid-cycle, database connection drops
2. STEP 3 (Matching) fails: "Database connection lost"
3. BARA logs **critical error**
4. Attempts to reconnect (3 retries)
5. If reconnect succeeds: Continue
6. If reconnect fails: Mark cycle as failed, wait 15 minutes, retry

**Server log:**

```
CRITICAL: database.connection_lost retries=3
ERROR: automation.cycle_failed cycle=20 error='Database unavailable'
INFO: automation.cycle.retry scheduled_at=2025-01-16T12:15:00Z
```

**Result:** BARA attempts recovery, doesn't crash, resumes when database available.

---

### 1.4 Real-World Example: 24-Hour Operation

**Scenario:** E-commerce business processing customer payments

**Setup:**

- BARA automation started at 9:00 AM on Monday
- Interval: 15 minutes (96 cycles per day)
- Email: Gmail inbox receiving bank alerts
- Transactions: Banking API for payment records

**What happens over 24 hours:**

**9:00 AM - Cycle 1:**

- Fetches 15 weekend emails (backlog)
- Polls 20 weekend transactions
- Matches 18 pairs immediately
- Duration: 6.2 seconds

**9:15 AM - Cycle 2:**

- Fetches 3 new emails
- Polls 5 new transactions
- Matches 7 pairs (includes 2 from backlog)
- Duration: 3.1 seconds

**12:00 PM - Cycle 13 (Lunch rush):**

- Fetches 25 emails (busy period)
- Polls 30 transactions
- Matches 28 pairs
- Duration: 8.5 seconds

**3:00 PM - Cycle 25:**

- Fetches 0 emails (quiet period)
- Polls 2 transactions
- Matches 2 pairs (from backlog)
- Duration: 2.1 seconds

**6:00 PM - Cycle 37:**

- Email server timeout (1 failure)
- Polls 15 transactions successfully
- Matches 8 pairs
- Duration: 3.8 seconds

**11:00 PM - Cycle 57:**

- Fetches 5 late-night emails
- Polls 8 transactions
- Matches 10 pairs
- Duration: 3.5 seconds

**Next day, 9:00 AM - Results:**

- **Total cycles:** 96
- **Successful cycles:** 95 (98.96% success rate)
- **Failed cycles:** 1 (email timeout, recovered next cycle)
- **Total emails processed:** 856
- **Total transactions processed:** 1,023
- **Total matches created:** 802
- **Average match confidence:** 89.3%
- **Unmatched emails:** 54 (6.3% - low-confidence or timing issues)
- **Unmatched transactions:** 221 (21.6% - likely future matches as emails arrive)

**Business impact:**

- 802 payments automatically reconciled
- 54 flagged for manual review (takes 5 minutes instead of 8 hours)
- Zero manual data entry
- Real-time fraud detection (unusual patterns flagged)
- Instant payment confirmation to customers

---

### 1.5 Summary: The Complete Picture

**When you start BARA automation, here's what you get:**

✅ **Continuous email monitoring** - Never miss a bank alert  
✅ **Automatic transaction polling** - Always up-to-date with banking API  
✅ **Intelligent matching** - 7-rule algorithm with 85-95% accuracy  
✅ **Error resilience** - Continues running despite failures  
✅ **Self-healing** - Circuit breakers, retries, automatic recovery  
✅ **Performance tracking** - Detailed metrics and logs  
✅ **Hands-free operation** - Runs 24/7 without intervention  
✅ **Real-time processing** - 15-minute cycles (customizable)

**The result:** Your reconciliation runs itself while you focus on your business.

---

## 19. Technical Deep Dive: How BARA Works

This section provides technical details for developers who want to understand the internals.

### 2.1 Async Architecture

**BARA is built on asyncio**, Python's native asynchronous I/O framework.

**Why async?**

- **Non-blocking I/O:** Thousands of emails/transactions without thread overhead
- **Concurrent operations:** Fetch emails while polling transactions
- **Efficient resource usage:** Single process handles high throughput
- **Modern best practices:** Scales better than threading

**Key async components:**

```python
# Email fetching (async)
async def fetch_emails():
    async with IMAPClient() as client:
        messages = await client.fetch_messages()
        for msg in messages:
            parsed = await parse_email(msg)  # async parsing
            await save_to_db(parsed)  # async database

# Transaction polling (async)
async def poll_transactions():
    async with httpx.AsyncClient() as client:
        response = await client.get("/api/transactions")
        transactions = response.json()
        for txn in transactions:
            await save_to_db(txn)

# Matching engine (async)
async def match_unmatched(db: AsyncSession):
    emails = await db.execute(select(Email).where(Email.matched == False))
    for email in emails:
        candidates = await retrieve_candidates(db, email)
        match = await score_and_rank(candidates)
        await save_match(db, match)
```

**Automation loop (async):**

```python
async def _automation_loop(self):
    while self._running:
        try:
            # Run cycle (all async)
            await self.run_cycle()

            # Sleep without blocking (async)
            await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("cycle_error", error=str(exc))
            await asyncio.sleep(self.interval_seconds)  # Continue despite errors
```

### 2.2 Database Patterns

**Repository + UnitOfWork pattern** ensures clean database access.

**UnitOfWork manages transactions:**

```python
async with UnitOfWork() as uow:
    # All operations share same transaction
    email = await uow.emails.get_by_id(1)
    transaction = await uow.transactions.get_by_id(1)
    match = await uow.matches.create(
        email_id=email.id,
        transaction_id=transaction.id,
        confidence_score=0.95
    )
    # Auto-commits on successful exit
    # Auto-rolls back on exception
```

**Filter operators enable clean queries:**

```python
# Greater than
high_value = await uow.transactions.filter(amount__gt=10000)

# Date range
recent = await uow.emails.filter(
    created_at__gte=datetime(2025, 1, 1),
    created_at__lte=datetime(2025, 1, 31)
)

# Combined filters
matches = await uow.matches.filter(
    confidence_score__gte=0.75,
    created_at__gte=last_week
)
```

### 2.3 Matching Algorithm Internals

**Composite key retrieval:**

```python
def _build_composite_key(email: NormalizedEmail) -> str:
    """Build search key for exact matching."""
    date_key = email.timestamp.strftime("%Y-%m-%d")
    return f"{email.amount}_{email.currency}_{date_key}"

async def retrieve_by_composite_key(db, email):
    """Fast exact lookup."""
    key = _build_composite_key(email)
    candidates = await db.execute(
        select(Transaction).where(
            Transaction.amount == email.amount,
            Transaction.currency == email.currency,
            func.date(Transaction.timestamp) == email.timestamp.date(),
            Transaction.matched == False
        )
    )
    return candidates.scalars().all()
```

**Range-based fallback:**

```python
async def retrieve_by_range(db, email):
    """Broader search when exact lookup fails."""
    min_amount = email.amount * 0.95  # -5%
    max_amount = email.amount * 1.05  # +5%
    min_time = email.timestamp - timedelta(hours=72)
    max_time = email.timestamp + timedelta(hours=72)

    candidates = await db.execute(
        select(Transaction).where(
            Transaction.amount >= min_amount,
            Transaction.amount <= max_amount,
            Transaction.timestamp >= min_time,
            Transaction.timestamp <= max_time,
            Transaction.matched == False
        )
    )
    return candidates.scalars().all()
```

**Rule scoring:**

```python
def calculate_match_score(email, transaction, config):
    """Apply all rules and aggregate scores."""
    scores = {}

    # Rule 1: Exact amount
    scores['exact_amount'] = 1.0 if email.amount == transaction.amount else 0.0

    # Rule 2: Exact reference
    scores['exact_reference'] = 1.0 if email.reference == transaction.reference else 0.0

    # Rule 3: Fuzzy reference
    if email.reference and transaction.reference:
        similarity = fuzz.ratio(email.reference, transaction.reference) / 100.0
        scores['fuzzy_reference'] = similarity
    else:
        scores['fuzzy_reference'] = 0.0

    # Rule 4: Timestamp proximity
    time_diff = abs((email.timestamp - transaction.timestamp).total_seconds())
    max_diff = 72 * 3600  # 72 hours
    proximity = max(0.0, 1.0 - (time_diff / max_diff))
    scores['timestamp_proximity'] = proximity

    # Rule 5: Fuzzy description
    if email.description and transaction.description:
        similarity = fuzz.token_sort_ratio(email.description, transaction.description) / 100.0
        scores['fuzzy_description'] = similarity
    else:
        scores['fuzzy_description'] = 0.0

    # Rule 6: Same currency
    scores['same_currency'] = 1.0 if email.currency == transaction.currency else 0.0

    # Rule 7: Same bank
    scores['same_bank'] = 1.0 if email.bank_code == transaction.bank_code else 0.0

    # Weighted sum
    total = sum(scores[rule] * config.RULES[rule]['weight'] for rule in scores)

    return total, scores
```

### 2.4 Error Recovery Mechanisms

**Circuit breaker (transaction polling):**

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.state = "closed"  # closed, open, half_open
        self.last_failure_time = None

    async def call(self, func):
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half_open"  # Try again
            else:
                raise CircuitBreakerOpenError("Too many failures")

        try:
            result = await func()
            if self.state == "half_open":
                self.state = "closed"  # Recovered!
                self.failure_count = 0
            return result
        except Exception as exc:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            raise
```

**Retry policy (with exponential backoff):**

```python
class RetryPolicy:
    def __init__(self, max_attempts=3, base_delay=1.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay

    async def execute(self, func):
        for attempt in range(self.max_attempts):
            try:
                return await func()
            except Exception as exc:
                if attempt == self.max_attempts - 1:
                    raise  # Last attempt, give up
                delay = self.base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Retry {attempt+1}/{self.max_attempts} after {delay}s")
                await asyncio.sleep(delay)
```

### 2.5 Performance Optimizations

**Database connection pooling:**

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,        # Max concurrent connections
    max_overflow=10,     # Extra connections when busy
    pool_pre_ping=True,  # Check connection health before use
    pool_recycle=3600    # Recycle connections every hour
)
```

**Batch processing:**

```python
async def save_emails_batch(emails: list[ParsedEmail], batch_size=100):
    """Save emails in batches for better performance."""
    for i in range(0, len(emails), batch_size):
        batch = emails[i:i+batch_size]
        async with UnitOfWork() as uow:
            for email in batch:
                await uow.emails.create(**email.dict())
            await uow.commit()
```

**Lazy loading relationships:**

```python
# Don't load related data unless needed
email = await uow.emails.get_by_id(1)  # Fast

# Only load match when accessed
if email.match_id:
    match = await uow.matches.get_by_id(email.match_id)  # Separate query
```

---

## 20. Production Deployment

### 3.1 Pre-Deployment Checklist

Before deploying BARA to production:

- [ ] **Database:** PostgreSQL configured and tested
- [ ] **Environment:** All `.env` variables set correctly
- [ ] **Email:** IMAP credentials tested and working
- [ ] **Transactions:** API client configured and tested
- [ ] **LLM:** Groq API key configured (optional but recommended)
- [ ] **Migrations:** Database schema up-to-date (`alembic upgrade head`)
- [ ] **Tests:** All tests passing (`pytest`)
- [ ] **Backup:** Database backup strategy in place
- [ ] **Monitoring:** Logging and alerting configured
- [ ] **Security:** Secrets stored securely (not in git)
- [ ] **Resources:** Server meets minimum requirements (2GB RAM, 1GB disk)

### 3.2 Deployment Options

#### Option 1: Direct Server Deployment

**Best for:** Simple production deployments, VPS/dedicated server

**Steps:**

1. **Provision server:**

   ```bash
   # Ubuntu 22.04 LTS recommended
   sudo apt update
   sudo apt install -y python3.13 python3.13-venv postgresql nginx
   ```

2. **Clone and setup:**

   ```bash
   git clone https://github.com/K-P1/Bank-Alert-Reconciliation-Agent.git
   cd Bank-Alert-Reconciliation-Agent
   python3.13 -m venv .venv
   source .venv/bin/activate
   pip install uv
   uv sync
   ```

3. **Configure environment:**

   ```bash
   cp .env.example .env
   nano .env  # Edit production settings
   ```

4. **Run migrations:**

   ```bash
   alembic upgrade head
   ```

5. **Start server with systemd:**

   ```bash
   # Create systemd service file
   sudo nano /etc/systemd/system/bara.service
   ```

   ```ini
   [Unit]
   Description=BARA - Bank Alert Reconciliation Agent
   After=network.target postgresql.service

   [Service]
   Type=simple
   User=bara
   WorkingDirectory=/home/bara/Bank-Alert-Reconciliation-Agent
   Environment="PATH=/home/bara/Bank-Alert-Reconciliation-Agent/.venv/bin"
   ExecStart=/home/bara/Bank-Alert-Reconciliation-Agent/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl enable bara
   sudo systemctl start bara
   sudo systemctl status bara
   ```

6. **Configure nginx reverse proxy:**

   ```nginx
   # /etc/nginx/sites-available/bara
   server {
       listen 80;
       server_name bara.yourcompany.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

7. **Start automation:**
   ```bash
   curl -X POST http://localhost:8000/automation/start
   ```

---

#### Option 2: Docker Deployment

**Best for:** Containerized environments, easy scaling, consistent deployments

**Steps:**

1. **Build Docker image:**

   ```bash
   docker build -t bara:3.0 -f docker/Dockerfile .
   ```

2. **Run container:**

   ```bash
   docker run -d \
     --name bara-production \
     -p 8000:8000 \
     --env-file .env \
     --restart unless-stopped \
     bara:3.0
   ```

3. **Run migrations:**

   ```bash
   docker exec bara-production alembic upgrade head
   ```

4. **Start automation:**

   ```bash
   docker exec bara-production curl -X POST http://localhost:8000/automation/start
   ```

5. **Docker Compose (recommended):**

   ```yaml
   # docker-compose.yml
   version: "3.8"

   services:
     bara:
       build: .
       ports:
         - "8000:8000"
       env_file: .env
       depends_on:
         - postgres
       restart: unless-stopped

     postgres:
       image: postgres:14
       environment:
         POSTGRES_DB: bara_prod
         POSTGRES_USER: bara_user
         POSTGRES_PASSWORD: ${DB_PASSWORD}
       volumes:
         - postgres_data:/var/lib/postgresql/data
       restart: unless-stopped

   volumes:
     postgres_data:
   ```

   ```bash
   docker-compose up -d
   ```

---

#### Option 3: Cloud Platform Deployment

**Heroku:**

```bash
# Install Heroku CLI
heroku create bara-production
heroku addons:create heroku-postgresql:standard-0
git push heroku main
heroku run alembic upgrade head
heroku ps:scale web=1
```

**Render:**

1. Connect GitHub repository
2. Select "Web Service"
3. Build command: `uv sync`
4. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL database
6. Deploy

**AWS EC2:**

Same as "Direct Server Deployment" but provision EC2 instance first.

---

### 3.3 Production Configuration

**Recommended `.env` for production:**

```bash
# Environment
ENV=production
DEBUG=false

# Database (PostgreSQL required)
DATABASE_URL=postgresql+asyncpg://bara_user:strong_password@prod-db:5432/bara_prod

# Agent
A2A_AGENT_NAME=BARA

# Email (REQUIRED in production)
IMAP_HOST=imap.gmail.com
IMAP_USER=alerts@yourcompany.com
IMAP_PASS=strong_app_specific_password

# LLM (Recommended)
GROQ_API_KEY=gsk_production_key_here
GROQ_MODEL=llama-3.1-8b-instant

# Performance tuning
POLLER_BATCH_SIZE=500
MOCK_EMAIL_COUNT=0  # Disable mock data in production
```

### 3.4 Security Best Practices

1. **Never commit secrets to git**

   - Use `.env` file (already in `.gitignore`)
   - Use environment variables in cloud platforms
   - Use secret management tools (AWS Secrets Manager, HashiCorp Vault)

2. **Use strong passwords**

   - Database password: 20+ characters, mix of letters/numbers/symbols
   - Email app password: Generated by provider
   - API keys: Rotate regularly

3. **Restrict database access**

   - Create dedicated database user for BARA
   - Grant only necessary permissions (no DROP, CREATE USER)
   - Use connection pooling limits

4. **Enable HTTPS**

   - Use nginx/Caddy reverse proxy
   - Install SSL certificate (Let's Encrypt free)
   - Redirect HTTP to HTTPS

5. **Firewall configuration**

   - Allow only port 443 (HTTPS) externally
   - Block direct access to port 8000
   - Allow database port only from BARA server

6. **Monitor logs for security events**
   - Failed login attempts (IMAP, database)
   - Unusual API activity
   - Unexpected errors

### 3.5 Monitoring & Alerting

**Set up monitoring for:**

1. **Uptime monitoring:**

   - Service: UptimeRobot, Pingdom, StatusCake
   - Monitor: `GET /healthz` every 5 minutes
   - Alert: Email/SMS if down for > 5 minutes

2. **Application metrics:**

   - Service: Prometheus + Grafana
   - Metrics: Request rate, response time, error rate
   - Dashboards: Automation cycles, match rates, confidence scores

3. **Log aggregation:**

   - Service: Logtail, Papertrail, CloudWatch Logs
   - Collect: All BARA logs (stdout)
   - Alerts: ERROR/CRITICAL logs trigger notification

4. **Database monitoring:**

   - Service: pgAdmin, DataDog
   - Monitor: Connection pool, query performance, disk usage
   - Alert: Connection pool exhaustion, slow queries

5. **Error tracking:**
   - Service: Sentry, Rollbar
   - Track: Exceptions, stack traces
   - Alert: New error patterns, high error rates

**Example Grafana dashboard:**

- Automation uptime %
- Cycles per hour
- Match success rate
- Average confidence score
- Email fetch latency
- Transaction poll latency
- Database query time

---

## 21. Troubleshooting Guide

### 4.1 Common Issues & Solutions

#### Issue 1: Server Won't Start

**Symptoms:**

```
Error: Address already in use
```

**Solutions:**

1. **Check if port 8000 is already in use:**

   ```powershell
   netstat -ano | findstr :8000
   ```

2. **Kill existing process:**

   ```powershell
   taskkill /PID <PID> /F
   ```

3. **Use different port:**
   ```powershell
   uvicorn app.main:app --port 8001
   ```

---

#### Issue 2: Database Connection Errors

**Symptoms:**

```
ERROR: could not connect to server: Connection refused
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError)
```

**Solutions:**

1. **Check PostgreSQL is running:**

   ```powershell
   # Windows
   Get-Service postgresql*

   # Linux
   sudo systemctl status postgresql
   ```

2. **Verify connection string:**

   ```bash
   # Check .env file
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/database
   ```

3. **Test connection manually:**

   ```powershell
   psql -U bara_user -d bara_prod -h localhost
   ```

4. **Check firewall:**
   ```powershell
   # Ensure PostgreSQL port 5432 is open
   telnet localhost 5432
   ```

---

#### Issue 3: Migrations Fail

**Symptoms:**

```
ERROR: Target database is not up to date.
alembic.util.exc.CommandError: Can't locate revision identified by 'xxxxx'
```

**Solutions:**

1. **Check current version:**

   ```powershell
   alembic current
   ```

2. **View migration history:**

   ```powershell
   alembic history
   ```

3. **Reset to head (caution: data loss):**

   ```powershell
   # Backup first!
   alembic stamp head
   ```

4. **Re-run migrations:**

   ```powershell
   alembic upgrade head
   ```

5. **If still broken, rebuild database:**
   ```powershell
   # Development only!
   python wipe.py
   alembic upgrade head
   ```

---

#### Issue 4: Email Fetching Fails

**Symptoms:**

```
ERROR: IMAP connection failed: [Errno -2] Name or service not known
WARNING: Email fetch returned 0 messages
```

**Solutions:**

1. **Verify IMAP settings:**

   ```bash
   # Check .env
   IMAP_HOST=imap.gmail.com  # Correct server?
   IMAP_USER=your-email@gmail.com  # Correct email?
   IMAP_PASS=app-specific-password  # Not account password!
   ```

2. **Test IMAP connection manually:**

   ```python
   import imaplib

   mail = imaplib.IMAP4_SSL('imap.gmail.com')
   mail.login('your-email@gmail.com', 'app-password')
   print("Success!")
   ```

3. **Gmail-specific issues:**

   - Enable IMAP in Gmail settings
   - Generate app-specific password (not account password)
   - Check "Less secure app access" (if using password auth)

4. **Check server logs for details:**
   ```
   INFO: email.fetch.start
   ERROR: email.imap.error error='...'
   ```

---

#### Issue 5: Transaction Polling Fails

**Symptoms:**

```
ERROR: Circuit breaker open
ERROR: API rate limit exceeded
WARNING: Transaction poll returned 0 records
```

**Solutions:**

1. **Check circuit breaker status:**

   ```bash
   curl http://localhost:8000/transactions/poller/status
   ```

   Response:

   ```json
   {
     "circuit_breaker": {
       "state": "open", // Problem!
       "failure_count": 5
     }
   }
   ```

2. **Wait for circuit breaker to reset:**

   - Default timeout: 60 seconds
   - State changes: open → half_open → closed

3. **Check API credentials:**

   ```bash
   # Verify API key in transaction client
   # Check API documentation for rate limits
   ```

4. **Reduce polling frequency:**

   - Increase automation interval to avoid rate limits
   - Reduce batch size: `POLLER_BATCH_SIZE=50`

5. **Check API status:**
   ```bash
   curl https://api.yourbank.com/status
   ```

---

#### Issue 6: Matching Produces Low Scores

**Symptoms:**

```
WARNING: Low confidence match: email_id=5 score=0.45
INFO: matching.complete total=50 matched=10 rejected=30
```

**Solutions:**

1. **Review rejected matches:**

   ```bash
   curl http://localhost:8000/matches/?status=rejected&limit=10
   ```

2. **Check data quality:**

   - Emails missing reference numbers
   - Transactions missing timestamps
   - Format mismatches (₦50,000 vs 50000.00)

3. **Verify bank enrichment:**

   ```python
   # Check if bank is in mapping
   from app.normalization.banks import BANK_MAPPINGS

   print(BANK_MAPPINGS.get("gtb"))
   # Should return bank details
   ```

4. **Adjust thresholds (carefully!):**

   ```python
   # app/matching/config.py

   # Current thresholds:
   AUTO_MATCH_THRESHOLD = 0.75  # Lower to 0.70?
   REVIEW_THRESHOLD = 0.50      # Lower to 0.40?
   ```

5. **Check rule weights:**

   ```python
   # If references often don't match, reduce weight:
   "exact_reference": {"weight": 0.15}  # From 0.25

   # If timestamps are unreliable, reduce weight:
   "timestamp_proximity": {"weight": 0.05}  # From 0.15
   ```

---

#### Issue 7: Automation Stops Unexpectedly

**Symptoms:**

```
ERROR: automation.loop_error error='...'
INFO: automation.stopped
```

**Solutions:**

1. **Check automation status:**

   ```bash
   curl http://localhost:8000/automation/status
   ```

   Response:

   ```json
   {
     "running": false,
     "last_error": "Database connection lost"
   }
   ```

2. **Review logs for errors:**

   ```
   ERROR: automation.cycle_failed cycle=25
   CRITICAL: unrecoverable_error
   ```

3. **Restart automation:**

   ```bash
   curl -X POST http://localhost:8000/automation/start
   ```

4. **Fix underlying issue:**
   - Database disconnection → Check PostgreSQL
   - Memory exhaustion → Increase server RAM
   - Disk full → Clean up logs/old data

---

#### Issue 8: Memory Usage High

**Symptoms:**

- Server becomes slow over time
- Out of memory errors
- Swap usage high

**Solutions:**

1. **Check database connection leaks:**

   ```python
   # Ensure UnitOfWork is used correctly:
   async with UnitOfWork() as uow:
       # Do work
       pass  # Auto-closes connection
   ```

2. **Reduce batch sizes:**

   ```bash
   # .env
   POLLER_BATCH_SIZE=100  # From 500
   MOCK_EMAIL_COUNT=10    # From 100
   ```

3. **Enable garbage collection:**

   ```python
   import gc
   gc.collect()  # After each cycle
   ```

4. **Restart server periodically:**
   ```bash
   # Systemd service with memory limit
   [Service]
   MemoryMax=2G
   Restart=always
   ```

---

### 4.2 Debugging Tips

**Enable debug logging:**

```bash
# .env
DEBUG=true
```

**View structured logs:**

```python
import structlog
logger = structlog.get_logger(__name__)

logger.debug("detailed.debug.info",
    email_id=1,
    transaction_id=2,
    score=0.95,
    rules={"exact_amount": 1.0, "exact_reference": 1.0}
)
```

**Use breakpoints in development:**

```python
import pdb; pdb.set_trace()  # Debugger
```

**Test individual components:**

```python
# Test email parsing
from app.emails.parser import parse_email
result = await parse_email(raw_email_text)
print(result)

# Test matching
from app.matching.engine import match_email
match = await match_email(email, transaction)
print(match.confidence_score, match.rule_scores)
```

---

### 4.3 Performance Debugging

**Profile slow queries:**

```python
import time

start = time.time()
result = await uow.emails.filter(matched=False)
duration = time.time() - start

if duration > 1.0:
    logger.warning("slow_query", table="emails", duration=duration)
```

**Monitor database connections:**

```sql
-- PostgreSQL: View active connections
SELECT * FROM pg_stat_activity WHERE datname = 'bara_prod';

-- Check connection pool usage
SELECT count(*) FROM pg_stat_activity;
```

**Check memory usage:**

```python
import psutil

process = psutil.Process()
memory_mb = process.memory_info().rss / 1024 / 1024
logger.info("memory_usage", mb=memory_mb)
```

---


