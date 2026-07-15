"""Manual smoke test against the REAL MCP server subprocess (stdio transport).

Not part of `uv run poe check` — tests/test_mcp_server.py already covers tool
business logic in-process via fastmcp.Client(mcp) against the server object
directly. This script instead proves the actual process boundary works: the
server starts as a real subprocess over stdio and returns correct results —
both success and not-found — over the real wire protocol.

It launches scripts/mcp_server_seeded.py (a test-only entry point that seeds
one example agreement, then runs the exact same `mcp` object as the real
`app/mcp_server.py`) rather than the production entry point directly, since
the production server has no write/seed capability by design (see
docs/specs/mcp_server.md "Known limitation"). Run manually:
    uv run python scripts/smoke_test_mcp_server.py
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

REPO_ROOT = Path(__file__).parent.parent

# Must match SEEDED_AGREEMENT_ID in scripts/mcp_server_seeded.py. Not imported
# from there directly so this script keeps running via a plain
# `python scripts/smoke_test_mcp_server.py` invocation (no package import of
# its own) — the -m requirement only applies to the subprocess it spawns.
SEEDED_AGREEMENT_ID = UUID("1a08e2ef-0ff9-4bae-ac8d-840c5820a94f")


async def main() -> None:
    transport = StdioTransport(
        command="uv",
        args=["run", "python", "-m", "scripts.mcp_server_seeded"],
        cwd=str(REPO_ROOT),
    )
    client = Client(transport)

    async with client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        print(f"Registered tools: {sorted(tool_names)}")
        if tool_names != {"get_agreement", "list_continuing_defaults"}:
            raise AssertionError(f"unexpected tool set: {tool_names}")

        # --- success path, against the seeded agreement ---
        get_result = await client.call_tool(
            "get_agreement", {"agreement_id": str(SEEDED_AGREEMENT_ID)}
        )
        content = get_result.structured_content
        assert content is not None
        if UUID(content["id"]) != SEEDED_AGREEMENT_ID:
            raise AssertionError(f"unexpected agreement id: {content['id']}")
        if Decimal(content["facility_amount"]) != Decimal("1000000.00"):
            raise AssertionError(f"unexpected facility_amount: {content['facility_amount']}")
        print(f"get_agreement(seeded) -> facility_amount={content['facility_amount']} OK")

        list_result = await client.call_tool(
            "list_continuing_defaults", {"agreement_id": str(SEEDED_AGREEMENT_ID)}
        )
        list_content = list_result.structured_content
        assert list_content is not None
        returned_ids = {UUID(event["id"]) for event in list_content["result"]}
        expected_ids = {UUID("00000000-0000-0000-0000-000000000001")}
        if returned_ids != expected_ids:
            raise AssertionError(
                f"expected only the continuing default {expected_ids}, got {returned_ids}"
            )
        print(f"list_continuing_defaults(seeded) -> {returned_ids} OK (remedied one filtered out)")

        # --- error path, against an unrelated unknown id ---
        unknown_id = uuid4()
        try:
            await client.call_tool("get_agreement", {"agreement_id": str(unknown_id)})
        except ToolError as exc:
            print(f"get_agreement(unknown) -> ToolError as expected: {exc}")
        else:
            raise AssertionError("expected ToolError for an unknown agreement_id")

    print(
        "\nOK — real stdio subprocess started, registered both tools, and "
        "returned correct results (success + not-found) over the wire."
    )


if __name__ == "__main__":
    asyncio.run(main())
