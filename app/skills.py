from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

from app.agent_state import AgentState
from app.openrouter import OpenRouterClient
from skills.builtin import get_builtin_skills, SkillDefinition


class SkillManager:
    def __init__(self, state: AgentState, client: OpenRouterClient, console: Console, env_file: Path = None,
                 heartbeat_monitor=None, cron_scheduler=None, mcp_manager=None, mpc_orchestrator=None):
        self.state = state
        self.client = client
        self.console = console
        self.env_file = env_file
        self.heartbeat_monitor = heartbeat_monitor
        self.cron_scheduler = cron_scheduler
        self.mcp_manager = mcp_manager
        self.mpc_orchestrator = mpc_orchestrator
        self.skills = {skill.name: skill for skill in get_builtin_skills()}

    def _get_md_skills(self) -> dict[str, tuple[str, Path]]:
        skills_dir = self.state.root_path / "skills"
        md_skills = {}
        if skills_dir.exists():
            # Only use top-level .md files as requested
            for f in skills_dir.glob("*.md"):
                try:
                    name = f.stem.lower()
                    if name in {"__init__", "builtin"}:
                        continue
                        
                    desc = "Custom .md skill"
                    content = f.read_text(encoding="utf-8").strip()
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            desc = line[:100]
                            break
                    md_skills[name] = (desc, f)
                except Exception:
                    continue
        return md_skills

    def list_skills(self, filter_query: str = "") -> None:
        table = Table(
            show_header=False,
            box=None,
            padding=(0, 2, 0, 0),
            expand=False,
        )
        table.add_column("command", style="bold #9B6DFF", no_wrap=True)
        table.add_column("desc", style="dim")

        # Built-in skills
        for skill in self.skills.values():
            if not filter_query or filter_query in skill.name or filter_query in skill.description.lower():
                table.add_row(f"  /{skill.name}", skill.description)

        # Markdown skills
        md_skills = self._get_md_skills()
        sorted_md = sorted(md_skills.items())
        
        # Categorize by prefix if there are many
        for name, (desc, _) in sorted_md:
            if not filter_query or filter_query in name or filter_query in desc.lower():
                if len(desc) > 60: desc = desc[:57] + "..."
                table.add_row(f"  /{name}", f"{desc} [dim](.md)[/dim]")

        self.console.print()
        title = "Commands" if not filter_query else f"Commands matching '{filter_query}'"
        self.console.print(
            Panel(
                table,
                border_style="#4A3A6A",
                title=f"[bold #9B6DFF]{title}[/bold #9B6DFF]",
                title_align="left",
                padding=(1, 1),
            )
        )
        self.console.print()

    def handle(self, command: str) -> bool:
        if not command:
            return True

        parts = command.strip().split(maxsplit=1)
        name = parts[0].lower()
        argument = parts[1] if len(parts) > 1 else ""

        if name == "help":
            self.list_skills()
            return True

        if name == "init":
            self._handle_init()
            return True

        if name == "agent":
            self._handle_agent(argument)
            return True

        if name == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            return True

        if name == "memory":
            self._show_memory()
            return True

        if name == "save":
            self._save_conversation(argument)
            return True

        if name == "summary":
            self._ask_summary()
            return True

        if name == "compact":
            self._handle_compact()
            return True

        if name == "doctor":
            self._handle_doctor()
            return True

        if name == "debug":
            self._debug_status()
            return True

        if name == "model":
            self._handle_model(argument)
            return True

        if name == "models":
            self._handle_models(argument)
            return True

        if name == "reload":
            self.state.reload_definitions()
            msg = Text()
            msg.append("  ✓ ", style="bold green")
            msg.append("Reloaded soul.md, agent.md, and memory.md.", style="dim")
            self.console.print(msg)
            return True

        if name == "cron":
            self._handle_cron(argument)
            return True

        if name == "heartbeat":
            self._handle_heartbeat()
            return True

        if name == "mcp":
            self._handle_mcp()
            return True

        if name == "mpc":
            self._handle_mpc(argument)
            return True

        if name == "skills":
            self._handle_skills_cmd(argument)
            return True

        if name in {"exit", "quit"}:
            from app.cli import _print_goodbye
            _print_goodbye(self.console)
            return False

        md_skills = self._get_md_skills()
        if name in md_skills:
            _, skill_file = md_skills[name]
            self._handle_md_skill(name, argument, skill_file)
            return True

        err = Text()
        err.append("  ✗ ", style="bold red")
        err.append(f"Unknown command: /{name}", style="red")
        err.append("  — use ", style="dim")
        err.append("/help", style="bold #9B6DFF")
        err.append(" to see available commands.", style="dim")
        self.console.print(err)
        return True

    def _handle_init(self) -> None:
        octo_md = self.state.root_path / "OCTO.md"
        if octo_md.exists():
            msg = Text()
            msg.append("  ℹ ", style="bold cyan")
            msg.append("OCTO.md already exists in this project.", style="dim")
            self.console.print(msg)
            return

        content = (
            "# Project Conventions\n\n"
            "## Build and Test Commands\n"
            "- Build: `npm run build` or equivalent\n"
            "- Test: `npm test` or equivalent\n\n"
            "## Code Style\n"
            "- Follow project-specific patterns\n"
            "- Use clean, documented code\n"
        )
        octo_md.write_text(content, encoding="utf-8")
        msg = Text()
        msg.append("  ✓ ", style="bold green")
        msg.append("Initialized OCTO.md with default conventions.", style="dim")
        self.console.print(msg)

    def _handle_md_skill(self, name: str, argument: str, skill_file: Path) -> None:
        prompt_template = skill_file.read_text(encoding="utf-8")
        if argument:
            task = f"{prompt_template}\n\nArgument: {argument}"
        else:
            task = prompt_template

        self.console.print()
        self.console.print(f"  [bold #9B6DFF]🐙 Running skill '/{name}'...[/bold #9B6DFF]")
        self.console.print()

        from app.engine import run_agent_turn
        from app.tools import build_default_registry
        
        self.state.record_message("user", task)
        
        try:
            from app.cli import _get_terminal_width
            run_agent_turn(
                console=self.console,
                state=self.state,
                client=self.client,
                registry=build_default_registry(),
                cwd=str(self.state.root_path),
                term_width=_get_terminal_width(),
            )
        except KeyboardInterrupt:
            warn = Text()
            warn.append("  ⚠ ", style="bold yellow")
            warn.append("Skill interrupted.", style="yellow")
            self.console.print(warn)
        except Exception as exc:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append(f"Skill Error: {exc}", style="red")
            self.console.print(err)

    def _handle_agent(self, argument: str) -> None:
        if not argument:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append("Usage: /agent [agent_name] [task...]", style="red")
            self.console.print(err)
            
            # List available specialized agents
            agents_dir = self.state.root_path / "agents"
            if agents_dir.exists():
                available = [f.stem for f in agents_dir.glob("*.md")]
                if available:
                    msg = Text()
                    msg.append("  ℹ ", style="bold cyan")
                    msg.append("Available agents: ", style="dim")
                    msg.append(", ".join(available), style="bold #B794F6")
                    self.console.print(msg)
            return

        parts = argument.split(maxsplit=1)
        agent_name = parts[0]
        task = parts[1] if len(parts) > 1 else ""
        
        if not task:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append("Please provide a task for the agent.", style="red")
            self.console.print(err)
            return

        agents_dir = self.state.root_path / "agents"
        agent_file = agents_dir / f"{agent_name}.md"
        
        if not agent_file.exists():
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append(f"Specialized agent '{agent_name}' not found.", style="red")
            self.console.print(err)
            return

        agent_prompt = agent_file.read_text(encoding="utf-8")
        
        self.console.print()
        self.console.print(f"  [bold #9B6DFF]🐙 Sub-agent '{agent_name}' activated for task:[/bold #9B6DFF]")
        self.console.print(f"  [dim]{task}[/dim]")
        self.console.print()

        from app.agent_state import AgentState
        from app.engine import run_agent_turn
        from app.tools import build_default_registry
        
        # Create a temporary state for the sub-agent
        sub_state = AgentState(self.state.root_path)
        sub_state.messages = [
            {"role": "system", "content": agent_prompt},
            {"role": "user", "content": task}
        ]
        
        try:
            from app.cli import _get_terminal_width
            run_agent_turn(
                console=self.console,
                state=sub_state,
                client=self.client,
                registry=build_default_registry(),
                cwd=str(self.state.root_path),
                term_width=_get_terminal_width(),
            )
        except KeyboardInterrupt:
            warn = Text()
            warn.append("  ⚠ ", style="bold yellow")
            warn.append("Sub-agent interrupted.", style="yellow")
            self.console.print(warn)
        except Exception as exc:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append(f"Sub-agent Error: {exc}", style="red")
            self.console.print(err)

        # Retrieve last assistant message and append to main state history
        last_msg = sub_state.messages[-1] if sub_state.messages else {}
        if last_msg.get("role") == "assistant":
            content = last_msg.get("content", "")
            self.state.record_message("assistant", f"[Sub-agent '{agent_name}' output]\n{content}")
            
        self.console.print()
        self.console.print(f"  [bold #9B6DFF]🐙 Sub-agent '{agent_name}' finished.[/bold #9B6DFF]")
        self.console.print()

    def _handle_model(self, argument: str) -> None:
        if not argument:
            msg = Text()
            msg.append("  ℹ ", style="bold cyan")
            msg.append("Current model: ", style="dim")
            msg.append(self.client.model, style="bold #B794F6")
            self.console.print(msg)
            return

        new_model = argument.strip()
        self.client.model = new_model
        
        if self.env_file:
            from app.cli import _update_env
            _update_env(self.env_file, "OPENROUTER_MODEL", new_model)
            
        msg = Text()
        msg.append("  ✓ ", style="bold green")
        msg.append("Model changed to: ", style="dim")
        msg.append(new_model, style="bold #B794F6")
        self.console.print(msg)

    def _handle_models(self, argument: str) -> None:
        import threading
        import time
        from rich.live import Live
        
        query = argument.strip().lower()
        result_holder = {"models": [], "error": None}

        def _fetch():
            try:
                result_holder["models"] = self.client.get_models()
            except Exception as exc:
                result_holder["error"] = exc

        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame_idx = 0

        with Live(
            Text.assemble(("  ⠋ ", "#9B6DFF"), ("Fetching models...", "dim")),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        ) as live:
            thread = threading.Thread(target=_fetch, daemon=True)
            thread.start()
            while thread.is_alive():
                frame = spinner_frames[frame_idx % len(spinner_frames)]
                live.update(Text.assemble((f"  {frame} ", "#9B6DFF"), ("Fetching models...", "dim")))
                frame_idx += 1
                time.sleep(0.08)
            thread.join()

        if result_holder["error"]:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append(f"Error fetching models: {result_holder['error']}", style="red")
            self.console.print(err)
            return
            
        models = result_holder["models"]
        if query:
            models = [m for m in models if query in m.get("id", "").lower() or query in m.get("name", "").lower()]
            
        if not models:
            msg = Text()
            msg.append("  ℹ ", style="bold cyan")
            msg.append(f"No models found matching '{query}'.", style="dim")
            self.console.print(msg)
            return

        models.sort(key=lambda m: m.get("id", ""))
        
        table = Table(show_header=True, header_style="bold #9B6DFF", box=None, padding=(0, 2, 0, 0))
        table.add_column("ID", style="#B794F6", no_wrap=True)
        table.add_column("Name", style="dim")
        table.add_column("Context", style="dim cyan", justify="right")
        
        for m in models[:30]:
            table.add_row(
                m.get("id", ""),
                m.get("name", ""),
                str(m.get("context_length", "N/A"))
            )
            
        self.console.print()
        from rich.panel import Panel
        title = f"[bold #9B6DFF]Models ({len(models)}{' matched' if query else ' total'})[/bold #9B6DFF]"
        if len(models) > 30:
            title += " [dim](showing first 30)[/dim]"
            
        self.console.print(
            Panel(
                table,
                border_style="#4A3A6A",
                title=title,
                title_align="left",
                padding=(1, 1),
            )
        )
        self.console.print()

    def _show_memory(self) -> None:
        from rich.markdown import Markdown
        try:
            memory_text = self.state.memory_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            memory_text = self.state.memory_text
        self.console.print()
        self.console.print(
            Panel(
                Markdown(memory_text) if memory_text.strip() else Text("(empty)", style="dim"),
                border_style="#4A3A6A",
                title="[bold #9B6DFF]Memory[/bold #9B6DFF]",
                title_align="left",
                padding=(1, 2),
            )
        )
        self.console.print()

    def _save_conversation(self, argument: str) -> None:
        timestamp = self._safe_timestamp()
        filename = argument.strip() or f"octo-conversation-{timestamp}.txt"
        save_path = self.state.root_path / filename
        lines = []
        for m in self.state.messages:
            role = m.get('role', 'unknown')
            if role in ('system', 'tool'):
                continue
            content = m.get('content') or ''
            if content:
                lines.append(f"{role.upper()}: {content}")
        save_path.write_text("\n\n".join(lines), encoding="utf-8")
        msg = Text()
        msg.append("  ✓ ", style="bold green")
        msg.append("Saved to ", style="dim")
        msg.append(str(save_path), style="bold #B794F6")
        self.console.print(msg)

    def _handle_doctor(self) -> None:
        table = Table(show_header=True, header_style="bold #9B6DFF", box=None, padding=(0, 2, 0, 0))
        table.add_column("Component", style="dim")
        table.add_column("Status", justify="right")

        def _check(path: Path):
            return "[success]✓ Found[/success]" if path.exists() else "[error]✗ Missing[/error]"

        table.add_row("  .env", _check(self.state.root_path / ".env"))
        table.add_row("  soul.md", _check(self.state.root_path / "soul.md"))
        table.add_row("  agent.md", _check(self.state.root_path / "agent.md"))
        table.add_row("  memory.md", _check(self.state.root_path / "memory.md"))
        table.add_row("  OCTO.md", _check(self.state.root_path / "OCTO.md"))
        table.add_row("  agents/", _check(self.state.root_path / "agents"))
        table.add_row("  skills/", _check(self.state.root_path / "skills"))

        self.console.print()
        self.console.print(
            Panel(
                table,
                border_style="#4A3A6A",
                title="[bold #9B6DFF]Agent Doctor[/bold #9B6DFF]",
                title_align="left",
                padding=(1, 1),
            )
        )
        self.console.print()

    def _handle_compact(self) -> None:
        import threading
        import time
        from rich.live import Live

        prompt = (
            "Summarize the conversation history so far into a single dense 'Context' block. "
            "Include all key decisions, code changes discussed, and current goals. "
            "This will be used to replace the current history to save context space. "
            "Respond in plain text only — do NOT use tool calls or JSON."
        )
        self.state.messages.append({"role": "user", "content": prompt})

        result_holder = {"response": None, "error": None}

        def _fetch():
            try:
                result_holder["response"] = self.client.chat(self.state.messages)
            except Exception as exc:
                result_holder["error"] = exc

        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame_idx = 0

        with Live(
            Text.assemble(("  ⠋ ", "#9B6DFF"), ("Compacting...", "dim")),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        ) as live:
            thread = threading.Thread(target=_fetch, daemon=True)
            thread.start()
            while thread.is_alive():
                frame = spinner_frames[frame_idx % len(spinner_frames)]
                live.update(Text.assemble((f"  {frame} ", "#9B6DFF"), ("Compacting...", "dim")))
                frame_idx += 1
                time.sleep(0.08)
            thread.join()

        if result_holder["error"]:
            # Remove the synthetic prompt we added so it doesn't pollute history
            if self.state.messages and self.state.messages[-1].get("content") == prompt:
                self.state.messages.pop()
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append(str(result_holder["error"]), style="red")
            self.console.print(err)
            return

        summary = result_holder["response"]
        
        # Replace history
        system_msg = self.state.messages[0]
        self.state.messages = [
            system_msg,
            {"role": "assistant", "content": f"Context Compacted. Previous history summary:\n\n{summary}"}
        ]
        
        msg = Text()
        msg.append("  ✓ ", style="bold green")
        msg.append("History compacted and replaced with summary.", style="dim")
        self.console.print(msg)

    def _debug_status(self) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0), expand=False)
        table.add_column("key", style="dim", no_wrap=True)
        table.add_column("value", style="#B794F6")

        table.add_row("  Endpoint", self.client.endpoint)
        table.add_row("  Model", self.client.model)
        table.add_row("  API Key", "✓ configured" if self.client.api_key else "✗ missing")

        self.console.print()
        self.console.print(
            Panel(
                table,
                border_style="#4A3A6A",
                title="[bold #9B6DFF]Debug Info[/bold #9B6DFF]",
                title_align="left",
                padding=(1, 1),
            )
        )
        self.console.print()

    def _ask_summary(self) -> None:
        from rich.markdown import Markdown
        import time
        import threading
        from rich.live import Live

        prompt = (
            "You are the Octo Agent assistant. Summarize the conversation so far and highlight the key goals, open tasks, and any code-related decisions. "
            "Keep it concise and actionable. Respond in plain text only — do NOT use tool calls or JSON."
        )
        # Add temporarily for the API call but don't persist to chat log
        self.state.messages.append({"role": "user", "content": prompt})

        result_holder = {"response": None, "error": None}

        def _fetch():
            try:
                result_holder["response"] = self.client.chat(self.state.messages)
            except Exception as exc:
                result_holder["error"] = exc

        spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame_idx = 0

        with Live(
            Text.assemble(("  ⠋ ", "#9B6DFF"), ("Summarizing...", "dim")),
            console=self.console,
            refresh_per_second=12,
            transient=True,
        ) as live:
            thread = threading.Thread(target=_fetch, daemon=True)
            thread.start()
            while thread.is_alive():
                frame = spinner_frames[frame_idx % len(spinner_frames)]
                live.update(Text.assemble((f"  {frame} ", "#9B6DFF"), ("Summarizing...", "dim")))
                frame_idx += 1
                time.sleep(0.08)
            thread.join()

        # Remove the synthetic summary prompt from history
        if self.state.messages and self.state.messages[-1].get("content") == prompt:
            self.state.messages.pop()

        if result_holder["error"]:
            err = Text()
            err.append("  ✗ ", style="bold red")
            err.append(str(result_holder["error"]), style="red")
            self.console.print(err)
            return

        summary = result_holder["response"]
        self.state.record_message("assistant", summary)
        self.console.print()
        self.console.print(
            Panel(
                Markdown(summary),
                border_style="#4A3A6A",
                title="[bold #9B6DFF]Summary[/bold #9B6DFF]",
                title_align="left",
                padding=(1, 2),
            )
        )
        self.console.print()

    # ── New subsystem handlers ────────────────────────────────────────

    def _handle_cron(self, argument: str) -> None:
        if not self.cron_scheduler:
            self.console.print("  [error]✗ Cron scheduler not initialized. Run with 'python main.py web' to enable.[/error]")
            return

        parts = argument.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        sub_arg = parts[1] if len(parts) > 1 else ""

        if sub == "list" or not sub:
            jobs = self.cron_scheduler.list_jobs()
            if not jobs:
                self.console.print("  [dim]No cron jobs configured.[/dim]")
                return
            table = Table(show_header=True, header_style="bold #9B6DFF", box=None, padding=(0, 2, 0, 0))
            table.add_column("ID", style="#B794F6")
            table.add_column("Name", style="dim")
            table.add_column("Schedule", style="dim cyan")
            table.add_column("Enabled", justify="center")
            table.add_column("Runs", justify="right")
            for j in jobs:
                enabled = "[green]✓[/green]" if j.enabled else "[yellow]⏸[/yellow]"
                table.add_row(j.job_id, j.name, j.schedule, enabled, str(j.run_count))
            self.console.print(Panel(table, border_style="#4A3A6A", title="[bold #9B6DFF]Cron Jobs[/]", title_align="left", padding=(1,1)))

        elif sub == "add":
            # /cron add <schedule> <name>: <prompt>
            if not sub_arg:
                self.console.print("  [error]Usage: /cron add <schedule> <name>: <prompt>[/error]")
                return
            # Parse: "every 5m Daily Check: do something"
            schedule_parts = sub_arg.split(":", maxsplit=1)
            if len(schedule_parts) < 2:
                self.console.print("  [error]Format: /cron add every 5m Job Name: prompt text[/error]")
                return
            header = schedule_parts[0].strip()
            prompt = schedule_parts[1].strip()
            # Split header into schedule and name
            tokens = header.split()
            # Try to find schedule pattern (e.g., "every 5m")
            schedule = ""
            name = ""
            if len(tokens) >= 2 and tokens[0] == "every":
                schedule = f"every {tokens[1]}"
                name = " ".join(tokens[2:]) or "Untitled"
            else:
                schedule = tokens[0] if tokens else "every 5m"
                name = " ".join(tokens[1:]) or "Untitled"
            job = self.cron_scheduler.add_job(name, schedule, prompt)
            msg = Text()
            msg.append("  ✓ ", style="bold green")
            msg.append(f"Created cron job '{job.name}' ({job.job_id}) — {job.schedule}", style="dim")
            self.console.print(msg)

        elif sub == "remove" or sub == "rm":
            if not sub_arg:
                self.console.print("  [error]Usage: /cron remove <job_id>[/error]")
                return
            ok = self.cron_scheduler.remove_job(sub_arg.strip())
            if ok:
                self.console.print(f"  [green]✓ Removed job {sub_arg}[/green]")
            else:
                self.console.print(f"  [error]✗ Job '{sub_arg}' not found[/error]")

        elif sub == "toggle":
            if not sub_arg:
                self.console.print("  [error]Usage: /cron toggle <job_id>[/error]")
                return
            new_state = self.cron_scheduler.toggle_job(sub_arg.strip())
            if new_state is not None:
                label = "enabled" if new_state else "paused"
                self.console.print(f"  [green]✓ Job {sub_arg} is now {label}[/green]")
            else:
                self.console.print(f"  [error]✗ Job '{sub_arg}' not found[/error]")
        else:
            self.console.print("  [dim]Usage: /cron [list|add|remove|toggle][/dim]")

    def _handle_heartbeat(self) -> None:
        if not self.heartbeat_monitor:
            self.console.print("  [error]✗ Heartbeat monitor not initialized. Run with 'python main.py web' to enable.[/error]")
            return
        snap = self.heartbeat_monitor.beat()
        table = Table(show_header=False, box=None, padding=(0, 2, 0, 0), expand=False)
        table.add_column("key", style="dim", no_wrap=True)

        table.add_column("value", style="#B794F6")
        table.add_row("  Status", snap.get("status", "unknown"))
        table.add_row("  Uptime", f"{snap.get('uptime_seconds', 0):.0f}s")
        table.add_row("  API Reachable", "✓" if snap.get("api_reachable") else "✗")
        sys_info = snap.get("system", {})
        if "cpu_percent" in sys_info:
            table.add_row("  CPU", f"{sys_info['cpu_percent']}%")
        if "memory_used_percent" in sys_info:
            table.add_row("  System Memory", f"{sys_info['memory_used_percent']}%")
        proc_info = snap.get("process", {})
        if "memory_mb" in proc_info:
            table.add_row("  Process Memory", f"{proc_info['memory_mb']} MB")
        self.console.print(Panel(table, border_style="#4A3A6A", title="[bold #9B6DFF]Heartbeat[/]", title_align="left", padding=(1,1)))

    def _handle_mcp(self) -> None:
        if not self.mcp_manager:
            self.console.print("  [error]✗ MCP manager not initialized. Run with 'python main.py web' to enable.[/error]")
            return
        status = self.mcp_manager.status()
        if not status:
            self.console.print("  [dim]No MCP servers configured. Add to mcp_config.json.[/dim]")
            return
        table = Table(show_header=True, header_style="bold #9B6DFF", box=None, padding=(0, 2, 0, 0))
        table.add_column("Server", style="#B794F6")
        table.add_column("Status")
        table.add_column("Tools", justify="right")
        table.add_column("Command", style="dim")
        for s in status:
            st = "[green]✓ Connected[/green]" if s["connected"] else "[red]✗ Disconnected[/red]"
            table.add_row(s["name"], st, str(s["tools_count"]), s["command"])
        self.console.print(Panel(table, border_style="#4A3A6A", title="[bold #9B6DFF]MCP Servers[/]", title_align="left", padding=(1,1)))

    def _handle_mpc(self, argument: str) -> None:
        if not self.mpc_orchestrator:
            self.console.print("  [error]✗ MPC orchestrator not initialized. Run with 'python main.py web' to enable.[/error]")
            return

        parts = argument.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"

        if sub == "list" or not argument.strip():
            agents = self.mpc_orchestrator.list_agents()
            if not agents:
                self.console.print("  [dim]No agents found. Add .md files to agents/ directory.[/dim]")
                return
            self.console.print(f"  [dim]Available agents:[/dim] [bold #B794F6]{', '.join(agents)}[/bold #B794F6]")

        elif sub == "pipeline":
            sub_arg = parts[1] if len(parts) > 1 else ""
            # /mpc pipeline coder,reviewer : task
            if ":" not in sub_arg:
                self.console.print("  [error]Usage: /mpc pipeline agent1,agent2 : task description[/error]")
                return
            agents_str, task = sub_arg.split(":", maxsplit=1)
            agent_names = [a.strip() for a in agents_str.split(",") if a.strip()]
            results = self.mpc_orchestrator.create_pipeline(agent_names, task.strip())
            from rich.markdown import Markdown
            for r in results:
                self.console.print(Panel(
                    Markdown(r.content),
                    border_style="#5A5A7A",
                    title=f"[bold #D4A574]{r.agent}[/] [dim](step {r.step})[/dim]",
                    title_align="left",
                    padding=(1, 2),
                ))

        elif sub == "debate":
            sub_arg = parts[1] if len(parts) > 1 else ""
            if ":" not in sub_arg:
                self.console.print("  [error]Usage: /mpc debate agent1,agent2 : task description[/error]")
                return
            agents_str, task = sub_arg.split(":", maxsplit=1)
            agent_names = [a.strip() for a in agents_str.split(",") if a.strip()]
            results = self.mpc_orchestrator.create_debate(agent_names, task.strip())
            from rich.markdown import Markdown
            for r in results:
                self.console.print(Panel(
                    Markdown(r.content),
                    border_style="#5A5A7A",
                    title=f"[bold #D4A574]{r.agent}[/] [dim](debate turn)[/dim]",
                    title_align="left",
                    padding=(1, 2),
                ))
        else:
            self.console.print("  [dim]Usage: /mpc [list|pipeline|debate][/dim]")

    def _handle_skills_cmd(self, argument: str) -> None:
        parts = argument.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else "list"
        sub_arg = parts[1] if len(parts) > 1 else ""

        if sub == "list" or not sub:
            self.list_skills(sub_arg)
        elif sub == "search":
            self.list_skills(sub_arg)
        elif sub == "reload":
            # Just trigger a refresh in UI
            self.console.print("  [success]✓ Refreshed skills cache.[/success]")
        elif sub == "add" or sub == "create":
            # Call existing creation logic via LLM or just direct?
            self.console.print("  [info]ℹ Use the 'create_skill' tool via the agent to add new skills.[/info]")
        else:
            self.console.print(f"  [dim]Usage: /skills [list|search|reload][/dim]")

    @staticmethod
    def _safe_timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
