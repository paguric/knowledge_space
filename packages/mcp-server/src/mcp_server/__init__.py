"""MCP server per Knowledge Space.

Espone le operazioni principali (workspace, base, file, search, sync)
come tool MCP, con trasporto stdio (default) e SSE (opzionale).
"""

from mcp_server.server import run_sse, run_stdio

__all__ = ["run_stdio", "run_sse"]


def main() -> None:
    """Entry point CLI per il server MCP standalone."""
    print("Usa 'ks serve' per avviare il server MCP.")
