# facility-agent

> Facility management agent API

## Stack

- **Python 3.13**
- **FastAPI** — async REST API
- **uv** — package management & virtual environment
- **poethepoet** — task runner
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

## MCP Server

The service layer is also exposed as an MCP server (`app/mcp_server.py`) — a
separate, independent entry point over stdio, not mounted on the FastAPI app.
It exposes two read-only query tools: `get_agreement` and
`list_continuing_defaults`. See [ADR-0018](docs/adr/0018-mcp-server-fastmcp-stdio.md)
and [`docs/specs/mcp_server.md`](docs/specs/mcp_server.md) for the full design
and a known limitation around per-process in-memory state.

```bash
uv run python -m app.mcp_server    # runs the MCP server over stdio
```

To point a Claude Code MCP client at it, add an entry to `.mcp.json` (or your
client's config) with `command: "uv"`, `args: ["run", "python", "-m", "app.mcp_server"]`,
and `cwd` set to this repo's root.

## Tasks

```bash
uv run poe test         # run tests
uv run poe lint         # ruff check
uv run poe format       # ruff format
uv run poe typecheck    # mypy + pyright
uv run poe check        # lint + typecheck + test
```
