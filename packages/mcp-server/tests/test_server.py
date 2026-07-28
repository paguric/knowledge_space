"""Test per il server MCP: verifica che i tool siano registrati correttamente
con l'API MCP 2.0 (add_request_handler, non decoratori on_list_tools/on_call_tool)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from knowledge_base.persistence import GlobalIndex
from knowledge_base.workspace_manager import WorkspaceManager
from mcp_server.server import _make_server


def _make_workspace_manager(tmp_path: Path) -> WorkspaceManager:
    """Crea un WorkspaceManager temporaneo per i test."""
    index_path = tmp_path / "workspaces.json"
    config_root = tmp_path / "configs"

    def config_path_for(ws_path: Path) -> Path:
        return config_root / ws_path.name / "config.json"

    return WorkspaceManager(GlobalIndex(path=index_path), config_path_for)


class TestMakeServer:
    """Test sulla creazione del server MCP."""

    def test_server_si_crea_senza_errori(self, tmp_path):
        """_make_server() non solleva eccezioni con MCP 2.0."""
        mgr = _make_workspace_manager(tmp_path)
        server = _make_server(mgr, lambda p: p, state_home=tmp_path)
        assert server is not None
        assert server.name == "knowledge-space"

    def test_tools_list_handler_registrato(self, tmp_path):
        """Il handler per tools/list è registrato."""
        mgr = _make_workspace_manager(tmp_path)
        server = _make_server(mgr, lambda p: p, state_home=tmp_path)
        assert "tools/list" in server._request_handlers

    def test_tools_call_handler_registrato(self, tmp_path):
        """Il handler per tools/call è registrato."""
        mgr = _make_workspace_manager(tmp_path)
        server = _make_server(mgr, lambda p: p, state_home=tmp_path)
        assert "tools/call" in server._request_handlers

    def test_on_list_tools_non_esiste(self, tmp_path):
        """Il decoratore on_list_tools non deve essere usato (API MCP 1.x)."""
        mgr = _make_workspace_manager(tmp_path)
        server = _make_server(mgr, lambda p: p, state_home=tmp_path)
        assert not hasattr(server, "on_list_tools")

    def test_on_call_tool_non_esiste(self, tmp_path):
        """Il decoratore on_call_tool non deve essere usato (API MCP 1.x)."""
        mgr = _make_workspace_manager(tmp_path)
        server = _make_server(mgr, lambda p: p, state_home=tmp_path)
        assert not hasattr(server, "on_call_tool")

    def test_ping_handler_registrato(self, tmp_path):
        """Il handler per ping è registrato (gestito internamente da MCP)."""
        mgr = _make_workspace_manager(tmp_path)
        server = _make_server(mgr, lambda p: p, state_home=tmp_path)
        assert "ping" in server._request_handlers
