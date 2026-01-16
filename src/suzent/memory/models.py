"""
Pydantic models for memory system data structures.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Message(BaseModel):
    """Represents a chat message."""
    role: str = Field(..., description="Role of the message sender (user, assistant)")
    content: str = Field(..., description="The message content")


class AgentAction(BaseModel):
    """Represents an agent tool call action."""
    tool: str = Field(..., description="Name of the tool that was called")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed to the tool")
    output: Optional[Any] = Field(None, description="Output returned by the tool")


class AgentStepsSummary(BaseModel):
    """Summary of agent execution steps."""
    actions: List[AgentAction] = Field(default_factory=list, description="List of tool calls made")
    planning: List[str] = Field(default_factory=list, description="Planning/reasoning steps")
    final_answer: str = Field("", description="Final answer provided to the user")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")

    @classmethod
    def from_succinct_steps(cls, steps: List[Any]) -> "AgentStepsSummary":
        """
        Create a summary from a list of agent steps (dict or smolagents objects).
        
        Args:
            steps: List of steps from agent_instance.memory.get_succinct_steps()
        """
        # Local import to avoid runtime dependency issues if smolagents isn't top-level imported
        try:
            from smolagents.memory import ActionStep, PlanningStep, FinalAnswerStep
        except ImportError:
            # Fallback mocks if smolagents not available (shouldn't happen in this app)
            ActionStep = type('ActionStep', (), {})
            PlanningStep = type('PlanningStep', (), {})
            FinalAnswerStep = type('FinalAnswerStep', (), {})
        
        summary = cls()
        
        for step in steps:
            # Handle dictionary format (serialized steps)
            if isinstance(step, dict):
                step_type = step.get('step_type') or step.get('type', 'unknown')
                
                if step_type == 'final_answer' or 'final_answer' in step:
                    answer = step.get('final_answer') or step.get('output') or step.get('content', '')
                    summary.final_answer = str(answer)
                
                elif step_type == 'action' or 'tool_calls' in step:
                    tool_calls = step.get('tool_calls', [])
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            summary.actions.append(AgentAction(
                                tool=tc.get('name', 'unknown'),
                                args=tc.get('arguments', {}),
                                output=step.get('action_output') or step.get('output')
                            ))
                    if step.get('error'):
                        summary.errors.append(str(step['error']))
                
                elif step_type == 'planning' or 'plan' in step:
                    plan = step.get('plan', '')
                    if plan:
                        summary.planning.append(plan)
            
            # Handle smolagents object format
            elif isinstance(step, ActionStep):
                for tool_call in step.tool_calls:
                    summary.actions.append(AgentAction(
                        tool=tool_call.name,
                        args=tool_call.arguments,
                        output=getattr(step, 'action_output', None)
                    ))
                if getattr(step, 'error', None):
                    summary.errors.append(str(step.error))
            
            elif isinstance(step, PlanningStep):
                summary.planning.append(step.plan)
            
            elif isinstance(step, FinalAnswerStep):
                summary.final_answer = str(step.output)
                
        return summary


class ConversationTurn(BaseModel):
    """Represents a complete conversation turn with context."""
    user_message: Message = Field(..., description="The user's message")
    assistant_message: Message = Field(..., description="The assistant's response")
    agent_actions: List[AgentAction] = Field(default_factory=list, description="Actions taken by the agent")
    agent_reasoning: List[str] = Field(default_factory=list, description="Reasoning steps")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        """Create a ConversationTurn from a dictionary."""
        user_msg_data = data.get("user_message", {})
        assistant_msg_data = data.get("assistant_message", {})
        actions_data = data.get("agent_actions", [])
        reasoning = data.get("agent_reasoning", [])

        user_message = Message(
            role=user_msg_data.get("role", "user"),
            content=user_msg_data.get("content", "")
        )
        assistant_message = Message(
            role=assistant_msg_data.get("role", "assistant"),
            content=assistant_msg_data.get("content", "")
        )
        agent_actions = [
            AgentAction(
                tool=a.get("tool", "unknown"),
                args=a.get("args", {}),
                output=a.get("output")
            )
            for a in actions_data
        ]

        return cls(
            user_message=user_message,
            assistant_message=assistant_message,
            agent_actions=agent_actions,
            agent_reasoning=reasoning
        )

    def format_for_extraction(self) -> str:
        """Format the conversation turn for memory extraction."""
        # Format actions
        if self.agent_actions:
            actions_parts = []
            for action in self.agent_actions:
                output_str = str(action.output or "")[:200]
                actions_parts.append(f"- Tool: {action.tool}({action.args})\n  Result: {output_str}...")
            actions_str = "\n".join(actions_parts)
        else:
            actions_str = "No tools used."

        # Format reasoning
        if self.agent_reasoning:
            valid_reasoning = [r for r in self.agent_reasoning if r.strip()]
            if valid_reasoning:
                reasoning_str = "\n".join([f"- {r}" for r in valid_reasoning])
            else:
                reasoning_str = "No explicit reasoning steps."
        else:
            reasoning_str = "No explicit reasoning steps."

        return f"""
Conversation Turn to Analyze:

USER MESSAGE:
{self.user_message.content}

AGENT REASONING:
{reasoning_str}

AGENT ACTIONS:
{actions_str}

ASSISTANT RESPONSE:
{self.assistant_message.content}
"""


class ConversationContext(BaseModel):
    """Context metadata for a memory entry."""
    user_intent: str = Field("inferred from conversation", description="What the user was trying to accomplish")
    agent_actions_summary: Optional[str] = Field(None, description="Summary of agent actions")
    outcome: str = Field("extracted from conversation turn", description="Result of the interaction")


class ExtractedFact(BaseModel):
    """A fact extracted from conversation for memory storage."""
    content: str = Field(..., description="The fact content as a standalone statement")
    category: Optional[str] = Field(None, description="Category: personal, preference, goal, context, technical, other")
    importance: float = Field(0.5, ge=0.0, le=1.0, description="Importance score from 0.0 to 1.0")
    tags: List[str] = Field(default_factory=list, description="Relevant tags for the fact")
    conversation_context: Optional[ConversationContext] = Field(None, description="Context from the conversation")


class MemoryExtractionResult(BaseModel):
    """Result of processing a conversation turn for memories."""
    extracted_facts: List[str] = Field(default_factory=list, description="List of extracted fact contents")
    memories_created: List[str] = Field(default_factory=list, description="IDs of newly created memories")
    memories_updated: List[str] = Field(default_factory=list, description="IDs of updated/similar existing memories")
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list, description="Any detected conflicts")

    @classmethod
    def empty(cls) -> "MemoryExtractionResult":
        """Create an empty result."""
        return cls()


class FactExtractionResponse(BaseModel):
    """LLM response model for fact extraction.
    
    This model is used with LiteLLM's structured output feature to ensure
    the LLM returns properly formatted fact extraction results.
    """
    facts: List[ExtractedFact] = Field(
        default_factory=list, 
        description="List of extracted facts from the conversation"
    )
