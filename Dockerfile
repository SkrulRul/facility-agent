FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

RUN uv sync --no-dev

# uv run otherwise re-syncs the environment (pulling dev/test-group deps
# over the network) on every invocation — the image must be runnable with
# no network egress once built.
ENV UV_NO_SYNC=1

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
