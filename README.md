# 🐙 Octo Agent: The Self-Evolving Terminal Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenRouter](https://img.shields.io/badge/AI-OpenRouter-orange.svg)](https://openrouter.ai/)

**Octo Agent** is a state-of-the-art, terminal-first AI assistant designed for high-performance engineering and autonomous task execution. Powered by OpenRouter, it combines a modular skill architecture with persistent memory and multi-agent orchestration to provide a truly agentic command-line experience.

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/nirmitpatel9714/Octo-agent.git
cd Octo-agent

# Install dependencies
pip install -r requirements.txt

# Run the onboarding wizard
python main.py onboard
```

### Launching the Agent
```bash
python main.py
```

---

## ✨ Key Capabilities

### 🧠 Advanced Memory Management
Octo Agent doesn't just chat; it remembers. Using a persistent `memory.md` file, the agent tracks your preferences, project conventions, and past decisions across sessions. Use `/memory` to view current state or `/compact` to summarize history when context runs low.

### 🛠️ Modular Skill System
The agent features a robust `/skills` system. 
- **Core Skills**: 15+ highly optimized prompts for debugging, refactoring, security auditing, and more (located in `skills/*.md`).
- **Hermes Library**: Integrated with 80+ specialized skills from the Hermes Agent ecosystem.
- **On-the-fly Creation**: Use the `create_skill` tool to build new slash commands dynamically during your conversation.

### 🤖 Multi-Agent Orchestration (MPC)
Run complex workflows by orchestrating multiple specialized sub-agents.
- **Pipelines**: Chain agents together (e.g., `Coder -> Reviewer -> Tester`).
- **Debates**: Have two agents argue over a technical decision to find the optimal solution.
- **Delegation**: Sprout independent sub-agents for focused tasks without cluttering your main history.

### 🌐 Real-world Integration
- **Web Browsing**: Fetch and summarize documentation or API references on the fly.
- **MCP Support**: Connect to Model Context Protocol servers for extended toolsets.
- **Filesystem Mastery**: Surgical code edits, recursive directory analysis, and smart file searching.

---

## ⌨️ Command Reference

| Command | Description |
| :--- | :--- |
| `/help` | 📖 Display the command directory |
| `/skills [query]` | 🛠️ Search and manage modular skills |
| `/agent [name] [task]` | 🤖 Invoke a specialized sub-agent |
| `/mpc pipeline [A,B] : [task]` | 🔀 Execute a multi-agent pipeline |
| `/memory` | 🧠 View the agent's long-term memory |
| `/compact` | 📉 Compress history into a dense context summary |
| `/doctor` | 🏥 Diagnose environment and configuration health |
| `/reload` | 🔄 Hot-reload soul, agent, and memory definitions |
| `/exit` | 🚪 Securely close the session |

---

## 📂 Architecture Overview

- **`app/`**: The engine room. Contains the CLI logic, tool registry, and agent state management.
- **`agents/`**: Markdown-based definitions for specialized personas (e.g., `Reviewer`, `SecurityExpert`).
- **`skills/`**: The modular brain. Prompt templates that define how the agent handles specific /slash commands.
- **`soul.md`**: The agent's core personality and behavioral guidelines.
- **`agent.md`**: Technical constraints and operational metadata.

---

## 🤝 Contributing

We welcome contributions! Whether it's adding new skills, improving the core engine, or fixing bugs:
1. Fork the repo.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---

*Built with ❤️ for the terminal-obsessed engineer.*
