"""
Shell session middleware (persistent process).

Creates a long-lived shell process (bash or PowerShell) at agent start and
exposes it via `state["resources"]["shell_session"]`. Shell tools can reuse
this session for lower latency and true continuity (env/cwd/history).

Order in builder:
    ShellSessionMiddleware -> ShellPolicyMiddleware -> HumanInTheLoopMiddleware
"""

import io
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Optional, cast

from langchain.agents.middleware import AgentMiddleware, AgentState
from langgraph.runtime import Runtime


@dataclass
class ShellSessionConfig:
    """Configuration for the persistent shell session.

    Attributes:
        shell_type: Which shell to start ("bash" or "powershell").
        startup_cwd: Initial working directory.
        read_timeout_sec: Timeout for reading command output.
        startup_cmds: Optional list of commands to pre-run on session start.
    """

    shell_type: Literal["bash", "powershell"] = "bash"
    startup_cwd: Path = Path(os.getenv("SHELL_ROOT_DIR", Path.cwd())).resolve()
    read_timeout_sec: float = 5.0
    startup_cmds: Optional[list[str]] = None


class _ShellSession:
    """Thin wrapper over a long-lived shell subprocess (stdin/stdout).

    Provides `run()` to write a command and collect output with a timeout.
    """

    def __init__(self, executable: str, cwd: Path, read_timeout_sec: float = 5.0):
        self._proc = subprocess.Popen(
            executable,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            text=True,
            bufsize=1,  # line-buffered
            shell=False,
        )
        self._out_q: "queue.Queue[str]" = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        self._timeout = read_timeout_sec

    def _pump(self) -> None:
        """Background reader that enqueues stdout lines."""
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._out_q.put_nowait(line)

    def run(self, command: str) -> str:
        """Run a single command and return combined output.

        Args:
            command: Command line to execute.

        Returns:
            str: Combined stdout/stderr output collected until timeout.
        """
        if not self._proc or not self._proc.stdin:
            return "[session closed]"

        # Add a sentinel line so we know where output ends.
        sentinel = f"__END_{int(time.time() * 1000)}__"
        to_write = f"{command}\necho {sentinel}\n"
        self._proc.stdin.write(to_write)
        self._proc.stdin.flush()

        buf = io.StringIO()
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            try:
                line = self._out_q.get(timeout=0.1)
            except queue.Empty:
                continue
            buf.write(line)
            if sentinel in line:
                break
        return buf.getvalue()

    def terminate(self) -> None:
        """Terminate the underlying process."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class ShellSessionMiddleware(AgentMiddleware):
    """Create a persistent shell session and attach to state resources.

    The middleware sets:
        state["resources"]["shell_session"] = {
            "bash": _ShellSession(...), or
            "powershell": _ShellSession(...),
        }

    Tools can read this handle to execute in the persistent shell.
    """

    def __init__(self, cfg: ShellSessionConfig):
        super().__init__()
        self.cfg = cfg

    def before_agent(
        self, state: AgentState, runtime: Runtime
    ) -> Dict[str, Any] | None:
        """Start the shell session before the agent loop begins.

        Returns:
            Optional state delta; here we attach the session into resources.
        """
        shell_exe = "/bin/bash" if self.cfg.shell_type == "bash" else "pwsh"
        print(f"[ShellSession] Starting {self.cfg.shell_type} shell: {shell_exe}")
        print(f"[ShellSession] Working directory: {self.cfg.startup_cwd}")

        session = _ShellSession(
            executable=shell_exe,
            cwd=self.cfg.startup_cwd,
            read_timeout_sec=self.cfg.read_timeout_sec,
        )

        # Optional startup commands (e.g., set -e, cd, env)
        if self.cfg.startup_cmds:
            print(f"[ShellSession] Running {len(self.cfg.startup_cmds)} startup commands")
            for c in self.cfg.startup_cmds:
                print(f"[ShellSession] Startup command: {c}")
                session.run(c)

        # Cast state to dict for type safety
        state_dict = cast(Dict[str, Any], state)
        resources = state_dict.get("resources") or {}
        resources["shell_session"] = resources.get("shell_session", {})
        resources["shell_session"][self.cfg.shell_type] = session

        print(f"[ShellSession] Session started and attached to state resources")
        return {"resources": resources}

    def after_agent(self, state: AgentState, runtime: Runtime) -> Dict[str, Any] | None:
        """Cleanup hook after agent completes."""
        print("[ShellSession] Cleaning up shell sessions")

        # Cast state to dict for type safety
        state_dict = cast(Dict[str, Any], state)
        resources = state_dict.get("resources") or {}
        sess_map = resources.get("shell_session") or {}

        for shell_type, sess in sess_map.items():
            try:
                print(f"[ShellSession] Terminating {shell_type} session")
                sess.terminate()
            except Exception as e:
                print(f"[ShellSession] Error terminating {shell_type} session: {e}")

        print("[ShellSession] Cleanup complete")
        return None
