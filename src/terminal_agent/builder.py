"""
Agent builder.

This module exposes a single factory function, :func:`build_agent`, which
constructs a LangChain agent capable of executing validated shell commands
(Bash and PowerShell).

Shell operations require explicit human approval via a Human-In-The-Loop (HITL)
middleware configuration.

Model/provider settings are injected from environment variables
via :class:`terminal_agent.core.config.AppConfig`.
"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

from terminal_agent.core.config import AppConfig
from terminal_agent.llm.base import get_llm
from terminal_agent.middleware.shell_policy import (
    ShellPolicyConfig,
    ShellPolicyMiddleware,
)
from terminal_agent.middleware.shell_session import (
    ShellSessionConfig,
    ShellSessionMiddleware,
)
from terminal_agent.tools.shell.bash import bash_tool
from terminal_agent.tools.shell.powershell import powershell_tool


async def build_agent(shell_type) -> Any:
    """Construct a shell execution agent for the specified shell type.

    This factory asynchronously builds a LangChain agent configured for either
    Bash or PowerShell, depending on ``shell_type``. The agent includes shell
    execution tools, middleware for policy enforcement and human-in-the-loop
    approvals, and a checkpointer for maintaining agent state between runs.

    Args:
        shell_type (str): The shell environment to use, one of ``"bash"`` or
            ``"powershell"``. Determines which tool is loaded and how commands
            are validated and executed.

    Returns:
        Any: A fully configured LangChain agent ready for invocation.

    Raises:
        ValueError: If ``shell_type`` is not one of the supported options.

    Example:
        ```python
        agent = await build_agent(shell_type="bash")
        result = await agent.ainvoke("List files in the current directory")
        print(result)
        ```
    """
    cfg = AppConfig.from_env()

    llm = get_llm(cfg.llm.provider.value, temperature=cfg.llm.temperature)

    # Assemble tools: shell tools (require HITL).
    tools: list[BaseTool] = [
        bash_tool,
        powershell_tool,
    ]

    # Agent definition
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=cfg.system_prompt,
        checkpointer=InMemorySaver(),
        middleware=[
            ShellSessionMiddleware(
                ShellSessionConfig(
                    shell_type=shell_type,
                    startup_cwd=cfg.shell_policy.root_dir,
                    read_timeout_sec=5.0,
                    startup_cmds=["echo Session started"],
                )
            ),
            ShellPolicyMiddleware(
                ShellPolicyConfig(
                    allowed_bash=cfg.shell_policy.allowed_bash_commands,
                    dangerous_bash=cfg.shell_policy.dangerous_bash_commands,
                    allowed_pwsh=cfg.shell_policy.allowed_powershell_commands,
                    dangerous_pwsh=cfg.shell_policy.dangerous_powershell_commands,
                    root_dir=cfg.shell_policy.root_dir,
                    enforce_root_jail=cfg.shell_policy.enforce_root_jail,
                    max_command_len=cfg.shell_policy.max_command_len,
                    enforce_mode="auto_block",
                )
            ),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    # Require human approval before executing shell commands
                    "bash_tool": {"allowed_decisions": ["approve", "reject"]},
                    "powershell_tool": {"allowed_decisions": ["approve", "reject"]},
                }
            ),
        ],
    )

    return agent
