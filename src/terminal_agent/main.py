"""
Command-line entry point for the Shell agent.

This module demonstrates a fully interactive human-in-the-loop (HITL)
workflow using the shell agent built in `terminal_agent.builder.build_agent`.

Shell-related actions will pause execution and prompt the user to approve,
reject before continuing.
"""

import asyncio
import logging
import platform
import uuid
from typing import Any, Dict, Literal

from langgraph.types import Command
from rich.panel import Panel

from terminal_agent.builder import build_agent
from terminal_agent.core.logging import setup_logging
from terminal_agent.core.state import ShellState
from terminal_agent.utils.console_utils import console, show_approval_panel


def _extract_tool_name(action_request: Any) -> str:
    """Best-effort extraction of the tool/action name from an interrupt payload.

    Args:
        action_request: The interrupt's action request payload.
    """
    if isinstance(action_request, dict):
        return (
            action_request.get("tool")
            or action_request.get("action")
            or action_request.get("name")
            or ""
        )
    if (
        isinstance(action_request, list)
        and action_request
        and isinstance(action_request[0], dict)
    ):
        return (
            action_request[0].get("tool")
            or action_request[0].get("action")
            or action_request[0].get("name")
            or ""
        )
    return ""


def build_resume_payload(
    decision: str,
    action_request: Dict[str, Any] | Any,
) -> Dict[str, Any]:
    """Construct the Human-In-The-Loop resume payload.

    Args:
        decision: One of "approve", "reject".
        action_request: The interrupt's action request payload.

    Returns:
        Dict[str, Any]: {"decisions": [ … ]} payload expected by HITL middleware.
    """
    tool_name = _extract_tool_name(action_request)

    if decision == "approve":
        item = {"type": "approve", "tool": tool_name}
    elif decision == "reject":
        item = {"type": "reject", "tool": tool_name}
    else:
        item = {"type": "reject", "tool": tool_name}

    return {"decisions": [item]}


async def run() -> None:
    """Run the interactive command-line interface for the Terminal Agent.

    This coroutine demonstrates real-time human-in-the-loop (HITL)
    decision-making. When the agent encounters a shell tool action
    (e.g., Bash or PowerShell command), it pauses and waits for user
    approval before execution. The user can choose to accept or ignore.

    Example:
        ```bash
        poetry run python -m terminal_agent.main
        ```

    Raises:
        Exception: Propagates exceptions from agent invocation or resume
        if critical errors occur.
    """
    setup_logging(logging.INFO)

    # Determine the default shell type from system platform.
    default_shell: Literal["bash", "powershell"] = (
        "powershell" if platform.system().lower().startswith("win") else "bash"
    )
    state = ShellState(cwd=".", shell_type=default_shell)

    # Build the agent
    agent = await build_agent(shell_type=default_shell)

    # Thread ID for the session.
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    console.print(
        Panel.fit(
            f"[bold green]>_ Terminal Agent[/bold green]\nUsing [bold]{default_shell}[/bold] by default.\n\n"
            "Type 'exit' to quit, or 'use bash' / 'use powershell' to switch.",
            border_style="green",
        )
    )

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        # Allow explicit shell switching mid-session
        if user_input.lower() in {"use bash", "bash"}:
            state.shell_type = "bash"
            console.print("[yellow]⚙️  Switched to Bash mode.[/yellow]")
            continue
        if user_input.lower() in {"use powershell", "pwsh", "powershell"}:
            state.shell_type = "powershell"
            console.print("[yellow]⚙️  Switched to PowerShell mode.[/yellow]")
            continue

        # Compose contextual prompt with working directory and shell type
        prompt = f"Current working directory: {state.cwd}. Using {state.shell_type} shell.\n{user_input}"

        try:
            with console.status("[bold cyan]Thinking…[/bold cyan]", spinner="dots"):
                result = agent.invoke(
                    {"messages": [{"role": "user", "content": prompt}]}, config=config
                )
        except Exception:
            logging.exception("Agent invocation failed.")
            continue

        # Attempt to fetch agent state for pending tool interrupts
        state_obj = None
        if hasattr(agent, "get_state"):
            try:
                state_obj = agent.get_state(config)
            except Exception:
                logging.exception("Failed to retrieve agent state after invocation.")

        while (
            state_obj is not None
            and getattr(state_obj, "next", None)
            and getattr(state_obj, "tasks", None)
        ):
            task = state_obj.tasks[0] if getattr(state_obj, "tasks", None) else None
            if not task or not getattr(task, "interrupts", None):
                break

            interrupt = task.interrupts[0]
            value = getattr(interrupt, "value", None)

            # Extract pending action details
            if isinstance(value, list) and value:
                action_request = value[0].get("action_request", {})
            else:
                action_request = value or {}

            # Display approval panel and prompt for decision
            show_approval_panel(action_request)

            decision = input("Decision ([a]pprove/[r]eject): ").strip().lower()
            if decision.startswith("a"):
                resume_payload = build_resume_payload("approve", action_request)
            elif decision.startswith("r"):
                resume_payload = build_resume_payload("reject", action_request)
            else:
                console.print(
                    "[yellow]Unrecognized decision; defaulting to reject.[/yellow]"
                )
                resume_payload = build_resume_payload("reject", action_request)

            # Resume execution with the selected decision
            try:
                with console.status(
                    "[bold cyan]Resuming with your decision…[/bold cyan]",
                    spinner="dots",
                ):
                    result = agent.invoke(Command(resume=resume_payload), config=config)
            except Exception:
                logging.exception("Error while resuming agent execution.")
                break

            # Refresh state for any further pending tasks
            if hasattr(agent, "get_state"):
                try:
                    state_obj = agent.get_state(config)
                except Exception:
                    logging.exception("Error refreshing state after resume.")
                    state_obj = None
            else:
                break

        # Print the final conversation trace
        console.print("\n[bold]=== Conversation Trace ===[/bold]")
        messages = (
            result.get("messages", [])
            if isinstance(result, dict)
            else getattr(result, "messages", [])
        )

        # Filter out None or empty messages
        messages = [
            msg
            for msg in messages or []
            if msg
            and (
                (isinstance(msg, dict) and msg.get("content"))
                or (hasattr(msg, "content") and getattr(msg, "content", None))
            )
        ]

        for i, msg in enumerate(messages or [], start=1):
            role = getattr(msg, "role", None) or (
                msg.get("role") if isinstance(msg, dict) else "assistant"
            )
            if role is None:
                role = "assistant"
            content = getattr(msg, "content", None) or (
                msg.get("content") if isinstance(msg, dict) else ""
            )
            role_color = "cyan" if role == "assistant" else "magenta"
            console.print(
                Panel.fit(
                    f"[bold {role_color}]{str(role).upper()}[/bold {role_color}]\n{content}",
                    border_style=role_color,
                    title=f"{role.capitalize()} Message {i}",
                    title_align="left",
                )
            )

    console.print("\n[cyan]👋 Session ended. Goodbye![/cyan]")


def agent() -> None:
    """Entry point for the Terminal Agent (sync wrapper)."""
    asyncio.run(run())


if __name__ == "__main__":
    agent()
