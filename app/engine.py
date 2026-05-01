"""
Octo Agent — Agent Engine
=========================
Orchestrates the agentic tool-use loop: sends messages to the LLM with
tool schemas, interprets tool-call responses, executes tools, feeds
results back, and repeats until the model produces a final text answer.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from app.agent_state import AgentState
from app.openrouter import OpenRouterClient
from app.tools import ToolRegistry


# ── Configuration ────────────────────────────────────────────────────

MAX_TOOL_ITERATIONS = 25       # hard cap on agentic loops per turn
SPINNER_FPS = 12


# ── Spinner helper ───────────────────────────────────────────────────

def _spinner_call(console: Console, label: str, fn: Callable) -> Any:
    """Run *fn* in a background thread while showing a braille spinner."""
    holder: Dict[str, Any] = {"result": None, "error": None}
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _target():
        try:
            holder["result"] = fn()
        except Exception as exc:
            holder["error"] = exc

    with Live(
        Text.assemble(("  ⠋ ", "#9B6DFF"), (label, "dim")),
        console=console,
        refresh_per_second=SPINNER_FPS,
        transient=True,
    ) as live:
        t = threading.Thread(target=_target, daemon=True)
        t.start()
        idx = 0
        while t.is_alive():
            f = frames[idx % len(frames)]
            live.update(Text.assemble((f"  {f} ", "#9B6DFF"), (label, "dim")))
            idx += 1
            time.sleep(1.0 / SPINNER_FPS)
        t.join()

    if holder["error"]:
        raise holder["error"]
    return holder["result"]


# ── Display helpers ──────────────────────────────────────────────────

def _display_tool_call(console: Console, registry: ToolRegistry, name: str, args: dict) -> None:
    """Print a compact one-liner showing which tool is being called."""
    spec = registry.get(name)
    icon = spec.icon if spec else "🔧"

    line = Text()
    line.append(f"  {icon} ", style="#9B6DFF")
    line.append(name, style="bold #9B6DFF")

    # Inline key arguments
    parts: list[str] = []
    if "path" in args:
        parts.append(args["path"])
    if "command" in args:
        parts.append(f"$ {args['command']}")
    if "pattern" in args:
        parts.append(f"/{args['pattern']}/")
    if "old_text" in args:
        preview = args["old_text"][:50].replace("\n", "\\n")
        parts.append(f'"{preview}…"' if len(args["old_text"]) > 50 else f'"{preview}"')
    if "agent_name" in args:
        parts.append(f"@{args['agent_name']}")

    if parts:
        line.append("  ", style="dim")
        line.append("  ".join(parts), style="#B794F6")

    console.print(line)


def _display_tool_result(console: Console, result: str, term_width: int) -> None:
    """Print tool output in a dim panel, truncated to 10 lines."""
    lines = result.strip().splitlines()
    preview = lines[:10]
    text = "\n".join(preview)
    if len(lines) > 10:
        text += f"\n  … ({len(lines) - 10} more lines)"

    console.print(Panel(
        Text(text, style="dim"),
        border_style="#4A3A6A",
        padding=(0, 2),
        width=min(term_width - 4, 100),
    ))


def _display_response(console: Console, content: str, model: str, term_width: int) -> None:
    """Render the final assistant text in a bordered panel."""
    console.print()
    console.print(Panel(
        Markdown(content),
        border_style="#6B5B95",
        title=f"[bold #9B6DFF]🐙 Octo[/bold #9B6DFF] [dim]({model})[/dim]",
        title_align="left",
        padding=(1, 2),
        width=term_width,
    ))
    console.print()


# ── The Agentic Loop ─────────────────────────────────────────────────

def run_agent_turn(
    console: Console,
    state: AgentState,
    client: OpenRouterClient,
    registry: ToolRegistry,
    cwd: str,
    term_width: int = 110,
) -> None:
    """
    Execute one full agentic turn.

    The LLM is called with the current message history and tool schemas.
    If it returns tool_calls the tools are executed and results fed back;
    this repeats until the LLM returns a plain text response or the
    iteration cap is hit.
    """
    tool_schemas = registry.openai_schemas()

    for iteration in range(MAX_TOOL_ITERATIONS):
        # ── Call the LLM ──
        label = f"Thinking ({client.model})..."
        msg: Dict[str, Any] = _spinner_call(
            console, label,
            lambda: client.chat_with_tools(state.messages, tools=tool_schemas),
        )

        tool_calls = msg.get("tool_calls") or []
        content = (msg.get("content") or "").strip()

        # ── Final text response (no tool calls) ──
        if not tool_calls:
            if content:
                state.record_message("assistant", content)
                _display_response(console, content, client.model, term_width)
            return

        # ── Process tool calls ──
        # Append the raw assistant message (with tool_calls) to history
        state.messages.append(msg)

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "unknown")
            try:
                tool_args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_args = {}
            tool_id = tc.get("id", "")

            # Show what is about to run
            _display_tool_call(console, registry, tool_name, tool_args)

            # Execute
            result = registry.execute(tool_name, tool_args, cwd=cwd)

            # Show truncated result
            _display_tool_result(console, result, term_width)

            # If a core memory tool was used, reload the system prompt so the AI sees it immediately
            if tool_name in ("core_memory_append", "core_memory_replace"):
                state.memory_text = state._load_text(state.memory_path, state._default_memory())
                if state.messages and state.messages[0].get("role") == "system":
                    state.messages[0]["content"] = state._build_system_prompt()

            # Feed result back to the LLM
            state.messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result,
            })

            # Log tool usage to session chat file
            state.log_tool_call(tool_name, tool_args, result)

        # If the model also produced text alongside tool calls, show it
        if content:
            info = Text()
            info.append("  💬 ", style="#9B6DFF")
            info.append(content, style="dim")
            console.print(info)
            console.print()

    # ── Exhausted iterations ──
    warn = Text()
    warn.append("  ⚠ ", style="bold yellow")
    warn.append(f"Reached max iterations ({MAX_TOOL_ITERATIONS}). Stopping.", style="yellow")
    console.print(warn)
    console.print()
