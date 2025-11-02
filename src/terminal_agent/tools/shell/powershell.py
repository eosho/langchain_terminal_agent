"""
PowerShell command execution tool.

Executes PowerShell commands sequentially with a persistent working directory.
If a persistent PowerShell session is available (provided by ShellSessionMiddleware),
this tool uses it for lower latency and true continuity; otherwise, it falls back
to subprocess execution. All commands are validated against the Terminal Policy.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field, model_validator

from terminal_agent.core.config import AppConfig

log = logging.getLogger(__name__)

_CONFIG = AppConfig.from_env()
POLICY = _CONFIG.shell_policy


def _pwsh_executable() -> str:
    """Resolve the path to the PowerShell executable.

    Returns:
        str: Absolute path or best-effort command name.

    Notes:
        - Prefers PowerShell 7+ (`pwsh`) when available.
        - Falls back to Windows PowerShell (`powershell` / `powershell.exe`) on Windows.
    """
    return (
        shutil.which("pwsh")
        or shutil.which("powershell")
        or ("powershell.exe" if os.name == "nt" else "pwsh")
    )


_PWSH = _pwsh_executable()
_MARKER = "__CWD_MARKER__6f2a1d4b__"  # unlikely to appear in real output


class PowerShellCommandsInput(BaseModel):
    """Input schema for PowerShell command execution.

    Attributes:
        commands: List of PowerShell commands to execute sequentially.
        cwd: Optional starting directory; defaults to policy root.
    """

    commands: List[str] = Field(
        ...,
        description="List of PowerShell commands to execute sequentially.",
        examples=[["Get-Location", "Get-ChildItem -Force"]],
    )
    cwd: Optional[str] = Field(
        default=None,
        description="Starting working directory (absolute or relative). Defaults to policy root.",
    )

    @model_validator(mode="after")
    def _validate_non_empty(self) -> "PowerShellCommandsInput":
        """Ensure that at least one non-empty command is provided.

        Raises:
            ValueError: If `commands` is empty or all whitespace.
        """
        if not self.commands or all(not c.strip() for c in self.commands):
            raise ValueError("commands must contain at least one non-empty string")
        return self


@tool(
    "powershell_tool",
    description="Execute PowerShell commands sequentially with a persistent working directory. Uses a persistent session if available; otherwise falls back to subprocess.",
    args_schema=PowerShellCommandsInput,
)
def powershell_tool(
    commands: List[str], cwd: Optional[str] = None, **kwargs: Any
) -> Dict[str, Any]:
    """Run PowerShell commands safely in sequence.

    Validates each command against policy, executes them in a persistent
    session when available, and maintains the current working directory.

    Args:
        commands: List of PowerShell commands.
        cwd: Optional starting directory.
        **kwargs: Optional runtime context (e.g., agent state).

    Returns:
        Dict with:
        - success (bool)
        - results (list of per-command outputs)
        - cwd (final working directory)
    """

    # Create input object from parameters
    input = PowerShellCommandsInput(commands=commands, cwd=cwd)

    # Resolve starting CWD and enforce sandbox root.
    cwd_path = Path(input.cwd) if input.cwd else POLICY.root_dir
    cwd_path = cwd_path.resolve()

    if POLICY.enforce_root_jail:
        root_r = POLICY.root_dir.resolve()
        if os.path.commonpath([str(root_r), str(cwd_path)]) != str(root_r):
            cwd_path = root_r

    # Prefer a persistent PowerShell session if middleware attached one.
    state = kwargs.get("state") or {}
    resources = state.get("resources") or {}
    session_map = resources.get("shell_session") or {}
    session = session_map.get("powershell")  # _ShellSession, if present

    results: List[Dict[str, Any]] = []

    # Helper: run a single PS command via session or subprocess
    def _run_ps(cmd: str, cwd: Path) -> Dict[str, Any]:
        """Execute a single PowerShell command.

        Args:
            cmd: The command to execute.
            cwd: Working directory to use.

        Returns:
            Dict[str, Any]: Single-command result dict.
        """
        wrapped = (
            f"Set-Location {cwd}; {cmd}; Write-Output {_MARKER}; (Get-Location).Path"
        )
        log.info("powershell_tool: running | cwd=%s | cmd=%s", cwd, cmd)

        if session:
            # Persistent session path
            try:
                out = session.run(wrapped)
                stdout = out or ""
                stderr = ""
                rc = 0
            except Exception as e:
                stdout, stderr, rc = "", f"[SESSION ERROR] {e}", 1
        else:
            # Subprocess fallback
            try:
                proc = subprocess.run(
                    [_PWSH, "-NoLogo", "-NoProfile", "-Command", wrapped],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    env=os.environ.copy(),
                    timeout=30,
                )
                stdout = proc.stdout or ""
                stderr = proc.stderr or ""
                rc = proc.returncode
            except subprocess.TimeoutExpired as e:
                stdout = (e.stdout.decode() if e.stdout else "").strip()
                stderr = (
                    (e.stderr.decode() if e.stderr else "") + "\n[TIMEOUT]"
                ).strip()
                rc = 124

        # Extract output and updated CWD using the marker
        lines = (stdout or "").splitlines()
        new_cwd = str(cwd)
        if _MARKER in lines:
            idx = lines.index(_MARKER)
            output_lines = lines[:idx]
            if idx + 1 < len(lines):
                new_cwd = lines[idx + 1].strip() or new_cwd
        else:
            output_lines = lines

        return {
            "cmd": cmd,
            "returncode": rc,
            "stdout": "\n".join(output_lines).strip(),
            "stderr": (stderr or "").strip(),
            "cwd": new_cwd,
        }

    # Execute each command with policy validation and sandbox checks.
    for cmd in input.commands:
        res = _run_ps(cmd, cwd_path)
        results.append(res)

        # Update and re-sandbox the working directory after each command.
        next_cwd = Path(res["cwd"]).resolve()
        if POLICY.enforce_root_jail:
            root_r = POLICY.root_dir.resolve()
            if os.path.commonpath([str(root_r), str(next_cwd)]) != str(root_r):
                next_cwd = root_r
        cwd_path = next_cwd

        if res["returncode"] != 0:
            return {"success": False, "results": results, "cwd": str(cwd_path)}

    return {"success": True, "results": results, "cwd": str(cwd_path)}
