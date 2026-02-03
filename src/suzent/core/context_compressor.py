"""
Context Compressor: Manages agent memory by summarizing and pruning old turns.
"""

from typing import List, Optional

from smolagents import CodeAgent
from smolagents.memory import (
    ActionStep,
    PlanningStep,
    FinalAnswerStep,
    TaskStep,
    ToolCall,
)
from smolagents.monitoring import Timing

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.llm import LLMClient
from suzent.core.provider_factory import get_effective_memory_config

logger = get_logger(__name__)

SUMMARY_PROMPT_TEMPLATE = """
You are a helpful assistant summarizing the conversation history for an AI agent to free up context window space.

Here is a segment of the conversation history (actions taken, thoughts, and outputs):
--------------------------------------------------
{steps_text}
--------------------------------------------------

Please provide a concise but comprehensive summary of these events.
- Focus on key decisions, tool outputs, and facts learned.
- Discard verbose logs or intermediate errors that are resolved.
- Structure it as a "Previous Context Summary" that the agent can read to understand what happened.
- Write it in the past tense.
"""


class ContextCompressor:
    """Handles compression of agent conversation history to manage context window size."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        if llm_client:
            self.llm_client = llm_client
        else:
            config = get_effective_memory_config()
            self.llm_client = LLMClient(model=config["extraction_model"])

        self.max_history_steps = CONFIG.max_history_steps

    async def compress_context(self, agent: CodeAgent) -> bool:
        """
        Check if context needs compression and perform it if necessary.

        Returns:
            True if compression occurred, False otherwise.
        """
        if not agent or not hasattr(agent, "memory"):
            return False

        steps = agent.memory.steps
        if not steps:
            return False

        reason = self._should_compress(agent, steps)
        if not reason:
            return False

        logger.info(f"Compressing agent context: {reason}")

        try:
            return await self._perform_compression(agent)
        except Exception as e:
            logger.error(f"Context compression failed: {e}")
            return False

    def _should_compress(self, agent: CodeAgent, steps: list) -> Optional[str]:
        """
        Determine whether compression is needed.

        Returns:
            A reason string if compression is needed, None otherwise.
        """
        if len(steps) > self.max_history_steps:
            return f"Step count ({len(steps)}) exceeds limit ({self.max_history_steps})"

        if hasattr(agent, "monitor") and agent.monitor:
            total_tokens = (
                agent.monitor.total_input_token_count
                + agent.monitor.total_output_token_count
            )
            if total_tokens > CONFIG.max_context_tokens:
                logger.warning(
                    f"Compression triggered by token usage: {total_tokens} > {CONFIG.max_context_tokens}"
                )
                return f"Token usage ({total_tokens}) exceeds limit ({CONFIG.max_context_tokens})"

        return None

    async def _perform_compression(self, agent: CodeAgent) -> bool:
        """
        Compress the agent's memory by summarizing older steps.

        Strategy:
        1. Keep the initial TaskStep (steps[0]).
        2. Summarize the compressible middle block into a single ActionStep.
        3. Keep the most recent N steps intact.
        """
        steps = agent.memory.steps

        # Keep last N steps (at least 5, or 25% of max)
        keep_recent_count = max(5, int(self.max_history_steps * 0.25))

        if len(steps) <= keep_recent_count + 1:
            logger.debug("Not enough steps to compress effectively yet.")
            return False

        start_index = 1  # After initial TaskStep
        end_index = len(steps) - keep_recent_count

        if start_index >= end_index:
            return False

        steps_to_compress = steps[start_index:end_index]
        steps_text = self._steps_to_text(steps_to_compress)

        summary = await self.llm_client.complete(
            prompt=SUMMARY_PROMPT_TEMPLATE.format(steps_text=steps_text),
            system="You are an expert technical summarizer.",
            temperature=0.3,
        )

        if not summary:
            logger.warning("Failed to generate summary for compression.")
            return False

        # Create a synthetic ActionStep containing the archived summary
        summary_tool_call = ToolCall(
            name="system_context_manager",
            arguments={"action": "read_archived_history"},
            id="context_compression_event",
        )

        summary_step = ActionStep(
            step_number=len(steps),
            timing=Timing(start_time=0.0, end_time=0.0),
            tool_calls=[summary_tool_call],
            error=None,
        )
        summary_step.action_output = (
            f"--- ARCHIVED CONTEXT SUMMARY ---\n{summary}\n--- END ARCHIVED CONTEXT ---"
        )

        # Rebuild memory: [TaskStep] + [Summary] + [Recent steps]
        new_memory = [steps[0], summary_step] + steps[end_index:]
        agent.memory.steps = new_memory

        logger.info(
            f"Context compressed. Steps reduced from {len(steps)} to {len(new_memory)}."
        )
        return True

    def _steps_to_text(self, steps: List) -> str:
        """Convert a list of agent steps to a text representation for summarization."""
        text = []
        for step in steps:
            if isinstance(step, ActionStep):
                if step.tool_calls:
                    for tool_call in step.tool_calls:
                        text.append(f"Action: {tool_call.name}({tool_call.arguments})")
                if step.action_output:
                    output = str(step.action_output)
                    if len(output) > 500:
                        output = output[:500] + "... (truncated)"
                    text.append(f"Result: {output}")
                if step.error:
                    text.append(f"Error: {step.error}")
            elif isinstance(step, PlanningStep):
                text.append(f"Plan: {step.plan}")
            elif isinstance(step, FinalAnswerStep):
                text.append(f"Final Answer: {step.final_answer}")
            elif isinstance(step, TaskStep):
                text.append(f"Task: {step.task}")

        return "\n".join(text)
