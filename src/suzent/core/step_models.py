"""
Suzent-owned step and state models.

These Pydantic models replace the direct dependency on smolagents' internal
step types (ActionStep, PlanningStep, FinalAnswerStep, TaskStep, ToolCall,
Timing). They are used for:
- State serialization (agent_serializer.py)
- Context compression (context_compressor.py)
- Memory extraction (chat_processor.py, memory/models.py)
- Streaming event mapping (streaming.py)
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    """Record of a tool call made by the agent."""

    name: str
    arguments: dict[str, Any] = {}
    id: str = ""
    output: Optional[str] = None


class ActionStepRecord(BaseModel):
    """Record of an agent action step (tool call + result)."""

    step_number: int = 0
    tool_calls: List[ToolCallRecord] = []
    model_output: Optional[str] = None
    observations: Optional[str] = None
    action_output: Optional[str] = None
    is_final_answer: bool = False
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class PlanningStepRecord(BaseModel):
    """Record of a planning step."""

    plan: str = ""


class TaskStepRecord(BaseModel):
    """Record of a task assignment."""

    task: str = ""


class FinalAnswerRecord(BaseModel):
    """Record of the final answer."""

    output: Optional[str] = None


class AgentStateSnapshot(BaseModel):
    """Complete snapshot of agent state for persistence.

    Version history:
    - v2: smolagents step-based serialization (legacy)
    - v3: pydantic-ai message-history serialization
    """

    version: int = 3
    model_id: Optional[str] = None
    instructions: Optional[str] = None
    tool_names: List[str] = []
    steps: List[dict] = Field(
        default_factory=list,
        description="Serialized step records (v2 compat) or empty for v3",
    )
    message_history: Optional[str] = Field(
        None,
        description="JSON-serialized pydantic-ai messages (v3)",
    )
