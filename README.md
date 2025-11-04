# Bank Alert Reconciliation Agent

Telex-compatible A2A agent that reconciles bank alert emails with internal transactions.

## Stage 1 status

- Health endpoints available at `/` and `/healthz`.
- A2A JSON-RPC endpoint at `POST /a2a/agent/{agent_name}` and `POST /a2a/agent/bankMatcher`.
  - Implemented method: `status` (returns success and metadata).
  - Other methods (`message/send`, `execute`) return JSON-RPC error `-32601` (not implemented) as scaffolding.

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
