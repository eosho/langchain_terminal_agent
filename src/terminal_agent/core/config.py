"""
Configuration module for the Terminal Agent.

This module defines the core configuration dataclasses used across the system:
- LLM configuration (provider, model, temperature, etc.)
- Static policy settings (command allow/deny lists, sandbox root, and safety limits)
- AppConfig, which aggregates both and provides easy access to system prompts
  and provider-specific model parameters.

At runtime, ShellPolicySettings is consumed by the ShellPolicyMiddleware, which enforces
these constraints before any shell command is executed.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()


class LLMProvider(str, Enum):
    """Enumerates supported Large Language Model providers."""

    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"


@dataclass
class LLMConfig:
    """Configuration for the LLM provider and model behavior.

    Values are read from environment variables and exposed via helpers that
    can be passed directly to your model client.

    Attributes:
        provider: Selected LLM provider (``openai`` or ``azure_openai``).
        model: Model name (or Azure deployment id).
        temperature: Sampling temperature for generations.
        max_tokens: Optional cap for response tokens.
        openai_api_key: API key for OpenAI (when provider is ``openai``).
        azure_endpoint: Azure OpenAI endpoint URL.
        azure_api_key: Azure OpenAI API key.
        azure_api_version: Azure OpenAI API version string.
        azure_deployment: Azure OpenAI deployment (falls back to ``model`` if unset).
        langsmith_enabled: Whether to enable LangSmith tracing.
        langsmith_tracing: Whether to enable detailed LangSmith tracing.
        langsmith_api_key: API key for LangSmith.
        otel_exporter_otlp_endpoint: OTLP endpoint for OpenTelemetry exporter.
    """

    provider: LLMProvider = LLMProvider(os.getenv("LLM_PROVIDER", "openai"))

    model: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
    temperature: float = float(os.getenv("MODEL_TEMPERATURE", "0.0"))
    max_tokens: Optional[int] = int(os.getenv("MODEL_MAX_TOKENS", 4096))

    # OpenAI
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")

    # Azure OpenAI
    azure_endpoint: Optional[str] = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_api_key: Optional[str] = os.getenv("AZURE_OPENAI_API_KEY")
    azure_api_version: Optional[str] = os.getenv("AZURE_OPENAI_API_VERSION")
    azure_deployment: Optional[str] = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    # Tracing
    langsmith_enabled: bool = (
        os.getenv("LANGSMITH_OTEL_ENABLED", "false").lower() == "true"
    )
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    langsmith_api_key: Optional[str] = os.getenv("LANGSMITH_API_KEY")
    otel_exporter_otlp_endpoint: Optional[str] = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )


@dataclass
class ShellPolicySettings:
    """Static shell policy configuration for terminal safety and assistant guidance.

    This class defines whitelisted and blacklisted command verbs for both Bash
    and PowerShell environments, as well as sandbox settings and limits used by
    the ShellPolicyMiddleware. It also generates the base system prompt describing
    expected agent behavior.

    Attributes:
        allowed_bash_commands: Whitelist of allowed Bash verbs.
        dangerous_bash_commands: List of disallowed Bash verbs.
        allowed_powershell_commands: Whitelist of allowed PowerShell verbs.
        dangerous_powershell_commands: List of disallowed PowerShell verbs.
        root_dir: Root directory of the sandbox/jail.
        enforce_root_jail: Whether to enforce that CWD stays under ``root_dir``.
        max_command_len: Maximum permitted command length (characters).
    """

    allowed_bash_commands: List[str] = field(
        default_factory=lambda: [
            "cd",
            "cp",
            "ls",
            "cat",
            "find",
            "touch",
            "echo",
            "grep",
            "pwd",
            "mkdir",
            "wget",
            "sort",
            "head",
            "tail",
            "du",
        ]
    )
    dangerous_bash_commands: List[str] = field(
        default_factory=lambda: [
            "rm",
            "mv",
            "rmdir",
            "sudo",
            "chmod",
            "chown",
            "dd",
            "mkfs",
            "shutdown",
            "reboot",
            "halt",
        ]
    )
    allowed_powershell_commands: List[str] = field(
        default_factory=lambda: [
            "Get-ChildItem",
            "Set-Location",
            "Get-Content",
            "Select-String",
            "Copy-Item",
            "New-Item",
            "Get-Process",
            "Get-Service",
            "Get-Date",
            "Invoke-WebRequest",
            "Sort-Object",
            "Measure-Object",
        ]
    )
    dangerous_powershell_commands: List[str] = field(
        default_factory=lambda: [
            "Remove-Item",
            "Stop-Process",
            "Restart-Computer",
            "Stop-Computer",
            "Set-ExecutionPolicy",
            "Invoke-Expression",
            "Invoke-Command",
            "New-Service",
            "Remove-Service",
            "Format-Volume",
            "New-LocalUser",
            "Remove-LocalUser",
        ]
    )

    root_dir: Path = field(
        default_factory=lambda: Path(os.getenv("SHELL_ROOT_DIR", Path.cwd()))
    )
    enforce_root_jail: bool = True
    max_command_len: int = 8000

    @property
    def system_prompt(self) -> str:
        """Render the system prompt guiding the terminal assistant."""
        return f"""
You are a cross-platform terminal assistant capable of reasoning about both Bash (Linux/macOS) and PowerShell (Windows).

Each command you produce will be executed in a new sandboxed process. Shell variables, history, and current working directory are not preserved between calls.

### Shell Detection
- Use PowerShell for Windows-style paths or cmdlets (`Get-`, `Set-`, etc.).
- Use Bash for Unix-style commands (`ls`, `cat`, `/home` paths).
- Default to Bash if unsure.

### Safety and Efficiency Rules
1. Do not run interactive or long-lived processes.
2. Never escalate privileges (`sudo`, `RunAs`, `Set-ExecutionPolicy`).
3. Avoid commands that access or modify files outside the sandbox root.
4. Always quote paths containing spaces.
5. Prefer absolute paths.
6. Chain related operations efficiently using `&&`, `;`, or `|`.

### Available Commands
- Environment: `cd`, `pwd`, `export`, `unset`, `env`
- Filesystem: `ls`, `find`, `mkdir`, `rm`, `cp`, `mv`, `touch`, `chmod`, `chown`
- File viewing: `cat`, `grep`, `head`, `tail`, `diff`, `less`
- Text processing: `awk`, `sed`, `sort`, `uniq`, `wc`
- System info: `ps`, `df`, `free`, `uname`, `whoami`, `date`
- Network: `curl`, `wget`, `ping`, `nc`, `dig`
- Archives: `tar`, `zip`, `unzip`
- Package tools: `pip`, `npm`, `cargo`, etc. (safe install/view only)

PowerShell equivalents (auto-detected):
- `ls` → `Get-ChildItem`
- `cd` → `Set-Location`
- `cat` → `Get-Content`
- `grep` → `Select-String`
- `mkdir` → `New-Item -ItemType Directory`
- `rm` → `Remove-Item -Force`

### Dynamic Execution Policy
You may only execute commands in these allowed lists:
{self.allowed_bash_commands}
{self.allowed_powershell_commands}

Never execute or suggest operations in these dangerous lists:
{self.dangerous_bash_commands}
{self.dangerous_powershell_commands}

If a request violates these constraints, politely refuse.

### Output Contract
- Return combined stdout and stderr.
- Include exit code in metadata when possible.
- Never reveal system internals or sensitive data.
""".strip()


@dataclass
class AppConfig:
    """Aggregate of model and policy configuration for the application.

    Attributes:
        llm: LLM configuration (provider, model, and tuning).
        shell_policy: ShellPolicySettings controlling command safety and assistant guidance.
    """

    llm: LLMConfig = field(default_factory=LLMConfig)
    shell_policy: ShellPolicySettings = field(default_factory=ShellPolicySettings)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Construct an AppConfig instance from environment variables.

        Returns:
            AppConfig: A configuration object with defaults resolved from
            the current process environment.
        """
        return cls()

    @property
    def system_prompt(self) -> str:
        """Expose the system prompt derived from the active policy."""
        return self.shell_policy.system_prompt
