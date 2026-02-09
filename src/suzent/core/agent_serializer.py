"""
Agent serialization module for persisting and restoring agent state.

This module handles:
- Serializing agent state to JSON bytes (human-readable, inspectable)
- Deserializing and restoring agent state from JSON or legacy pickle
- Converting smolagents step objects to/from JSON-safe dicts
"""

import json
import pickle
from typing import Optional, Dict, Any, List

from smolagents import CodeAgent

from suzent.logger import get_logger

logger = get_logger(__name__)

# Format version for migration detection
STATE_FORMAT_VERSION = 2


# ─── Step serialization ───────────────────────────────────────────────


def _serialize_steps(steps) -> List[dict]:
    """Convert smolagents step objects to JSON-serializable dicts."""
    from smolagents.memory import ActionStep, PlanningStep, TaskStep, FinalAnswerStep

    serialized = []
    for step in steps:
        try:
            if isinstance(step, ActionStep):
                # Serialize tool calls
                tool_calls = None
                if step.tool_calls:
                    tool_calls = [
                        {
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "id": tc.id,
                        }
                        for tc in step.tool_calls
                    ]

                serialized.append(
                    {
                        "type": "action",
                        "step_number": step.step_number,
                        "tool_calls": tool_calls,
                        "model_output": (
                            step.model_output
                            if isinstance(step.model_output, str)
                            else None
                        ),
                        "code_action": step.code_action,
                        "observations": (
                            str(step.observations)[:4000] if step.observations else None
                        ),
                        "action_output": (
                            str(step.action_output)[:2000]
                            if step.action_output is not None
                            else None
                        ),
                        "is_final_answer": step.is_final_answer,
                    }
                )

            elif isinstance(step, PlanningStep):
                serialized.append(
                    {
                        "type": "planning",
                        "plan": step.plan,
                    }
                )

            elif isinstance(step, TaskStep):
                serialized.append(
                    {
                        "type": "task",
                        "task": step.task,
                    }
                )

            elif isinstance(step, FinalAnswerStep):
                serialized.append(
                    {
                        "type": "final_answer",
                        "output": str(step.output)[:2000]
                        if step.output is not None
                        else None,
                    }
                )

            else:
                # Unknown step type — store as generic dict
                serialized.append(
                    {
                        "type": "unknown",
                        "repr": repr(step)[:500],
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to serialize step {type(step).__name__}: {e}")
            continue

    return serialized


def _deserialize_steps(step_dicts: List[dict]) -> list:
    """Reconstruct smolagents step objects from JSON dicts."""
    from smolagents.memory import (
        ActionStep,
        PlanningStep,
        TaskStep,
        FinalAnswerStep,
        ToolCall,
    )
    from smolagents.monitoring import Timing

    steps = []
    for d in step_dicts:
        try:
            step_type = d.get("type")

            if step_type == "action":
                tool_calls = None
                if d.get("tool_calls"):
                    tool_calls = [
                        ToolCall(
                            name=tc["name"],
                            arguments=tc["arguments"],
                            id=tc.get("id", ""),
                        )
                        for tc in d["tool_calls"]
                    ]

                step = ActionStep(
                    step_number=d.get("step_number", 0),
                    timing=Timing(start_time=0.0, end_time=0.0),
                    tool_calls=tool_calls,
                    model_output=d.get("model_output"),
                    code_action=d.get("code_action"),
                    observations=d.get("observations"),
                    action_output=d.get("action_output"),
                    is_final_answer=d.get("is_final_answer", False),
                )
                steps.append(step)

            elif step_type == "planning":
                from smolagents.models import ChatMessage

                steps.append(
                    PlanningStep(
                        model_input_messages=[],
                        model_output_message=ChatMessage(
                            role="assistant", content=d.get("plan", "")
                        ),
                        plan=d.get("plan", ""),
                        timing=Timing(start_time=0.0, end_time=0.0),
                    )
                )

            elif step_type == "task":
                steps.append(TaskStep(task=d.get("task", "")))

            elif step_type == "final_answer":
                steps.append(FinalAnswerStep(output=d.get("output")))

            # Skip "unknown" types silently

        except Exception as e:
            logger.warning(f"Failed to deserialize step (type={d.get('type')}): {e}")
            continue

    return steps


# ─── Tool name extraction ─────────────────────────────────────────────


def _extract_tool_names(agent: CodeAgent) -> List[str]:
    """Extract tool class names from agent."""
    tool_attr = getattr(agent, "_tool_instances", None)
    if tool_attr is None:
        raw_tools = getattr(agent, "tools", None)
        if isinstance(raw_tools, dict):
            tool_iterable = raw_tools.values()
        elif isinstance(raw_tools, (list, tuple)):
            tool_iterable = raw_tools
        elif raw_tools is None:
            tool_iterable = []
        else:
            tool_iterable = [raw_tools]
    else:
        tool_iterable = tool_attr

    names = []
    for tool in tool_iterable:
        try:
            name = tool.__class__.__name__
        except AttributeError:
            continue
        if name not in names:
            names.append(name)
    return names


# ─── Public API ────────────────────────────────────────────────────────


def serialize_agent(agent: CodeAgent) -> Optional[bytes]:
    """
    Serialize agent state to JSON bytes.

    Produces a human-readable JSON document (format version 2).
    Falls back to pickle only if JSON serialization fails entirely.
    """
    try:
        # Get steps from the memory object
        memory = agent.memory
        if hasattr(memory, "steps"):
            steps = _serialize_steps(memory.steps)
        elif isinstance(memory, list):
            steps = _serialize_steps(memory)
        else:
            steps = []

        state = {
            "version": STATE_FORMAT_VERSION,
            "model_id": (
                getattr(agent.model, "model_id", None)
                if hasattr(agent, "model")
                else None
            ),
            "instructions": getattr(agent, "instructions", None),
            "step_number": getattr(agent, "step_number", 1),
            "max_steps": getattr(agent, "max_steps", 10),
            "tool_names": _extract_tool_names(agent),
            "steps": steps,
        }

        return json.dumps(state, ensure_ascii=False, default=str).encode("utf-8")

    except Exception as e:
        logger.warning(f"JSON serialization failed, falling back to pickle: {e}")

        # Pickle fallback (for edge cases with exotic step contents)
        try:
            from smolagents.memory import ActionStep

            # Clear errors in-place (same as old _sanitize_memory)
            if hasattr(agent.memory, "steps"):
                for step in agent.memory.steps:
                    if isinstance(step, ActionStep) and getattr(step, "error", None):
                        step.error = None

            legacy_state = {
                "memory": agent.memory,
                "model_id": getattr(agent.model, "model_id", None)
                if hasattr(agent, "model")
                else None,
                "instructions": getattr(agent, "instructions", None),
                "step_number": getattr(agent, "step_number", 1),
                "max_steps": getattr(agent, "max_steps", 10),
                "tool_names": _extract_tool_names(agent),
                "managed_agents": getattr(agent, "managed_agents", []),
            }
            return pickle.dumps(legacy_state)
        except Exception as e2:
            logger.error(f"Pickle fallback also failed: {e2}")
            return None


def deserialize_agent(
    agent_data: bytes, config: Dict[str, Any], create_agent_fn
) -> Optional[CodeAgent]:
    """
    Deserialize agent state and restore it to a new agent instance.

    Tries JSON (v2) first, falls back to pickle for legacy sessions.
    """
    if not agent_data:
        return None

    # --- Try JSON v2 first ---
    try:
        state = json.loads(agent_data.decode("utf-8"))
        if isinstance(state, dict) and state.get("version") == STATE_FORMAT_VERSION:
            return _restore_from_json(state, config, create_agent_fn)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass  # Not JSON — try pickle

    # --- Fallback to pickle (legacy) ---
    try:
        state = pickle.loads(agent_data)
    except (TypeError, AttributeError, pickle.UnpicklingError) as e:
        logger.warning(f"Failed to unpickle agent state: {e}")
        return None

    if not isinstance(state, dict):
        logger.warning(f"Legacy state is not a dict ({type(state).__name__}), skipping")
        return None

    return _restore_from_pickle(state, config, create_agent_fn)


# ─── Restoration helpers ──────────────────────────────────────────────


def _restore_from_json(
    state: dict, config: Dict[str, Any], create_agent_fn
) -> Optional[CodeAgent]:
    """Restore agent from JSON v2 state."""
    try:
        agent = create_agent_fn(config)

        # Reconstruct steps and assign to memory
        step_dicts = state.get("steps", [])
        if step_dicts:
            restored_steps = _deserialize_steps(step_dicts)
            if hasattr(agent.memory, "steps"):
                agent.memory.steps = restored_steps
            else:
                agent.memory = restored_steps

        if "step_number" in state:
            agent.step_number = state["step_number"]
        if "max_steps" in state:
            agent.max_steps = state["max_steps"]

        logger.debug(f"Restored agent from JSON v2 ({len(step_dicts)} steps)")
        return agent

    except Exception as e:
        logger.warning(f"JSON restoration failed: {e}")
        return None


def _restore_from_pickle(
    state: dict, config: Dict[str, Any], create_agent_fn
) -> Optional[CodeAgent]:
    """Restore agent from legacy pickle state."""
    try:
        agent = create_agent_fn(config)

        if "memory" in state:
            agent.memory = state["memory"]
        if "step_number" in state:
            agent.step_number = state["step_number"]
        if "max_steps" in state:
            agent.max_steps = state["max_steps"]

        logger.debug("Restored agent from legacy pickle format")
        return agent

    except Exception as e:
        logger.warning(f"Pickle restoration failed: {e}")
        return None
