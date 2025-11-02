# 🧠 Terminal Agent

A **safe, human-in-the-loop terminal assistant** capable of executing **Bash** and **PowerShell** commands.
Designed for use with [LangChain](https://www.langchain.com/) and [LangGraph](https://github.com/langchain-ai/langgraph), it brings LLM reasoning, guardrails, and human oversight to real shell execution.

---

## 🚀 Features

- ✅ **Cross-Shell Execution** – Runs both **Bash** (Linux/macOS) and **PowerShell** (Windows) commands.
- 🧩 **Policy-Governed Safety** – Validates every command against an allow/deny list before execution.
- 🧠 **LLM Integration** – Uses OpenAI or Azure OpenAI chat models to interpret user intent and respond safely.
- 👀 **Human-In-The-Loop (HITL)** – Requires approval before executing commands, ensuring full visibility and control.
- 🪄 **Persistent Shell Sessions** – Maintains shell state and working directory across commands using middleware.
- 🛡️ **Sandboxed Execution** – Enforces a root jail defined by `SHELL_ROOT_DIR` for added system safety.
- 🔄 **In-Memory State Management** – Uses LangGraph's checkpointing for conversation persistence.
- ⚙️ **Modular Architecture** – Extensible middleware system for policy enforcement and session management.

---

## 🧱 Architecture Overview

```mermaid
flowchart TB
    %% User Layer
    User["👤 User Input"]
    
    %% Agent Core
    Agent["🧠 LangChain Agent<br/>(LangGraph Runtime)"]
    LLM["🤖 Chat Model<br/>(OpenAI / Azure OpenAI)"]
    
    %% Configuration
    Config["⚙️ AppConfig<br/>(from .env)"]
    Policy["🛡️ Policy Settings<br/>- Allowed Commands<br/>- Dangerous Commands<br/>- Root Directory<br/>- Enforce Mode"]
    
    %% Middleware Stack
    SessionMW["🔄 Session Middleware<br/>- Persistent Shell Process<br/>- State Management<br/>- CWD Tracking"]
    PolicyMW["🔒 Policy Middleware<br/>- Command Validation<br/>- Sandbox Enforcement<br/>- Token Telemetry"]
    HITLMW["👀 HITL Middleware<br/>- Human Approval<br/>- Edit/Reject/Accept"]
    
    %% Tools
    BashTool["⚡ Bash Tool<br/>- Execute Commands<br/>- Persistent CWD<br/>- Root Jail"]
    PowerShellTool["⚡ PowerShell Tool<br/>- Execute Commands<br/>- Persistent CWD<br/>- Root Jail"]
    
    %% State Management
    State["💾 State Checkpointer<br/>(SQLite / In-Memory)"]
    
    %% System Output
    System["💻 System Execution<br/>(Bash / PowerShell)"]
    Output["📤 Results & Output"]
    
    %% Flow connections
    User -->|"Request"| Agent
    Config -->|"Load Settings"| Agent
    Config -->|"Provide Policy"| Policy
    Policy -->|"Configure"| PolicyMW
    Policy -->|"Configure"| SessionMW
    
    Agent -->|"Generate Response"| LLM
    LLM -->|"Tool Selection"| Agent
    
    Agent -->|"Tool Call"| SessionMW
    SessionMW -->|"Validate Command"| PolicyMW
    PolicyMW -->|"Validate Command"| HITLMW
    PolicyMW -.->|"Policy Violation"| User
    
    HITLMW -->|"Request Approval"| User
    User -.->|"Approve/Edit/Reject"| HITLMW
    
    HITLMW -->|"Approved"| BashTool
    HITLMW -->|"Approved"| PowerShellTool
    
    BashTool -->|"Execute"| System
    PowerShellTool -->|"Execute"| System
    
    System -->|"stdout/stderr"| BashTool
    System -->|"stdout/stderr"| PowerShellTool
    
    BashTool -->|"Results"| Agent
    PowerShellTool -->|"Results"| Agent
    
    Agent <-->|"Save/Load State"| State
    Agent -->|"Final Response"| Output
    Output -->|"Display"| User
    
    %% Styling
    classDef userClass fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef agentClass fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef configClass fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef middlewareClass fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef toolClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef stateClass fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef systemClass fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    
    class User,Output userClass
    class Agent,LLM agentClass
    class Config,Policy configClass
    class SessionMW,PolicyMW,HITLMW middlewareClass
    class BashTool,PowerShellTool toolClass
    class State stateClass
    class System systemClass
```

---

## ⚙️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/eosho/langchain_terminal_agent
cd langchain_terminal_agent
````

### 2. Install dependencies

Using [Poetry](https://python-poetry.org/):

```bash
poetry install
```

Or using `pip` directly:

```bash
pip install -r requirements.txt
```

### 3. Copy environment variables

```bash
cp .env.sample .env
```

### 4. Configure `.env`

Edit your `.env` file to include model credentials and shell root directory:

```bash
# LLM Provider Configuration
LLM_PROVIDER=azure_openai  # or "openai"
MODEL_NAME=gpt-4o-mini
MODEL_TEMPERATURE=0.0
MODEL_MAX_TOKENS=4096

# Azure OpenAI Configuration (if using azure_openai provider)
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# OpenAI Configuration (if using openai provider)
OPENAI_API_KEY=sk-your-api-key

# Terminal Agent Settings
SHELL_ROOT_DIR=tmp/workspace  # Sandbox directory
LOG_LEVEL=INFO
```

---

## 🧩 Configuration Overview

| Variable                    | Description                                  | Default               |
| ---------------------------- | -------------------------------------------- | --------------------- |
| `LLM_PROVIDER`              | LLM backend: `openai` or `azure_openai`     | `openai`              |
| `MODEL_NAME`                | Model name or deployment ID                 | `gpt-4o-mini`         |
| `MODEL_TEMPERATURE`         | Sampling temperature for creativity         | `0.0`                 |
| `MODEL_MAX_TOKENS`          | Maximum number of output tokens             | `4096`                |
| `OPENAI_API_KEY`            | OpenAI API key (if using openai provider)   | None                  |
| `AZURE_OPENAI_ENDPOINT`     | Azure OpenAI endpoint URL                   | None                  |
| `AZURE_OPENAI_API_KEY`      | Azure OpenAI API key                        | None                  |
| `AZURE_OPENAI_API_VERSION`  | Azure OpenAI API version                    | None                  |
| `AZURE_OPENAI_DEPLOYMENT`   | Azure OpenAI deployment name                | None                  |
| `SHELL_ROOT_DIR`            | Root directory jail for shell execution     | `tmp/workspace`       |
| `LOG_LEVEL`                 | Logging verbosity (`DEBUG`, `INFO`, `WARN`) | `INFO`                |

---

## 🧠 Usage Examples

### Run a basic Bash command

```python
from terminal_agent.tools.shell.bash import bash_tool
from terminal_agent.core.config import AppConfig

cfg = AppConfig.from_env()

# Direct tool invocation (bypasses HITL)
result = bash_tool(
    commands=["pwd", "ls -la"],
    cwd=str(cfg.shell_policy.root_dir),
)

print(result)
```

### Run PowerShell commands

```python
from terminal_agent.tools.shell.powershell import powershell_tool
from terminal_agent.core.config import AppConfig

cfg = AppConfig.from_env()

# Direct tool invocation (bypasses HITL)
result = powershell_tool(
    commands=["Get-Location", "Get-Date"],
    cwd=str(cfg.shell_policy.root_dir),
)

print(result)
```

### Use with LangChain Agent

```python
from terminal_agent.builder import build_agent
import asyncio

async def main():
    agent = await build_agent(shell_type="bash")  # or "powershell"
    config = {"configurable": {"thread_id": "1"}}
    
    # Interactive mode with human-in-the-loop approval
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Show me the current directory and list its files."}]},
        config=config
    )
    print(result)

asyncio.run(main())
```

---

## 🧰 Development

### Code formatting

```bash
# Using black for code formatting
python -m black .

# Using isort for import sorting  
python -m isort .
```

### Run tests

```bash
# Run all tests
python -m pytest -v

# Run with coverage
python -m pytest --cov=terminal_agent tests/
```

### Lint

```bash
# Check code style
python -m flake8 src/terminal_agent

# Type checking
python -m mypy src/terminal_agent
```

### Local Development Setup

```bash
# Install in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt  # if available

# Run the interactive CLI for testing
python main.py
```

---

## 🔐 Safety Notes

* All command executions are **guarded by `ShellPolicyMiddleware`**.
* Commands are validated against explicit **allow** and **deny** lists.
* `SHELL_ROOT_DIR` defines the safe sandbox — no command can escape it.
* Destructive operations (`rm -rf`, `shutdown`, `format-volume`, etc.) are always blocked.
* **Human-In-The-Loop (HITL) middleware** requires user approval before any real command runs.
* **Persistent shell sessions** are managed safely with automatic cleanup.
* All command outputs are captured and returned safely without system exposure.

---

## 🧩 Project Structure

```txt
langchain_terminal_agent/
├── src/
│   └── terminal_agent/
│       ├── __init__.py
│       ├── builder.py           # Agent builder factory
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py        # LLM + policy configuration
│       │   ├── logging.py       # Logging configuration
│       │   └── state.py         # Agent state configuration
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py          # LLM factory and provider interface
│       │   └── provider.py      # OpenAI and Azure OpenAI providers
│       ├── middleware/
│       │   ├── shell_policy.py  # Policy middleware for command validation
│       │   └── shell_session.py # Persistent shell session middleware
│       └── tools/
│           ├── __init__.py
│           └── shell/
│               ├── __init__.py
│               ├── bash.py      # Bash execution tool
│               └── powershell.py# PowerShell execution tool
├── tmp/
│   └── workspace/               # Default sandbox directory
│       ├── data/
│       ├── config/
│       ├── docs/
│       └── scripts/
├── main.py                      # Entry point for local testing
├── requirements.txt
├── Makefile
├── .env                         # Environment configuration
├── .env.sample                  # Environment template
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🧠 Example Policy Rules

The agent uses configurable allow/deny lists for both Bash and PowerShell commands:

```python
allowed_bash_commands = ["ls", "cat", "pwd", "echo", "mkdir"]
dangerous_bash_commands = ["rm", "mv", "shutdown", "reboot"]

allowed_powershell_commands = ["Get-ChildItem", "Set-Location", "Get-Process"]
dangerous_powershell_commands = ["Remove-Item", "Stop-Computer"]
```

---

## 🧑‍💻 Contributing

Pull requests are welcome!
If you find bugs, open an issue with clear reproduction steps.

### Local Development

```bash
poetry install --with dev
pre-commit install
```

---

## 🪪 License

This project is licensed under the **MIT License**.
See [`LICENSE`](LICENSE) for details.
