"""
State models for agent sessions.

This module defines Pydantic models that encapsulate the session context
for the shell-only agent. These states can be persisted between tool
invocations to maintain continuity of information—such as the working
directory and the active shell type.
"""

from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


class BaseAgentState(BaseModel):
    """Base class for all agent state models.

    Provides shared fields such as `session_id` for correlating
    agent interactions and an optional `metadata` dictionary
    for storing arbitrary contextual information.

    Attributes:
        session_id: Unique identifier for the current agent session.
        metadata: Arbitrary session metadata for contextual storage.
    """

    session_id: Optional[str] = Field(
        default=None, description="Unique identifier for the session."
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary metadata for storing additional session context.",
    )


class ShellState(BaseAgentState):
    """Represents the execution context for shell operations.

    Maintains the current working directory and shell type
    (e.g., bash or powershell). By persisting this state, the
    agent can preserve continuity between commands—allowing
    operations like `cd` to affect subsequent invocations.

    Attributes:
        cwd: Current working directory path for the session.
        shell_type: Shell environment in use, either "bash" or "powershell".
    """

    cwd: str = Field(
        default=".", description="Current working directory for shell operations."
    )
    shell_type: Literal["bash", "powershell"] = Field(
        default="bash", description="Shell environment to use (bash or powershell)."
    )
