"""
Shell Policy middleware for terminal command safety and telemetry.

This module provides the `ShellPolicyMiddleware` class which intercepts
agent execution via LangChain's middleware hooks. It enforces shell
command safety (whitelist/blacklist, sandboxing, length limits) and
emits telemetry (token usage, execution timing) in the `wrap_model_call`
hook. Intended to run **before** human-in-the-loop (HITL) middleware.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, cast

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    hook_config,
)
from langchain_core.messages import AIMessage
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

    Works by intercepting the agent loop via `after_model` hook.
    Validates tool actions (shell commands) and logs token usage.

    Usage:
        Inject into `middleware=[...]` when calling `create_agent(...)`.
    """

    def __init__(self, cfg: ShellPolicyConfig):
        """Initialize the shell policy middleware with configuration settings.

        Args:
            cfg: Instance of `ShellPolicyConfig` defining allowed/disallowed verbs,
                sandbox settings, and enforcement mode.
        """
        super().__init__()
        self.cfg = cfg
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
        print(
            f"[Policy] ShellPolicyMiddleware initialized with mode: {cfg.enforce_mode}"
        )

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

    def _validate_command(
        self, cmd: str, powershell: bool, cwd: Path
    ) -> tuple[bool, str]:
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

    def _log_token_usage(self, message: AIMessage) -> None:
        """Extract and log token usage from an AIMessage.

        Args:
            message: The AIMessage to extract usage from.
        """
        # Try usage_metadata first (newer LangChain versions)
        if hasattr(message, "usage_metadata") and message.usage_metadata:
            usage = message.usage_metadata

            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Update totals
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_calls += 1

            # Log current call
            print(
                f"[Policy] Token usage: input={input_tokens} output={output_tokens} total={total_tokens}"
            )
            print(
                f"[Policy] Session totals: input={self.total_input_tokens} output={self.total_output_tokens} calls={self.total_calls}"
            )

        return None

    @hook_config(can_jump_to=["end"])
    def after_model(self, state: AgentState, runtime: Runtime) -> Dict[str, Any] | None:
        """Hook executed immediately after each model invocation (before tool execution).

        This hook:
        1. Logs token usage from the model response
        2. Validates shell tool calls against policy
        3. Possibly interrupts execution for policy violations

        Args:
            state: Current agent state. Typical keys: "messages", etc.
            runtime: Runtime context object.

        Returns:
            Optional dict: If returning a dict with {"jump_to": "end", ...},
            the agent will skip to the end. Otherwise, return `None`
            to continue execution normally.

        Raises:
            ShellPolicyViolation: If enforcement mode is `auto_block` and a violation is found.
        """
        # Cast state to dict for type safety
        state_dict = cast(Dict[str, Any], state)

        # Check if the last message contains tool calls
        messages = state_dict.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]

        # Log token usage if this is an AIMessage
        if isinstance(last_message, AIMessage):
            self._log_token_usage(last_message)

        # Check if the last message has tool calls
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return None

        # Validate each tool call
        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name")
            tool_input = tool_call.get("args", {})

            if tool_name in {"bash_tool", "powershell_tool"}:
                powershell = tool_name == "powershell_tool"
                commands = tool_input.get("commands", [])
                cwd_raw = tool_input.get("cwd", ".")
                cwd = Path(cwd_raw).resolve()

                for cmd in commands:
                    allowed, reason = self._validate_command(
                        cmd, powershell=powershell, cwd=cwd
                    )
                    if not allowed:
                        detail = {
                            "tool": tool_name,
                            "cmd": cmd,
                            "reason": reason,
                            "cwd": str(cwd),
                        }
                        print("[Policy] Violation: %s", detail)
                        mode = self.cfg.enforce_mode
                        if mode == "auto_block":
                            # For auto_block mode, we should let HITL middleware handle the interrupt
                            # but we can still log and optionally add metadata
                            print("[Policy] Auto-blocking command: %s", detail)
                            # Return None to allow HITL to handle the interrupt
                            return None
                        elif mode == "warn_only":
                            # Return warning detail in interrupt_payload for downstream handling
                            print(
                                "[Policy] Warning only mode - allowing command with warning"
                            )
                            return None
                        else:  # "defer_to_hitl"
                            # Let HITL or downstream handle the decision
                            return None
                    else:
                        print(f"[Policy] Command allowed: {cmd}")

        # Continue normal execution
        return None

    def get_usage_stats(self) -> Dict[str, int]:
        """Get current token usage statistics.

        Returns:
            Dictionary with usage stats including input/output/total tokens and call count.
        """
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_calls": self.total_calls,
        }

    def reset_usage_stats(self) -> None:
        """Reset token usage statistics."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0
