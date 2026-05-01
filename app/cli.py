"""
Octo Agent — CLI Shell
======================
Terminal user interface built with prompt_toolkit and rich.
Connects the user to the agent engine.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text
from rich.theme import Theme

from app.agent_state import AgentState
from app.engine import run_agent_turn
from app.openrouter import OpenRouterClient
from app.skills import SkillManager
from app.tools import build_default_registry


# ── Theme ────────────────────────────────────────────────────────────

OCTO_THEME = Theme({
    "info": "dim cyan",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "prompt.arrow": "bold #9B6DFF",
    "prompt.cwd": "bold #B794F6",
    "header.title": "bold #9B6DFF",
    "header.border": "#4A3A6A",
    "response.border": "#4A3A6A",
    "dim": "dim white",
    "accent": "#9B6DFF",
    "muted": "#7B6B9D",
})


# ── Env file helpers ─────────────────────────────────────────────────

def _update_env(env_path: Path, key: str, value: str) -> None:
    lines = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_env(env_file: Path) -> None:
    """Load .env into os.environ (only valid KEY=value lines)."""
    import re
    _ENV_LINE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and _ENV_LINE.match(line):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


# ── Terminal helpers ─────────────────────────────────────────────────

def _get_terminal_width() -> int:
    return min(shutil.get_terminal_size().columns, 120)


def _format_prompt() -> str:
    return "\x1b[1;38;2;155;109;255m ❯\x1b[0m "


# ── Welcome / Goodbye ───────────────────────────────────────────────

def _print_welcome(console: Console, model: str, root_path: Path, session_id: str) -> None:
    width = _get_terminal_width()
    console.print()

    # Top border
    title_text = Text()
    title_text.append("╭─ ", style="#4A3A6A")
    title_text.append("🐙 Octo Agent", style="bold #9B6DFF")
    title_text.append(" v2.0.0", style="dim #7B6B9D")
    remaining = width - 20 - 6
    title_text.append(" " + "─" * max(remaining, 0) + "╮", style="#4A3A6A")
    console.print(title_text)

    # Info rows
    for label, value in [("model", model), ("cwd", str(root_path)), ("session", session_id)]:
        row = Text()
        row.append("│  ", style="#4A3A6A")
        row.append(f"{label}: ", style="dim")
        display = value
        max_val = width - len(label) - 8
        if len(display) > max_val:
            display = "…" + display[-(max_val - 1):]
        row.append(display, style="bold #B794F6" if label == "model" else "#B794F6")
        pad = width - len(f"│  {label}: {display}") - 1
        row.append(" " * max(pad, 0) + "│", style="#4A3A6A")
        console.print(row)

    # Bottom border
    console.print(Text("╰" + "─" * (width - 2) + "╯", style="#4A3A6A"))

    # Tips
    tips = Text()
    tips.append("  Type a message to chat", style="dim")
    tips.append("  •  ", style="#4A3A6A")
    tips.append("/help", style="bold #9B6DFF")
    tips.append(" for commands", style="dim")
    tips.append("  •  ", style="#4A3A6A")
    tips.append("/exit", style="bold #9B6DFF")
    tips.append(" to quit", style="dim")
    console.print(tips)
    console.print()


def _print_goodbye(console: Console) -> None:
    goodbye = Text()
    goodbye.append("  🐙 ", style="#9B6DFF")
    goodbye.append("Session ended. Goodbye!", style="dim")
    console.print(goodbye)
    console.print()


# ── Main loop ────────────────────────────────────────────────────────

class SlashCommandCompleter(Completer):
    def __init__(self, commands: list[str]):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith('/') and ' ' not in text:
            for cmd in self.commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))


def _run_loop(
    console: Console,
    state: AgentState,
    client: OpenRouterClient,
    skills: SkillManager,
    registry,
    cwd: str,
) -> None:
    command_names = [f"/{name}" for name in skills.skills.keys()]
    command_names.extend([f"/{name}" for name in skills._get_md_skills().keys()])
    session = PromptSession(
        history=InMemoryHistory(),
        completer=SlashCommandCompleter(command_names),
        auto_suggest=AutoSuggestFromHistory(),
        complete_while_typing=True
    )

    while True:
        try:
            with patch_stdout():
                user_input = session.prompt(ANSI(_format_prompt()))
        except (EOFError, KeyboardInterrupt):
            console.print()
            _print_goodbye(console)
            break

        text = user_input.strip()
        if not text:
            continue

        # Slash commands
        if text.startswith("/"):
            should_continue = skills.handle(text[1:].strip())
            if not should_continue:
                break
            continue

        # Regular message → agentic turn
        state.record_message("user", text)
        try:
            run_agent_turn(
                console=console,
                state=state,
                client=client,
                registry=registry,
                cwd=cwd,
                term_width=_get_terminal_width(),
            )
        except KeyboardInterrupt:
            console.print()
            warn = Text()
            warn.append("  ⚠ ", style="bold yellow")
            warn.append("Interrupted.", style="yellow")
            console.print(warn)
            console.print()
        except Exception as exc:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append("Error: ", style="bold red")
            err.append(str(exc), style="red")
            console.print(err)
            console.print()


# ── Entry point ──────────────────────────────────────────────────────

def _run_onboarding(console: Console, env_file: Path) -> None:
    console.print()
    console.print("[bold #9B6DFF]🐙 Welcome to Octo Agent Onboarding! 🐙[/]")
    console.print("Let's get your environment set up.\n")
    
    api_key = Prompt.ask("Enter your API key (OpenRouter, OpenAI, etc.)", password=True)
    if api_key.strip():
        _update_env(env_file, "OPENROUTER_API_KEY", api_key.strip())
        console.print("  [success]✔ API key saved![/]")
    
    endpoint = Prompt.ask(
        "API endpoint",
        default="https://openrouter.ai/api/v1/chat/completions",
    )
    if endpoint.strip():
        _update_env(env_file, "OPENROUTER_API_BASE", endpoint.strip())
        console.print("  [success]✔ Endpoint saved![/]")
    
    model = Prompt.ask("Enter default model", default="gpt-4o-mini")
    if model.strip():
        _update_env(env_file, "OPENROUTER_MODEL", model.strip())
        console.print("  [success]✔ Model saved![/]")
        
    console.print("\n[bold green]Onboarding complete![/] Run [bold cyan]python main.py[/] to start Octo.\n")


def main() -> None:
    args = _parse_args()

    root_path = Path(args.data_dir).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)

    # Load .env
    env_file = root_path / ".env"
    _load_env(env_file)

    console = Console(theme=OCTO_THEME)

    if getattr(args, "command", None) == "onboard":
        _run_onboarding(console, env_file)
        return

    api_key = args.api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit(
            "API key is required. Run 'python main.py onboard' to set it up, "
            "or set OPENROUTER_API_KEY or OPENAI_API_KEY."
        )

    if args.api_key:
        _update_env(env_file, "OPENROUTER_API_KEY", args.api_key)

    state = AgentState(root_path)
    model = args.model or os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    client = OpenRouterClient(api_key, model=model, endpoint=args.endpoint)
    registry = build_default_registry()
    skills = SkillManager(state, client, console, env_file=env_file)
    cwd = str(root_path)

    _print_welcome(console, model, root_path, state.session_id)
    _run_loop(console, state, client, skills, registry, cwd)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Octo Agent — Agentic Terminal Assistant 🐙")
    parser.add_argument("command", nargs="?", default=None, help="Command to run (e.g. onboard)")
    parser.add_argument("--api-key", help="API key (OpenRouter, OpenAI, etc.)")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--endpoint", help="API base endpoint (any OpenAI-compatible)")
    parser.add_argument("--data-dir", default=".", help="Directory for config and state files")
    return parser.parse_args()
