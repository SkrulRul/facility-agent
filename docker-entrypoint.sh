#!/bin/sh
set -e

# Migrations only make sense against a real Postgres (ADR-0019: absent
# DATABASE_URL means the in-memory backend, which has no schema to migrate).
if [ -n "$DATABASE_URL" ]; then
    uv run alembic upgrade head
fi

exec uv run fastapi run app/main.py
