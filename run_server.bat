@echo off
REM Start FastAPI app with auto-reload (Windows)
setlocal enableextensions enabledelayedexpansion

IF NOT EXIST .env (
  echo [info] No .env found. You can copy .env.example to .env if needed.
)

set PORT=8000
set HOST=127.0.0.1

echo Starting server on http://%HOST%:%PORT%
uvicorn app.main:app --host %HOST% --port %PORT% --reload
