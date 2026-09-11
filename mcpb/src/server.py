"""MCPB entry point: run the OpenHire MCP server over stdio.

The real server lives in the `openhire` PyPI package (declared in pyproject.toml); this
file exists so the uv runtime has a script to execute. First run auto-downloads the
public job snapshot (jobs/companies only — never user data).
"""
from openhire.mcp_server import serve

if __name__ == "__main__":
    serve(transport="stdio")
