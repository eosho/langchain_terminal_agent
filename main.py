"""
Command-line entry point for the Shell agent.

This module demonstrates a fully interactive human-in-the-loop (HITL)
workflow using the shell agent built in `terminal_agent.build_agent`.

Shell-related actions will pause execution and prompt the user to approve,
edit, ignore, or manually respond before continuing.
"""

import asyncio
import json
import logging
import platform

from langgraph.types import Command

from terminal_agent.core.logging import setup_logging
from terminal_agent.core.state import ShellState
from terminal_agent.builder import build_agent


async def run() -> None:
    """Run the interactive command-line interface for the Terminal Agent.

    This coroutine demonstrates real-time human-in-the-loop (HITL)
    decision-making. When the agent encounters a shell tool action
    (e.g., Bash or PowerShell command), it pauses and waits for user
    approval before execution. The user can choose to accept, edit,
    ignore, or manually respond.

    Example:
        ```bash
        poetry run python -m terminal_agent.main
        ```

    Raises:
        Exception: Propagates exceptions from agent invocation or resume
        if critical errors occur.
    """
    # Initialize structured logging.
    setup_logging(logging.INFO)

    # Determine the default shell type from system platform.
    default_shell = (
        "powershell" if platform.system().lower().startswith("win") else "bash"
    )
    state = ShellState(cwd=".", shell_type=default_shell)

    # Build the agent
    agent = await build_agent(shell_type=default_shell)

    # Fixed thread ID for this demo session.
    thread_id = "1"
    config = {"configurable": {"thread_id": thread_id}}

    print(f"🧠 Terminal Agent (HITL Mode)\nUsing {default_shell} shell by default.")
    print("Type 'exit' to quit, or 'use bash' / 'use powershell' to switch.\n")

    while True:
        user_input = input("> ").strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        # Allow explicit shell switching mid-session
        if user_input.lower() in {"use bash", "bash"}:
            state.shell_type = "bash"
            print("⚙️  Switched to Bash mode.")
            continue
        if user_input.lower() in {"use powershell", "pwsh", "powershell"}:
            state.shell_type = "powershell"
            print("⚙️  Switched to PowerShell mode.")
            continue

        # Compose contextual prompt with working directory and shell type
        prompt = f"Current working directory: {state.cwd}. Using {state.shell_type} shell.\n{user_input}"

        # Invoke the agent with user input
        try:
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

        # Handle Human-In-The-Loop approvals
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

            print("\n⚠️  Action requires approval:")
            try:
                print(json.dumps(action_request, indent=2))
            except TypeError:
                print(str(action_request))

            decision = (
                input("Enter decision ([a]ccept/[e]dit/[i]gnore/[r]esponse): ")
                .strip()
                .lower()
            )

            # Build resume payload based on user decision
            if decision.startswith("a"):
                resume_payload = {"decisions": [{"type": "approve"}]}
            elif decision.startswith("e"):
                new_args = input("Enter edited args as JSON: ").strip()
                try:
                    parsed_args = json.loads(new_args) if new_args else {}
                except json.JSONDecodeError:
                    print("Invalid JSON provided. Defaulting to approve.")
                    parsed_args = {}
                # Ensure action_request is a dict before accessing .get("action")
                action_value = None
                if isinstance(action_request, dict):
                    action_value = action_request.get("action")
                elif (
                    isinstance(action_request, list)
                    and action_request
                    and isinstance(action_request[0], dict)
                ):
                    action_value = action_request[0].get("action")
                resume_payload = {
                    "decisions": [
                        {
                            "type": "edit",
                            "args": {
                                "action": action_value,
                                "args": parsed_args,
                            },
                        }
                    ]
                }
            elif decision.startswith("i"):
                resume_payload = {"decisions": [{"type": "reject"}]}
            elif decision.startswith("r"):
                manual_resp = input("Enter manual response: ").strip()
                # For manual response, we'll reject the original action and provide a manual response
                resume_payload = {
                    "decisions": [{"type": "reject", "response": manual_resp}]
                }
            else:
                print("Unrecognized decision; defaulting to approve.")
                resume_payload = {"decisions": [{"type": "approve"}]}

            # Resume execution with the selected decision
            try:
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
        print("\n=== Conversation Trace ===")
        messages = (
            result.get("messages", [])
            if isinstance(result, dict)
            else getattr(result, "messages", [])
        )
        for i, msg in enumerate(messages or [], start=1):
            role = getattr(msg, "role", None) or (
                msg.get("role") if isinstance(msg, dict) else "assistant"
            )
            content = getattr(msg, "content", None) or (
                msg.get("content") if isinstance(msg, dict) else ""
            )
            print(f"\nMessage {i} [{role}]:\n{content}")

    print("\n👋 Session ended. Goodbye!")


def agent() -> None:
    """Entry point for the Terminal Agent."""
    asyncio.run(run())


if __name__ == "__main__":
    agent()
