"""
Octo Agent — MCP Server
========================
Exposes Octo's tool registry as an MCP-compatible server.
Supports initialize, tools/list, tools/call via JSON-RPC over stdio.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict, List, Optional

from app.tools import ToolRegistry, build_default_registry


class MCPServer:
    SERVER_NAME = "octo-agent"
    SERVER_VERSION = "1.0.0"
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, registry: Optional[ToolRegistry] = None, cwd: str = ".") -> None:
        self.registry = registry or build_default_registry()
        self.cwd = cwd
        self._handlers: Dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "ping": self._handle_ping,
        }

    @staticmethod
    def _resp(id: Any, result: Any) -> Dict:
        return {"jsonrpc": "2.0", "id": id, "result": result}

    @staticmethod
    def _err(id: Any, code: int, msg: str) -> Dict:
        return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": msg}}

    def _handle_initialize(self, p: Dict) -> Dict:
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self.SERVER_NAME, "version": self.SERVER_VERSION},
        }

    def _handle_initialized(self, p: Dict) -> Dict:
        return {}

    def _handle_ping(self, p: Dict) -> Dict:
        return {}

    def _handle_tools_list(self, p: Dict) -> Dict:
        tools = []
        for s in self.registry.openai_schemas():
            f = s["function"]
            tools.append({
                "name": f["name"],
                "description": f.get("description", ""),
                "inputSchema": f.get("parameters", {"type": "object", "properties": {}}),
            })
        return {"tools": tools}

    def _handle_tools_call(self, p: Dict) -> Dict:
        name = p.get("name", "")
        args = p.get("arguments", {})
        if not self.registry.get(name):
            return {"content": [{"type": "text", "text": f"Unknown tool '{name}'"}], "isError": True}
        try:
            result = self.registry.execute(name, args, cwd=self.cwd)
            return {"content": [{"type": "text", "text": result}], "isError": False}
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True}

    def handle_message(self, message: Dict) -> Optional[Dict]:
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})
        handler = self._handlers.get(method)
        if not handler:
            return self._err(msg_id, -32601, f"Method not found: {method}") if msg_id else None
        try:
            result = handler(params)
            return self._resp(msg_id, result) if msg_id else None
        except Exception as exc:
            return self._err(msg_id, -32603, str(exc)) if msg_id else None

    def run_stdio(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                sys.stdout.write(json.dumps(self._err(None, -32700, "Parse error")) + "\n")
                sys.stdout.flush()
                continue
            resp = self.handle_message(msg)
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


def run_mcp_server(cwd: str = ".") -> None:
    MCPServer(cwd=cwd).run_stdio()
