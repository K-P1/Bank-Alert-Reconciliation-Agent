# Configuration and Secrets

This project uses environment variables (via a local `.env` file) to configure runtime behavior and manage secrets. In production, prefer real environment variables or a secrets manager; do not commit secrets to the repository.

## Environment variables

Copy `.env.example` to `.env` and set values as needed:

- `ENV` — `development` | `staging` | `production` (default: `development`)
- `DEBUG` — `true` or `false` (default: `true`)
- `A2A_AGENT_NAME` — Name used in the A2A route (e.g., `bankMatcher`) and metadata
- `DATABASE_URL` — Connection string for DB (e.g., `postgresql+asyncpg://user:pass@host/db`)
- `TEST_DATABASE_URL` — Optional test DB connection string
- `IMAP_HOST`, `IMAP_USER`, `IMAP_PASS` — IMAP credentials for email fetcher (future stages)
- `LLM_PROVIDER`, `GROQ_API_KEY`, `GROQ_MODEL` — Optional LLM provider config (future stages)

## Loading order

- Locally, `.env` is read automatically by `pydantic-settings` (see `app/core/config.py`).
- In production, set variables in the environment; `.env` is ignored by default.

## Secret handling guidelines

- Never commit real secrets. `.env` is git-ignored.
- Use unique credentials per environment and rotate periodically.
- Restrict IMAP and DB users to the minimal permissions required.
- Avoid logging sensitive data (PII, secrets). Structured logs are configured not to include request bodies by default.
- For CI, use repository or organization-level secrets (e.g., GitHub Actions Secrets) and do not print them in logs.

## Health and A2A endpoints

- Health checks: `GET /` and `GET /healthz`
- A2A JSON-RPC: `POST /a2a/agent/{agent_name}` and `POST /a2a/agent/bankMatcher`
  - Stage 1: only `status` is implemented; other methods return JSON-RPC error `-32601` (not implemented).
