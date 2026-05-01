from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List


class AgentState:
    def __init__(self, root_path: Path):
        self.root_path = root_path
        
        self.chats_path = self.root_path / "chats"
        self.chats_path.mkdir(parents=True, exist_ok=True)
        self.agents_path = self.root_path / "agents"
        self.agents_path.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.session_file = self.chats_path / f"chat_{self.session_id}.md"
        self.session_file.write_text(f"# Chat Session {self.session_id}\n\n", encoding="utf-8")

        self.soul_path = self.root_path / "soul.md"
        self.agent_path = self.root_path / "agent.md"
        self.memory_path = self.root_path / "memory.md"
        self.soul_text = self._load_text(self.soul_path, self._default_soul())
        self.agent_text = self._load_text(self.agent_path, self._default_agent())
        self.memory_text = self._load_text(self.memory_path, self._default_memory())
        self._ensure_specialized_agents()
        self._ensure_custom_skills()
        self.messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(),
            }
        ]

    def _load_text(self, path: Path, default: str) -> str:
        if not path.exists():
            path.write_text(default, encoding="utf-8")
        return path.read_text(encoding="utf-8")

    def _ensure_specialized_agents(self) -> None:
        agents = {
            "coder": (
                "You are an expert coder within the Octo Agent system. Focus on providing efficient, "
                "clean, and bug-free code. Use tools proactively to write, test, and debug code. "
                "When delegated a task, be thorough and verify your work."
            ),
            "researcher": (
                "You are a meticulous researcher within the Octo Agent system. Use tools to search "
                "thoroughly, gather facts, and present well-structured summaries. Cross-reference "
                "multiple sources when possible."
            ),
            "reviewer": (
                "You are a strict code reviewer within the Octo Agent system. Look for edge cases, "
                "security vulnerabilities, performance issues, and code quality problems. Provide "
                "actionable feedback with specific suggestions."
            ),
            "architect": (
                "You are a software architect within the Octo Agent system. Focus on system design, "
                "component interactions, scalability, and maintainability. Provide high-level design "
                "documents and diagrams when helpful."
            ),
            "debugger": (
                "You are an expert debugger within the Octo Agent system. Systematically diagnose issues "
                "using tools: read logs, inspect state, add instrumentation, and narrow down root causes. "
                "Always verify fixes before reporting success."
            ),
        }
        for name, prompt in agents.items():
            path = self.agents_path / f"{name}.md"
            content = f"# {name.title()}\n\n{prompt}\n"
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def _ensure_custom_skills(self) -> None:
        self.custom_skills_path = self.root_path / "skills"
        self.custom_skills_path.mkdir(parents=True, exist_ok=True)
        
        anthropic_skills = {
            "bug": "Report and resolve bugs. This skill analyzes the codebase, reproduces the issue, and implements a verified fix.",
            "commit": "Analyze staged changes and generate a high-quality commit message following Conventional Commits. Use git diff to understand the changes.",
            "explain": "Explain code, concepts, or error messages clearly and concisely, breaking down complex logic into digestible parts.",
            "review": "Perform an AI-powered code review on staged or unstaged changes, checking for correctness, style, and potential bugs.",
            "test": "Generate tests for your project files, analyzing method behavior and edge cases to ensure reliability and coverage.",
            "docs": "Generate or update documentation, including READMEs and docstrings, ensuring accuracy and Markdown consistency.",
            "compact": "Compress the conversation history into a concise summary to maintain context quality and manage token limits.",
            "pr": "Generate a detailed Pull Request description based on the current changes, including impact and a reviewer checklist.",
            "doctor": "Diagnose the current agent state and environment to ensure everything is configured and running correctly."
        }
        
        for name, prompt in anthropic_skills.items():
            path = self.custom_skills_path / f"{name}.md"
            content = f"# {name.title()}\n\n{prompt}\n"
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def _build_system_prompt(self) -> str:
        prompt = "# Octo Agent System Prompt\n"
        prompt += self.soul_text.strip() + "\n\n"
        prompt += self.agent_text.strip() + "\n\n"
        octo_md = self.root_path / "OCTO.md"
        # Also check for legacy ANDA.md
        anda_md = self.root_path / "ANDA.md"
        if octo_md.exists():
            prompt += "Project Conventions (OCTO.md):\n" + octo_md.read_text(encoding="utf-8").strip() + "\n\n"
        elif anda_md.exists():
            prompt += "Project Conventions (ANDA.md):\n" + anda_md.read_text(encoding="utf-8").strip() + "\n\n"

        if self.memory_text.strip():
            prompt += "Long-term memory:\n" + self.memory_text.strip() + "\n\n"

        # Build a dynamic index of all .md files in the project
        md_index = self._build_md_index()
        if md_index:
            prompt += "Available reference documents (.md files):\n"
            prompt += md_index + "\n"
            prompt += (
                "Use `read_file` to read any of these when relevant. "
                "Use `list_reference_docs` to get a refreshed listing at any time.\n\n"
            )

        prompt += (
            "You are Octo 🐙, an agentic AI coding assistant running in a terminal. "
            "You have access to tools: read_file, write_file, edit_file, run_command, "
            "list_directory, search_files, core_memory_append, core_memory_replace, "
            "create_skill, delete_skill, list_reference_docs, create_agent, list_agents, "
            "delegate_to_agent, browse_url. "
            "Use these tools proactively to explore the codebase, write code, run tests, and solve problems. "
            "When the user asks you to do something, use your tools to actually do it — "
            "don't just describe what to do. "
            "Read files before editing them. Be precise and thorough. "
            "You can delegate complex sub-tasks to specialized agents using `delegate_to_agent`. "
            "You can create new reusable skills with `create_skill` — these become /slash-commands the user can invoke. "
            "After completing a task, give a concise summary of what you did."
        )
        return prompt

    def _build_md_index(self) -> str:
        """Scan the project and return a compact index of all .md files with one-line descriptions."""
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".env", "chats"}
        entries: list[str] = []

        def _first_content_line(path: Path) -> str:
            """Return the first non-empty, non-heading line as a short description."""
            try:
                for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                        return stripped[:100]
            except OSError:
                pass
            return ""

        def _walk(dir_path: Path, prefix: str = "") -> None:
            try:
                for entry in sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    if entry.name in skip_dirs:
                        continue
                    rel = f"{prefix}{entry.name}" if prefix else entry.name
                    if entry.is_dir():
                        _walk(entry, f"{rel}/")
                    elif entry.suffix.lower() == ".md":
                        desc = _first_content_line(entry)
                        line = f"  - {rel}"
                        if desc:
                            line += f"  — {desc}"
                        entries.append(line)
            except PermissionError:
                pass

        _walk(self.root_path)
        return "\n".join(entries)

    def record_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        if role in {"user", "assistant"}:
            self._append_chat(role, content)

    def _append_chat(self, role: str, content: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"\n\n### {timestamp} ({role.upper()})\n{content.strip()}\n"
        with self.session_file.open("a", encoding="utf-8") as f:
            f.write(entry)

    def log_tool_call(self, tool_name: str, args: dict, result: str) -> None:
        """Log a tool invocation to the session chat file."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        args_short = {k: (v[:120] + "…" if isinstance(v, str) and len(v) > 120 else v) for k, v in args.items()}
        result_short = result[:300] + "…" if len(result) > 300 else result
        entry = f"\n\n### {timestamp} (TOOL: {tool_name})\nArgs: {args_short}\nResult: {result_short}\n"
        with self.session_file.open("a", encoding="utf-8") as f:
            f.write(entry)

    def reload_definitions(self) -> None:
        self.soul_text = self._load_text(self.soul_path, self._default_soul())
        self.agent_text = self._load_text(self.agent_path, self._default_agent())
        self.memory_text = self._load_text(self.memory_path, self._default_memory())
        # Only update the system prompt, preserving conversation history
        new_system = {"role": "system", "content": self._build_system_prompt()}
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0] = new_system
        else:
            self.messages.insert(0, new_system)

    @staticmethod
    def _default_soul() -> str:
        return (
            "# Soul\n\n"
            "Octo 🐙 is a calm and capable terminal AI assistant. It is inquisitive but concise, "
            "prioritizes clarity, and stays oriented around the user's intent. It remembers important "
            "project details and behaves like a skilled collaborator rather than a lecture."
        )

    @staticmethod
    def _default_agent() -> str:
        return (
            "# Agent Design\n\n"
            "Octo Agent is a terminal-first AI assistant that uses any OpenAI-compatible API for chat completions. "
            "It stores persona notes in soul.md and long-term memory in memory.md. "
            "Support explicit commands using the /help skill list, and preserve session history for later review."
        )

    @staticmethod
    def _default_memory() -> str:
        return "# Memory\n\nThis file stores persistent memory for the agent across terminal sessions. \n"
