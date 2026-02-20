"""
Context Compressor: Manages agent memory by summarizing and pruning old turns.

Supports pre-compaction memory flush: before compressing steps, extract
important facts from the steps about to be removed and persist them
to the memory system (LanceDB + markdown). This ensures no valuable
context is lost when the context window is trimmed.
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
    """Handles compression of agent conversation history to manage context window size.

    Supports pre-compaction memory flush: before compressing, extract facts from
    steps about to be removed and feed them to the memory system.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        if llm_client:
            self.llm_client = llm_client
        else:
            config = get_effective_memory_config()
            self.llm_client = LLMClient(model=config["extraction_model"])

        self.max_history_steps = CONFIG.max_history_steps
        self.chat_id = chat_id
        self.user_id = user_id

    async def compress_context(self, agent: CodeAgent) -> bool:
        """
        Check if context needs compression and perform it if necessary.

        Before compressing, runs a pre-compaction memory flush to capture
        important facts from the steps that will be removed.

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
        2. Pre-compaction flush: extract facts from steps about to be removed.
        3. Summarize the compressible middle block into a single ActionStep.
        4. Keep the most recent N steps intact.
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

        # Pre-compaction memory flush: extract facts before they're lost
        await self._pre_compaction_flush(steps_to_compress)

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

    async def _pre_compaction_flush(self, steps_to_compress: List) -> None:
        """
        Extract memories from steps about to be compressed away.

        Builds a synthetic ConversationTurn from the steps being removed
        and feeds it to the memory manager. This ensures no important
        facts are lost when context is trimmed.

        Args:
            steps_to_compress: List of agent steps about to be removed.
        """
        if not CONFIG.memory_enabled:
            return

        if not self.chat_id or not self.user_id:
            logger.debug("Pre-compaction flush skipped: no chat_id/user_id")
            return

        try:
            from suzent.memory.lifecycle import get_memory_manager
            from suzent.memory import ConversationTurn, Message, AgentAction

            memory_mgr = get_memory_manager()
            if not memory_mgr:
                return

            # Build a synthetic turn from the steps about to be discarded
            user_parts = []
            assistant_parts = []
            actions = []
            reasoning = []

            for step in steps_to_compress:
                if isinstance(step, TaskStep):
                    user_parts.append(step.task or "")

                elif isinstance(step, ActionStep):
                    if step.tool_calls:
                        for tc in step.tool_calls:
                            actions.append(
                                AgentAction(
                                    tool=tc.name,
                                    args=tc.arguments or {},
                                    output=str(step.action_output or "")[:200],
                                )
                            )
                    elif step.action_output:
                        output = str(step.action_output)
                        if len(output) > 300:
                            output = output[:300] + "..."
                        assistant_parts.append(output)
                    if step.error:
                        assistant_parts.append(f"[Error: {step.error}]")

                elif isinstance(step, PlanningStep):
                    reasoning.append(step.plan or "")

                elif isinstance(step, FinalAnswerStep):
                    answer = str(getattr(step, "final_answer", "") or "")
                    if answer:
                        assistant_parts.append(answer)

            # Only flush if there's meaningful content
            user_text = "\n".join(p for p in user_parts if p).strip()
            assistant_text = "\n".join(p for p in assistant_parts if p).strip()

            if not user_text and not assistant_text:
                logger.debug("Pre-compaction flush: no meaningful content to extract")
                return

            # Build synthetic conversation turn
            turn = ConversationTurn(
                user_message=Message(
                    role="user",
                    content=user_text or "(context from previous steps)",
                ),
                assistant_message=Message(
                    role="assistant",
                    content=assistant_text or "(actions taken in previous steps)",
                ),
                agent_actions=actions[:10],
                agent_reasoning=reasoning[:5],
            )

            # Feed to memory system
            result = await memory_mgr.process_conversation_turn_for_memories(
                conversation_turn=turn,
                chat_id=self.chat_id,
                user_id=self.user_id,
            )

            extracted_count = len(result.extracted_facts) if result else 0
            created_count = len(result.memories_created) if result else 0
            logger.info(
                f"Pre-compaction flush: extracted {extracted_count} facts, "
                f"created {created_count} memories from {len(steps_to_compress)} steps"
            )

        except Exception as e:
            # Pre-compaction flush should never block compression
            logger.warning(f"Pre-compaction memory flush failed: {e}")

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
