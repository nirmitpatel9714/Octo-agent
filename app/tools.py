"""
Octo Agent — Tool Registry & Execution Layer
=============================================
Defines every tool the agent can call and a registry that manages
discovery, schema export, and safe execution.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ── Risk levels ──────────────────────────────────────────────────────

class Risk:
    READ = "read"          # no side-effects
    WRITE = "write"        # creates / modifies files
    EXECUTE = "execute"    # runs arbitrary shell commands


# ── Tool descriptor ──────────────────────────────────────────────────

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., str]
    risk: str = Risk.READ
    icon: str = "🔧"


# ── Tool Registry ────────────────────────────────────────────────────

class ToolRegistry:
    """Central registry of all tools available to the agent."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def openai_schemas(self) -> List[Dict[str, Any]]:
        """Export every tool as an OpenAI function-calling schema."""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def execute(self, name: str, arguments: Dict[str, Any], cwd: str = ".") -> str:
        spec = self._tools.get(name)
        if spec is None:
            return f"Error: Unknown tool '{name}'"
        try:
            return spec.handler(cwd=cwd, **arguments)
        except TypeError as exc:
            return f"Error: Bad arguments for '{name}': {exc}"
        except Exception as exc:
            return f"Error executing '{name}': {exc}"


# ── Tool implementations ─────────────────────────────────────────────

def _read_file(*, path: str, cwd: str = ".") -> str:
    resolved = Path(cwd, path).resolve()
    if not resolved.exists():
        return f"Error: File not found: {resolved}"
    if not resolved.is_file():
        return f"Error: Not a file: {resolved}"
    try:
        content = resolved.read_text(encoding="utf-8")
        lines = content.splitlines()
        cap = 500
        numbered = "\n".join(f"{i+1:4d} | {l}" for i, l in enumerate(lines[:cap]))
        suffix = f" (showing first {cap})" if len(lines) > cap else ""
        return f"File: {resolved} ({len(lines)} lines{suffix})\n\n{numbered}"
    except UnicodeDecodeError:
        return f"Error: Cannot read binary file: {resolved}"


def _write_file(*, path: str, content: str, cwd: str = ".") -> str:
    resolved = Path(cwd, path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    lc = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return f"Successfully wrote {lc} lines to {resolved}"


def _edit_file(*, path: str, old_text: str, new_text: str, cwd: str = ".") -> str:
    resolved = Path(cwd, path).resolve()
    if not resolved.exists():
        return f"Error: File not found: {resolved}"
    try:
        original = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: Cannot read binary file: {resolved}"
    if old_text not in original:
        return (
            f"Error: The old_text was not found in {resolved}. "
            "Make sure it matches the file content exactly (including whitespace)."
        )
    count = original.count(old_text)
    updated = original.replace(old_text, new_text, 1)
    resolved.write_text(updated, encoding="utf-8")
    note = f" (Warning: {count} occurrences found, only first replaced)" if count > 1 else ""
    return f"Successfully edited {resolved}{note}"


def _run_command(*, command: str, timeout: int = 120, cwd: str = ".") -> str:
    try:
        result = subprocess.run(
            command, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        out = ""
        if result.stdout:
            out += result.stdout[:8000]
        if result.stderr:
            out += ("\n" if out else "") + result.stderr[:3000]
        if not out:
            out = "(no output)"
        return f"Exit code: {result.returncode}\n{out}"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."


def _list_directory(*, path: str = ".", cwd: str = ".") -> str:
    resolved = Path(cwd, path).resolve()
    if not resolved.exists():
        return f"Error: Directory not found: {resolved}"
    if not resolved.is_dir():
        return f"Error: Not a directory: {resolved}"
    entries = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lines = [f"Directory: {resolved}\n"]
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            lines.append(f"  📁 {entry.name}/")
        else:
            size = entry.stat().st_size
            if size < 1024:
                s = f"{size} B"
            elif size < 1048576:
                s = f"{size/1024:.1f} KB"
            else:
                s = f"{size/1048576:.1f} MB"
            lines.append(f"  📄 {entry.name}  ({s})")
    return "\n".join(lines)


def _search_files(*, pattern: str, path: str = ".", include: str = "", cwd: str = ".") -> str:
    resolved = Path(cwd, path).resolve()
    if not resolved.exists():
        return f"Error: Path not found: {resolved}"
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error:
        compiled = re.compile(re.escape(pattern), re.IGNORECASE)
    results: List[str] = []
    skip = {".git", "__pycache__", "node_modules", ".venv", ".env", "chats"}

    def _walk(dir_path: Path) -> None:
        try:
            for entry in sorted(dir_path.iterdir()):
                if entry.name in skip:
                    continue
                if entry.is_dir():
                    if len(results) >= 50:
                        return
                    _walk(entry)
                elif entry.is_file():
                    if include and not entry.match(include):
                        continue
                    if len(results) >= 50:
                        return
                    try:
                        for i, line in enumerate(
                            entry.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
                        ):
                            if compiled.search(line):
                                results.append(
                                    f"  {entry.relative_to(resolved)}:{i}: {line.strip()}"
                                )
                                if len(results) >= 50:
                                    return
                    except OSError:
                        pass
        except PermissionError:
            pass

    _walk(resolved)
    if not results:
        return f"No matches found for '{pattern}' in {resolved}"
    header = f"Found {len(results)} match(es) for '{pattern}' in {resolved}:\n"
    if len(results) >= 50:
        header += "(capped at 50 results)\n"
    return header + "\n".join(results)


def _core_memory_append(*, content: str, cwd: str = ".") -> str:
    memory_path = Path(cwd, "memory.md").resolve()
    if not memory_path.exists():
        memory_path.write_text("# Memory\n\n", encoding="utf-8")
    
    current = memory_path.read_text(encoding="utf-8")
    updated = current.rstrip() + f"\n\n{content}\n"
    memory_path.write_text(updated, encoding="utf-8")
    return "Successfully appended to memory."


def _core_memory_replace(*, old_content: str, new_content: str, cwd: str = ".") -> str:
    memory_path = Path(cwd, "memory.md").resolve()
    if not memory_path.exists():
        return "Error: memory.md does not exist yet."
    
    current = memory_path.read_text(encoding="utf-8")
    if old_content not in current:
        return "Error: old_content not found in memory. Make sure it matches exactly."
    
    updated = current.replace(old_content, new_content, 1)
    memory_path.write_text(updated, encoding="utf-8")
    return "Successfully replaced content in memory."


def _create_skill(*, name: str, content: str, cwd: str = ".") -> str:
    """Create a new .md skill file in the skills/ directory."""
    # Validate name: alphanumeric, hyphens, underscores only
    clean = name.strip().lower().replace(" ", "-")
    if not re.match(r'^[a-z][a-z0-9_-]*$', clean):
        return (
            "Error: Skill name must start with a lowercase letter and contain only "
            "lowercase letters, digits, hyphens, or underscores."
        )
    if clean in {"__init__", "builtin", "example"}:
        return f"Error: '{clean}' is a reserved name."

    skills_dir = Path(cwd, "skills").resolve()
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skills_dir / f"{clean}.md"

    if skill_path.exists():
        return f"Error: Skill '{clean}' already exists at {skill_path}. Use edit_file to modify it."

    # Ensure the content has a heading
    if not content.strip().startswith("#"):
        content = f"# {clean.replace('-', ' ').title()}\n\n{content}"

    skill_path.write_text(content, encoding="utf-8")
    return (
        f"Successfully created skill '{clean}' at {skill_path}. "
        f"The user can now run it with /{clean}."
    )


def _delete_skill(*, name: str, cwd: str = ".") -> str:
    """Delete a .md skill file from the skills/ directory."""
    clean = name.strip().lower().replace(" ", "-")
    skills_dir = Path(cwd, "skills").resolve()
    skill_path = skills_dir / f"{clean}.md"

    if not skill_path.exists():
        return f"Error: Skill '{clean}' not found at {skill_path}."

    # Protect built-in files
    protected = {"__init__", "builtin"}
    if clean in protected:
        return f"Error: Cannot delete protected file '{clean}'."

    skill_path.unlink()
    return f"Successfully deleted skill '{clean}'."


def _list_reference_docs(*, path: str = ".", cwd: str = ".") -> str:
    """List all .md files in the project with one-line descriptions."""
    resolved = Path(cwd, path).resolve()
    if not resolved.exists():
        return f"Error: Path not found: {resolved}"

    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", ".env", "chats"}
    entries: List[str] = []

    def _first_line(p: Path) -> str:
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith("---"):
                    return s[:120]
        except OSError:
            pass
        return ""

    def _walk(dir_path: Path) -> None:
        try:
            for entry in sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if entry.name in skip_dirs:
                    continue
                if entry.is_dir():
                    _walk(entry)
                elif entry.suffix.lower() == ".md":
                    rel = entry.relative_to(resolved)
                    desc = _first_line(entry)
                    size = entry.stat().st_size
                    line = f"  📄 {rel}  ({size} B)"
                    if desc:
                        line += f"  — {desc}"
                    entries.append(line)
        except PermissionError:
            pass

    _walk(resolved)
    if not entries:
        return f"No .md files found in {resolved}"
    return f"Reference docs in {resolved} ({len(entries)} files):\n\n" + "\n".join(entries)


def _create_agent(*, name: str, system_prompt: str, cwd: str = ".") -> str:
    """Create a new specialized agent in the agents/ directory."""
    clean = name.strip().lower().replace(" ", "-")
    if not re.match(r'^[a-z][a-z0-9_-]*$', clean):
        return "Error: Agent name must start with a lowercase letter and contain only lowercase letters, digits, hyphens, or underscores."
    
    agents_dir = Path(cwd, "agents").resolve()
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agents_dir / f"{clean}.md"
    
    if agent_path.exists():
        return f"Error: Agent '{clean}' already exists. Use edit_file to modify it."
    
    content = f"# {clean.replace('-', ' ').title()}\n\n{system_prompt}\n"
    agent_path.write_text(content, encoding="utf-8")
    return f"Successfully created agent '{clean}' at {agent_path}. Use /agent {clean} <task> to invoke it."


def _list_agents(*, cwd: str = ".") -> str:
    """List all available specialized agents."""
    agents_dir = Path(cwd, "agents").resolve()
    if not agents_dir.exists():
        return "No agents directory found."
    
    agents = []
    for f in sorted(agents_dir.glob("*.md")):
        # Get first non-heading line as description
        desc = ""
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    desc = line[:100]
                    break
        except OSError:
            pass
        agents.append(f"  🤖 {f.stem}" + (f"  — {desc}" if desc else ""))
    
    if not agents:
        return "No agents found in agents/ directory."
    return f"Available agents ({len(agents)}):\n" + "\n".join(agents)


def _delegate_to_agent(*, agent_name: str, task: str, cwd: str = ".") -> str:
    """Delegate a task to a specialized sub-agent. The sub-agent runs independently and returns its result."""
    agents_dir = Path(cwd, "agents").resolve()
    agent_file = agents_dir / f"{agent_name}.md"
    
    if not agent_file.exists():
        available = [f.stem for f in agents_dir.glob("*.md")] if agents_dir.exists() else []
        return f"Error: Agent '{agent_name}' not found. Available: {', '.join(available) or 'none'}"
    
    agent_prompt = agent_file.read_text(encoding="utf-8")
    return f"[DELEGATE:{agent_name}] Sub-agent '{agent_name}' invoked with task: {task}\nAgent prompt: {agent_prompt}"


def _browse_url(*, url: str, cwd: str = ".") -> str:
    """Fetch and extract text content from a URL."""
    import requests
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "OctoAgent/2.0"})
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        
        if "text/html" in content_type:
            # Simple HTML to text extraction
            text = resp.text
            # Remove script and style tags
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Clean whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            # Limit output
            if len(text) > 5000:
                text = text[:5000] + "\n... (truncated)"
            return f"URL: {url}\n\n{text}"
        else:
            text = resp.text[:5000]
            return f"URL: {url}\nContent-Type: {content_type}\n\n{text}"
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


# ── Build the default registry ───────────────────────────────────────

def build_default_registry() -> ToolRegistry:
    """Create a ToolRegistry pre-loaded with all built-in tools."""
    registry = ToolRegistry()

    registry.register(ToolSpec(
        name="read_file",
        description="Read the contents of a file at the given path. Returns line-numbered content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path to the file."},
            },
            "required": ["path"],
        },
        handler=_read_file,
        risk=Risk.READ,
        icon="📖",
    ))

    registry.register(ToolSpec(
        name="write_file",
        description="Create a new file or overwrite an existing file with the given content.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to write."},
                "content": {"type": "string", "description": "Full content to write to the file."},
            },
            "required": ["path", "content"],
        },
        handler=_write_file,
        risk=Risk.WRITE,
        icon="✏️",
    ))

    registry.register(ToolSpec(
        name="edit_file",
        description=(
            "Make a targeted edit to an existing file by replacing old_text with new_text. "
            "old_text must match the file content exactly. Use read_file first to see the content."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to edit."},
                "old_text": {"type": "string", "description": "Exact text to find and replace."},
                "new_text": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_text", "new_text"],
        },
        handler=_edit_file,
        risk=Risk.WRITE,
        icon="🔧",
    ))

    registry.register(ToolSpec(
        name="run_command",
        description="Execute a shell command and return stdout/stderr. Default timeout: 120s. Use for running scripts, tests, installs, git, etc.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)."},
            },
            "required": ["command"],
        },
        handler=_run_command,
        risk=Risk.EXECUTE,
        icon="⚡",
    ))

    registry.register(ToolSpec(
        name="list_directory",
        description="List files and subdirectories in a directory.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path. Use '.' for current directory."},
            },
            "required": [],
        },
        handler=_list_directory,
        risk=Risk.READ,
        icon="📂",
    ))

    registry.register(ToolSpec(
        name="search_files",
        description="Search for a text or regex pattern across files in a directory. Returns matching lines with file paths and line numbers.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex pattern to search for."},
                "path": {"type": "string", "description": "Directory to search in. Default: current directory."},
                "include": {"type": "string", "description": "Glob filter for files, e.g. '*.py'. Optional."},
            },
            "required": ["pattern"],
        },
        handler=_search_files,
        risk=Risk.READ,
        icon="🔍",
    ))

    registry.register(ToolSpec(
        name="core_memory_append",
        description="Append important facts, user preferences, or task history to the agent's long-term memory (memory.md).",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The text to append to memory."},
            },
            "required": ["content"],
        },
        handler=_core_memory_append,
        risk=Risk.WRITE,
        icon="🧠",
    ))

    registry.register(ToolSpec(
        name="core_memory_replace",
        description="Update existing facts in the agent's long-term memory (memory.md) by replacing old content.",
        parameters={
            "type": "object",
            "properties": {
                "old_content": {"type": "string", "description": "The exact text currently in memory to replace."},
                "new_content": {"type": "string", "description": "The new text to insert in its place."},
            },
            "required": ["old_content", "new_content"],
        },
        handler=_core_memory_replace,
        risk=Risk.WRITE,
        icon="🧠",
    ))

    registry.register(ToolSpec(
        name="create_skill",
        description=(
            "Create a new reusable .md skill in the skills/ directory. "
            "The skill becomes a /slash-command the user can invoke. "
            "The content should be a prompt template that instructs the agent what to do when the skill is triggered. "
            "Good skills are focused, reusable, and include clear instructions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill name (lowercase, hyphens/underscores OK). Becomes the /command name.",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown content for the skill. Should include a heading and clear instructions.",
                },
            },
            "required": ["name", "content"],
        },
        handler=_create_skill,
        risk=Risk.WRITE,
        icon="🛠️",
    ))

    registry.register(ToolSpec(
        name="delete_skill",
        description="Delete a .md skill file from the skills/ directory.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the skill to delete (without .md extension)."},
            },
            "required": ["name"],
        },
        handler=_delete_skill,
        risk=Risk.WRITE,
        icon="🗑️",
    ))

    registry.register(ToolSpec(
        name="list_reference_docs",
        description=(
            "List all .md reference documents in the project with file sizes and one-line descriptions. "
            "Use this to discover available skills, agent definitions, and documentation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to scan. Default: project root."},
            },
            "required": [],
        },
        handler=_list_reference_docs,
        risk=Risk.READ,
        icon="📚",
    ))

    registry.register(ToolSpec(
        name="create_agent",
        description=(
            "Create a new specialized sub-agent in the agents/ directory. "
            "The agent can then be invoked via /agent or delegate_to_agent for focused tasks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Agent name (lowercase, hyphens OK)."},
                "system_prompt": {"type": "string", "description": "The system prompt defining the agent's role and behavior."},
            },
            "required": ["name", "system_prompt"],
        },
        handler=_create_agent,
        risk=Risk.WRITE,
        icon="🤖",
    ))

    registry.register(ToolSpec(
        name="list_agents",
        description="List all available specialized sub-agents with their descriptions.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=_list_agents,
        risk=Risk.READ,
        icon="🤖",
    ))

    registry.register(ToolSpec(
        name="delegate_to_agent",
        description=(
            "Delegate a specific task to a specialized sub-agent. "
            "The sub-agent will run with its own context and return results. "
            "Use this for complex tasks that benefit from specialized focus."
        ),
        parameters={
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name of the agent to delegate to."},
                "task": {"type": "string", "description": "The task description for the sub-agent."},
            },
            "required": ["agent_name", "task"],
        },
        handler=_delegate_to_agent,
        risk=Risk.READ,
        icon="🔀",
    ))

    registry.register(ToolSpec(
        name="browse_url",
        description="Fetch and extract text content from a URL. Useful for reading documentation, APIs, or web pages.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch content from."},
            },
            "required": ["url"],
        },
        handler=_browse_url,
        risk=Risk.READ,
        icon="🌐",
    ))

    def _list_skills_tool(*, cwd: str = ".") -> str:
        skills_dir = Path(cwd, "skills").resolve()
        if not skills_dir.exists():
            return "No skills directory found."
        
        skills = []
        # Built-in skills from builtin.py
        from skills.builtin import get_builtin_skills
        for s in get_builtin_skills():
            skills.append(f"  /{s.name} — {s.description}")
        
        # Markdown skills
        for f in skills_dir.glob("*.md"):
            try:
                name = f.stem.lower()
                if name in {"__init__", "builtin"}: continue
                
                desc = "Custom .md skill"
                for line in f.read_text(encoding="utf-8").strip().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        desc = line[:100]
                        break
                skills.append(f"  /{name} — {desc} (.md)")
            except Exception:
                continue
        
        return f"Available skills ({len(skills)}):\n" + "\n".join(sorted(skills))

    registry.register(ToolSpec(
        name="list_skills",
        description="List all available slash-command skills (built-in and custom .md skills).",
        parameters={"type": "object", "properties": {}},
        handler=_list_skills_tool,
        risk=Risk.READ,
        icon="🛠️",
    ))

    return registry
