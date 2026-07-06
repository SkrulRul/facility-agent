# facility-agent

> Facility management agent API

## Stack

- **Python 3.13**
- **FastAPI** — async REST API
- **uv** — package management
- **mypy + pyright** — strict type checking
- **ruff** — linting & formatting

## Setup

```bash
uv sync --group dev
```

## Run

```bash
uv run uvicorn src.facility_agent.main:app --reload
```

## Type check

```bash
uv run mypy
uv run pyright
```

## Lint

```bash
uv run ruff check .
uv run ruff format .
```
