"""
Helper utilities for Rich-based console UI for the Terminal Agent.

Includes common components like `console`, and the `show_approval_panel`
helper.
"""

import time
from typing import Union

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.live import Live
from rich.align import Align

# Global Console object
console = Console()


def show_approval_panel(action_request: dict | list | str) -> None:
    """Render the “Action Requires Approval” panel with subtle visual effect.

    Args:
        action_request: The payload representing the tool/action requiring approval.
    """
    try:
        body: Union[JSON, Panel] = JSON.from_data(action_request)
    except Exception:
        body = Panel(str(action_request), style="red", title="Raw Payload")

    header = Panel.fit(
        "⚠️  [bold yellow]Action Requires Approval[/bold yellow]",
        style="bold yellow",
        border_style="yellow",
    )
    block = Align.left(Panel.fit(body, border_style="yellow", title="Action Request"))

    console.print()  # blank line
    console.print(header)
    time.sleep(0.08)
    with Live(block, console=console, transient=True, refresh_per_second=20):
        time.sleep(0.18)
    console.print(block)
