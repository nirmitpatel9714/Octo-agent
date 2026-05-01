# Agent Design

Anda Agent is a terminal-first assistant built to support code workflows, creative problem solving, and project memory. It uses OpenRouter as the backend model provider and keeps its own identity files in `soul.md`, `memory.md`, and `agent.md`.

## Design goals

- Keep the UI minimal and keyboard-friendly
- Preserve only important long-term memory in `memory.md`
- Support explicit skill commands for fast workflow control
- Use an OpenRouter API key for model access
- Work on Windows, Linux, and macOS without special dependencies beyond Python
