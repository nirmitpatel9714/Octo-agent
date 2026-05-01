"""
Octo Agent — MCP Client
========================
Connects to external MCP servers (via subprocess stdio) and makes their
tools available inside Octo's tool registry.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class MCPClientConnection:
    """A connection to a single external MCP server process."""

    def __init__(self, name: str, command: List[str], env: Optional[Dict[str, str]] = None):
        self.name = name
        self.command = command
        self.env = env
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._msg_id = 0
        self.tools: List[Dict[str, Any]] = []
        self.connected = False

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def connect(self) -> bool:
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.env,
            )
            # Send initialize
            init_resp = self._send({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "octo-agent", "version": "2.0.0"},
                },
            })
            if init_resp and "result" in init_resp:
                # Send initialized notification
                self._send_notification({"jsonrpc": "2.0", "method": "initialized", "params": {}})
                # Fetch tools
                tools_resp = self._send({
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "tools/list",
                    "params": {},
                })
                if tools_resp and "result" in tools_resp:
                    self.tools = tools_resp["result"].get("tools", [])
                self.connected = True
                return True
        except Exception:
            pass
        return False

    def _send(self, message: Dict) -> Optional[Dict]:
        with self._lock:
            if not self._proc or not self._proc.stdin or not self._proc.stdout:
                return None
            try:
                self._proc.stdin.write(json.dumps(message) + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
                if line:
                    return json.loads(line.strip())
            except Exception:
                pass
        return None

    def _send_notification(self, message: Dict) -> None:
        with self._lock:
            if self._proc and self._proc.stdin:
                try:
                    self._proc.stdin.write(json.dumps(message) + "\n")
                    self._proc.stdin.flush()
                except Exception:
                    pass

    def call_tool(self, name: str, arguments: Dict) -> str:
        resp = self._send({
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if not resp:
            return "Error: No response from MCP server"
        result = resp.get("result", {})
        if result.get("isError"):
            content = result.get("content", [{}])
            return content[0].get("text", "Unknown error") if content else "Unknown error"
        content = result.get("content", [{}])
        return content[0].get("text", "") if content else ""

    def disconnect(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass


class MCPManager:
    """Manages multiple MCP server connections and integrates their tools."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self._connections: Dict[str, MCPClientConnection] = {}

    def load_config(self, path: Optional[Path] = None) -> None:
        p = path or self.config_path
        if not p or not p.exists():
            return
        try:
            config = json.loads(p.read_text(encoding="utf-8"))
            servers = config.get("mcpServers", {})
            for name, server_config in servers.items():
                command = server_config.get("command", "")
                args = server_config.get("args", [])
                env = server_config.get("env")
                if command:
                    full_cmd = [command] + args
                    self._connections[name] = MCPClientConnection(name, full_cmd, env)
        except (json.JSONDecodeError, OSError):
            pass

    def connect_all(self) -> Dict[str, bool]:
        results = {}
        for name, conn in self._connections.items():
            results[name] = conn.connect()
        return results

    def disconnect_all(self) -> None:
        for conn in self._connections.values():
            conn.disconnect()

    def get_all_tools(self) -> List[Dict[str, Any]]:
        all_tools = []
        for name, conn in self._connections.items():
            if conn.connected:
                for tool in conn.tools:
                    tool_copy = dict(tool)
                    tool_copy["_mcp_server"] = name
                    all_tools.append(tool_copy)
        return all_tools

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> str:
        conn = self._connections.get(server_name)
        if not conn or not conn.connected:
            return f"Error: MCP server '{server_name}' not connected"
        return conn.call_tool(tool_name, arguments)

    @property
    def connections(self) -> Dict[str, MCPClientConnection]:
        return dict(self._connections)

    def status(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "connected": conn.connected,
                "tools_count": len(conn.tools),
                "command": " ".join(conn.command),
            }
            for name, conn in self._connections.items()
        ]
