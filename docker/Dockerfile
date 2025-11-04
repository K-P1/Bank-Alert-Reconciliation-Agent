# syntax=docker/dockerfile:1.7

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system deps (if any needed later) and uvicorn runtime deps
RUN apt-get update -y && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock* requirements.txt README.md ./
COPY app ./app

# Install dependencies using pip as uv may not be available in production
RUN python -m pip install --upgrade pip \
    && if [ -f requirements.txt ] && [ -s requirements.txt ]; then pip install -r requirements.txt; fi \
    && pip install .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
