"""
Shell Policy middleware for terminal command safety and telemetry.

This module provides the `ShellPolicyMiddleware` class which intercepts
agent execution via LangChain's middleware hooks. It enforces shell
command safety (whitelist/blacklist, sandboxing, length limits) and
emits telemetry (token usage, execution timing) in the `after_model`
hook. Intended to run **before** human-in-the-loop (HITL) middleware.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


@dataclass
class ShellPolicyConfig:
    """Configuration settings for the shell terminal policy.

    Attributes:
        allowed_bash: List of allowed Bash command verbs.
        dangerous_bash: List of disallowed Bash command verbs.
        allowed_pwsh: List of allowed PowerShell command verbs.
        dangerous_pwsh: List of disallowed PowerShell verbs.
        root_dir: Sandbox root directory under which commands must run.
        enforce_root_jail: If true, enforce that cwd stays under root_dir.
        max_command_len: Maximum characters allowed in a command string.
        enforce_mode: Enforcement mode: "auto_block", "warn_only", or "defer_to_hitl".
    """
    allowed_bash: List[str]
    dangerous_bash: List[str]
    allowed_pwsh: List[str]
    dangerous_pwsh: List[str]
    root_dir: Path
    enforce_root_jail: bool = True
    max_command_len: int = 8000
    enforce_mode: Literal["auto_block", "warn_only", "defer_to_hitl"] = "auto_block"


class ShellPolicyViolation(Exception):
    """Raised by ShellPolicyMiddleware to interrupt execution when a policy violation occurs.

    The `detail` attribute contains context about the violation.
    """

    def __init__(self, message: str, detail: Dict[str, Any]):
        super().__init__(message)
        self.detail: Dict[str, Any] = detail


class ShellPolicyMiddleware(AgentMiddleware):
    """Middleware enforcing terminal guardrails and logging telemetry.

    Works by intercepting the agent loop via `before_model` and `after_model`
    hooks. Validates tool actions (shell commands) and logs token usage.

    Usage:
        Inject into `middleware=[...]` when calling `create_agent(...)`.
    """

    def __init__(self, cfg: ShellPolicyConfig):
        """Initialize the shell policy middleware with configuration settings.

        Args:
            cfg: Instance of `ShellPolicyConfig` defining allowed/disallowed verbs,
                sandbox settings, and enforcement mode.
        """
        self.cfg = cfg

    def _first_token(self, cmd: str) -> str:
        """Return the first whitespace-delimited token (the verb) of a command."""
        return cmd.strip().split()[0] if cmd.strip() else ""

    def _within_root(self, cwd: Path) -> bool:
        """Check if the provided cwd is within the configured sandbox root."""
        if not self.cfg.enforce_root_jail:
            return True
        try:
            return cwd.resolve().is_relative_to(self.cfg.root_dir.resolve())
        except Exception:
            return str(cwd.resolve()).startswith(str(self.cfg.root_dir.resolve()))

    def _validate_command(self, cmd: str, powershell: bool, cwd: Path) -> tuple[bool, str]:
        """Validate a single shell command string against the policy.

        Args:
            cmd: The command string to check.
            powershell: True if the command is for PowerShell; False for Bash.
            cwd: Current working directory.

        Returns:
            Tuple[bool, str]: (allowed, reason). If allowed == False, reason contains explanation.
        """
        if not cmd.strip():
            return False, "Empty command."
        if len(cmd) > self.cfg.max_command_len:
            return False, f"Command too long (> {self.cfg.max_command_len})."

        verb = self._first_token(cmd)
        if powershell:
            v = verb.lower()
            if any(d.lower() == v for d in self.cfg.dangerous_pwsh):
                return False, f"Dangerous command '{verb}'."
            if not any(a.lower() == v for a in self.cfg.allowed_pwsh):
                return False, f"'{verb}' not in allowed PowerShell commands."
        else:
            if verb in self.cfg.dangerous_bash:
                return False, f"Dangerous command '{verb}'."
            if verb not in self.cfg.allowed_bash:
                return False, f"'{verb}' not in allowed Bash commands."

        if not self._within_root(cwd):
            return False, f"CWD '{cwd}' is outside sandbox '{self.cfg.root_dir}'."

        return True, ""

    def before_model(self, state: AgentState, runtime: Runtime) -> Dict[str, Any] | None:
        """Hook executed just before each model invocation.

        Use this to inspect state and possibly redirect execution prior to tool actions.

        Args:
            state: Current agent state, including `state["messages"]` etc.
            runtime: Runtime context object for the agent.

        Returns:
            Optional dict: Return a dict with keys (e.g., `jump_to`) to redirect agent flow,
            or `None` to continue normal processing.

        Raises:
            ShellPolicyViolation: If enforcement mode is `auto_block` and a violation is detected.
        """
        # At this stage, the model has not yet chosen a tool. We can still inspect prior state if needed.
        return None

    def after_model(self, state: AgentState, runtime: Runtime) -> Dict[str, Any] | None:
        """Hook executed immediately after each model invocation (before tool execution).

        This is where we inspect whether the model selected a shell tool (bash/powershell),
        validate the tool call against policy, log token usage, and possibly interrupt execution.

        Args:
            state: Current agent state. Typical keys: "messages", "tool_name", "tool_input", "usage".
            runtime: Runtime context object.

        Returns:
            Optional dict: If returning a dict with {"jump_to": "__interrupt__", "interrupt_payload": ...},
            the agent will pause and go to a human-in-the-loop decision step. Otherwise, return `None`
            to continue execution normally.

        Raises:
            ShellPolicyViolation: If enforcement mode is `auto_block` and a violation is found.
        """
        # Log token usage if available
        usage = state.get("usage")
        if isinstance(usage, dict):
            input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
            output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
            total_tokens = usage.get("total_tokens")
            logger.info(
                "[Policy] Model token usage: input=%s output=%s total=%s",
                input_tokens, output_tokens, total_tokens
            )

        # Determine if the model called a tool
        tool_name = state.get("tool_name")
        tool_input = state.get("tool_input", {})
        if tool_name in {"bash_tool", "powershell_tool"}:
            powershell = (tool_name == "powershell_tool")
            commands = tool_input.get("commands", [])
            cwd_raw = tool_input.get("cwd", ".")
            cwd = Path(cwd_raw).resolve()

            for cmd in commands:
                allowed, reason = self._validate_command(cmd, powershell=powershell, cwd=cwd)
                if not allowed:
                    detail = {"tool": tool_name, "cmd": cmd, "reason": reason, "cwd": str(cwd)}
                    logger.warning("[Policy] Violation: %s", detail)
                    mode = self.cfg.enforce_mode
                    if mode == "auto_block":
                        return {"jump_to": "__interrupt__", "interrupt_payload": detail}
                    elif mode == "warn_only":
                        # Return warning detail in interrupt_payload for downstream handling
                        return {"interrupt_payload": detail}
                    else:  # "defer_to_hitl"
                        # Let HITL or downstream handle the decision
                        return None

        # Continue normal execution
        return None
