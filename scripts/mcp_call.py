"""Call one OpenHire MCP tool against the INSTALLED code, in-process, and print the result.

Why this exists: the openhire MCP server a desktop client started earlier keeps running the
code it loaded then, so a persona test through that client tests yesterday's build. This
starts the current package's FastMCP server in memory (the same way tests/test_mcp_acceptance
does), calls exactly one tool with JSON arguments, and prints the tool's return value as JSON.

Usage:
  python scripts/mcp_call.py search_jobs '{"skills": ["感知"], "limit": 3}'
  python scripts/mcp_call.py get_company_info '{"company_id": "Momenta"}'
  python scripts/mcp_call.py --list

Reads the index at OPENHIRE_DATABASE_URL (default: the user's local index). Never writes
anything except what the tool itself writes (watches, receipts).
"""
from __future__ import annotations

import asyncio
import json
import sys

from mcp.shared.memory import create_connected_server_and_client_session as connect


def _payload(res):
    sc = res.structuredContent
    if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
        return sc["result"]
    if sc is not None:
        return sc
    return json.loads(res.content[0].text) if res.content else None


async def _main(argv: list[str]) -> int:
    from openhire import __version__
    from openhire.mcp_server import mcp

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    async with connect(mcp._mcp_server) as client:
        if argv[0] == "--list":
            tools = await client.list_tools()
            print(json.dumps({"version": __version__, "tools": [t.name for t in tools.tools]}, ensure_ascii=False))
            return 0
        name = argv[0]
        args = json.loads(argv[1]) if len(argv) > 1 else {}
        res = await client.call_tool(name, args)
        out = {"version": __version__, "tool": name, "args": args, "result": _payload(res)}
        if getattr(res, "isError", False):
            out["isError"] = True
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return 1 if getattr(res, "isError", False) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
