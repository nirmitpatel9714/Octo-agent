"""
Octo Agent — MPC (Multi-Party Chat) Orchestration
===================================================
Orchestrates multiple specialized agents working together on a task.
Supports pipeline mode (sequential) and debate mode (parallel + judge).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.openrouter import OpenRouterClient


@dataclass
class MPCAgent:
    name: str
    role: str
    system_prompt: str


@dataclass
class MPCResult:
    agent: str
    content: str
    step: int


class MPCOrchestrator:
    """Run multi-agent workflows: pipeline or debate."""

    def __init__(self, client: OpenRouterClient, root_path: Path):
        self.client = client
        self.root_path = root_path
        self._agents: Dict[str, MPCAgent] = {}
        self._load_agents()

    def _load_agents(self) -> None:
        agents_dir = self.root_path / "agents"
        if not agents_dir.exists():
            return
        for f in agents_dir.glob("*.md"):
            content = f.read_text(encoding="utf-8")
            self._agents[f.stem] = MPCAgent(
                name=f.stem,
                role=f.stem,
                system_prompt=content,
            )

    def create_pipeline(self, agent_names: List[str], task: str) -> List[MPCResult]:
        """Sequential pipeline: each agent builds on the previous output."""
        results: List[MPCResult] = []
        current_input = task

        for step, name in enumerate(agent_names):
            agent = self._agents.get(name)
            if not agent:
                results.append(MPCResult(agent=name, content=f"Error: Agent '{name}' not found", step=step))
                continue

            messages = [
                {"role": "system", "content": agent.system_prompt},
                {"role": "user", "content": current_input},
            ]

            try:
                response = self.client.chat(messages, max_tokens=2000)
                results.append(MPCResult(agent=name, content=response, step=step))
                # Feed output to next agent
                current_input = (
                    f"Previous agent ({name}) output:\n{response}\n\n"
                    f"Original task: {task}\n\n"
                    f"Please build on the above and continue."
                )
            except Exception as exc:
                results.append(MPCResult(agent=name, content=f"Error: {exc}", step=step))
                break

        return results

    def create_debate(self, agent_names: List[str], task: str, rounds: int = 2) -> List[MPCResult]:
        """Debate mode: agents each respond, then see each other's responses for multiple rounds."""
        results: List[MPCResult] = []
        step = 0
        all_responses: Dict[str, str] = {}

        for round_num in range(rounds):
            for name in agent_names:
                agent = self._agents.get(name)
                if not agent:
                    continue

                if round_num == 0:
                    prompt = task
                else:
                    others = "\n\n".join(
                        f"**{n}** said:\n{r}" for n, r in all_responses.items() if n != name
                    )
                    prompt = (
                        f"Original task: {task}\n\n"
                        f"Other agents' responses:\n{others}\n\n"
                        f"Please provide your updated response considering the above."
                    )

                messages = [
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": prompt},
                ]

                try:
                    response = self.client.chat(messages, max_tokens=2000)
                    all_responses[name] = response
                    results.append(MPCResult(agent=name, content=response, step=step))
                except Exception as exc:
                    results.append(MPCResult(agent=name, content=f"Error: {exc}", step=step))
                step += 1

        return results

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def save_session(self, results: List[MPCResult], filename: str = "") -> Path:
        if not filename:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"mpc_session_{ts}.json"
        path = self.root_path / "chats" / filename
        data = [{"agent": r.agent, "content": r.content, "step": r.step} for r in results]
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path
