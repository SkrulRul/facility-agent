# facility-agent

> Facility management agent API

## Stack

- **Python 3.13**
- **FastAPI** — async REST API
- **uv** — package management & virtual environment
- **mypy + pyright** — strict type checking
- **ruff** — linting & formatting
- **pytest** — testing

## Setup

```bash
uv sync          # installs all groups (dev + test) automatically
```

## Run

```bash
uv run fastapi dev          # development (auto-reload)
uv run fastapi run          # production
```

API available at `http://127.0.0.1:8000`
Docs at `http://127.0.0.1:8000/docs`

## Test

```bash
uv run pytest
```

## Type check

```bash
uv run mypy
uv run pyright
```

## Lint & format

```bash
uv run ruff check .
uv run ruff format .
```
