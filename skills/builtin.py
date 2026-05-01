from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class SkillDefinition:
    name: str
    description: str
    usage: str


def get_builtin_skills() -> List[SkillDefinition]:
    return [
        SkillDefinition("agent", "Invoke a specialized sub-agent for a task.", "/agent [agent_name] [task...]"),
        SkillDefinition("init", "Initialize the project with an OCTO.md file.", "/init"),
        SkillDefinition("help", "Show available built-in commands.", "/help"),
        SkillDefinition("model", "View or change the current model.", "/model [model_name]"),
        SkillDefinition("models", "Search or list available models.", "/models [search_query]"),
        SkillDefinition("clear", "Clear the terminal screen.", "/clear"),
        SkillDefinition("memory", "Display the contents of memory.md.", "/memory"),
        SkillDefinition("save", "Save the current conversation to a file.", "/save [filename]"),
        SkillDefinition("summary", "Ask the agent to summarize the conversation.", "/summary"),
        SkillDefinition("compact", "Compress conversation history to save context.", "/compact"),
        SkillDefinition("doctor", "Diagnose environment and configuration.", "/doctor"),
        SkillDefinition("reload", "Reload soul.md, agent.md, and memory.md.", "/reload"),
        SkillDefinition("debug", "Show API endpoint and request diagnostics.", "/debug"),
        SkillDefinition("cron", "Manage scheduled cron jobs.", "/cron [list|add|remove|toggle]"),
        SkillDefinition("heartbeat", "Show current agent health snapshot.", "/heartbeat"),
        SkillDefinition("mcp", "View MCP server connection status.", "/mcp"),
        SkillDefinition("mpc", "Run multi-agent pipelines or debates.", "/mpc [list|pipeline|debate]"),
        SkillDefinition("skills", "Search, list, or reload modular skills.", "/skills [search|list|reload]"),
        SkillDefinition("exit", "Exit the terminal app.", "/exit"),
        SkillDefinition("quit", "Exit the terminal app.", "/quit"),
    ]
