# ADR-0022 — Bootstrap tooling choices (Phase 0.1)

**Status:** Accepted

## Decision

A set of environment/tooling choices made at project bootstrap, before Phase 1, recorded here retroactively at MVP close-out (previously tracked only as an unnumbered "Bootstrap Notes" draft in the Notion ADR Log):

- **`uv` over Poetry.** Not just consolidation/speed — the PubGrub resolver, native `uv python install`/`uv python pin` (Poetry defers to pyenv/system Python), and Cargo-style `[tool.uv.workspace]` support.
- **Flat `app/` layout over `src/`-layout.** Matches FastAPI's own "Bigger Applications" docs convention; `fastapi dev` autodetection works natively (needs a package at the invocation root, which `src/` doesn't provide without extra args); no `src/` explanation needed for contributors.
- **`[build-system]`/hatchling omitted.** Consequence of the `app/` decision: this is an application that runs, not a library that's built/distributed. No wheel/sdist needed.
- **mypy strict + pyright strict, asymmetric test scoping.** Both scoped to `app/` + `tests/`. mypy has a `disallow_untyped_defs = false` override for `tests.*` (reduces signature boilerplate; `check_untyped_defs` stays active, so bug detection inside test bodies is not lost). Pyright has no override — deliberately kept stricter than mypy in tests.
- **Ruff `select` includes `ANN` and `FAST`.** `ANN` justified by (a) fail-fast speed vs. a full mypy pass, and (b) `ANN401` catching explicit `Any`, which mypy strict does not flag (an explicit `Any` is technically a valid annotation under `strict = true`). `FAST` is FastAPI's own linter ruleset ported into Ruff (e.g. `FAST002`: flags `Depends(...)` as a parameter default instead of `Annotated[...]`).
- **`fastapi[standard]>=0.115.0`.** Chose the `[standard]` extra (includes `fastapi-cli`) over bare `fastapi` + separate `uvicorn` — `fastapi dev`/`fastapi run` is the more common local-dev pattern industry-wide, not just a convenience wrapper.
- **Task runner: `poethepoet` (`poe`) over Makefile.** Consolidates task definitions inside `pyproject.toml`, consistent with mypy/pyright/ruff/pytest already living there.
- **No LICENSE file.** Deliberate — this repo is for display (portfolio/interview), not third-party reuse.

## Drivers

- Reduce ecosystem-tool sprawl (one lockfile format, one task runner, one place tool config lives — `pyproject.toml`).
- Fail fast and cheap: ruff's `ANN`/`FAST` rules catch a subset of mypy-strict violations in milliseconds rather than seconds.
- This is a training/portfolio project, not a distributed package or a library — several choices above (no `[build-system]`, no LICENSE) follow directly from that.

## Alternatives considered

- **`src/`-layout + hatchling build backend.** Rejected — `src/`-layout's import-isolation guarantee (tests exercising the installed package, not the working directory) is real but low-probability for a self-contained app with no ambiguous package naming and no third-party installers. Revisit if this becomes a monorepo or something others install as a dependency.
- **Makefile.** Rejected — one extra dev dependency (`poethepoet`) is a smaller cost than a second, disconnected task-definition surface outside `pyproject.toml`.
- **Poetry.** Rejected per the `uv` decision above — younger tool (public 1.0 in 2024), less mature plugin/workspace ecosystem than Poetry, `uv.lock` not yet a cross-tool standard format; accepted as a trade-off for the resolver/tooling wins.

## Consequences

- No `Invoice`-style pip-installable packaging exists or is planned; adding one later requires revisiting the `[build-system]` omission.
- Contributors need `uv` installed locally (no Poetry/pip fallback documented) — acceptable for a solo/portfolio repo, would need re-evaluating for a team onboarding flow.
- `poe` task definitions (`lint`, `format`, `typecheck`, `test`, `check`) are the canonical way to run project checks — CI (ADR-0024) and the Docker build (ADR-0023) both defer to this same surface rather than re-implementing check logic.
