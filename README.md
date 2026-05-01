# 🐙 Octo Agent Terminal UI

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

**Octo Agent** is a powerful, terminal-first AI assistant powered by OpenRouter. It features an advanced modular skill system, persistent memory, and multi-agent orchestration capabilities.

---

## ✨ Features

- 🖥️ **Cross-Platform**: Works seamlessly on Windows, Linux, and macOS.
- 🧠 **OpenRouter Integration**: Access 100+ AI models with ease.
- 🛠️ **Advanced Skill System**: 
  - **Recursive Skills**: Supports nested modular skills (e.g., `github-pr`, `web-dev-react`).
  - **Auto-Discovery**: Agent can discover and use its own skills dynamically.
  - **Easy Creation**: Create new skills on the fly with the `/skills` system.
- 💾 **Persistent Memory**: Retains context across sessions via `memory.md`.
- 🤖 **Multi-Agent Orchestration**: Run pipelines or debates between specialized sub-agents.
- 🧹 **Clean Terminal UI**: Modern, aesthetic interface with command history and tab completion.

## 🚀 Installation

1. **Prerequisites**: Ensure you have **Python 3.10** or higher.
2. **Install Dependencies**:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. **Setup**: Run the onboarding wizard:
   ```bash
   python main.py onboard
   ```

## 💻 Usage

Start the agent:
```bash
python main.py
```

## ⌨️ Essential Commands

- `/help` — 📖 Show available commands
- `/skills` — 🛠️ Search and manage modular skills (e.g., `/skills search github`)
- `/memory` — 🧠 Display the agent's long-term memory
- `/agent` — 🤖 Invoke a specialized sub-agent
- `/mpc` — 🔀 Run multi-agent pipelines or debates
- `/clear` — 🧹 Clear the terminal screen
- `/reload` — 🔄 Refresh configuration and skills
- `/exit` — 🚪 Close the application

## 📂 Project Structure

- `agents/`: Definitions for specialized sub-agents.
- `skills/`: Modular prompt-based skills (includes 100+ Hermes Agent skills).
- `soul.md`: Core personality and behavior guidelines.
- `agent.md`: Technical instructions and metadata.
- `memory.md`: Persistent knowledge storage.

---
*Octo Agent: The terminal assistant that grows with you.*
