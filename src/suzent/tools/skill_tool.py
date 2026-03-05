from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool


class SkillTool(Tool):
    name = "SkillTool"
    tool_name = "skill_execute"

    def __init__(self):
        super().__init__()
        from suzent.skills import get_skill_manager

        self.skill_manager = get_skill_manager()
        # Update description dynamically at instantiation (used for reference only;
        # the forward() docstring is what pydantic-ai exposes to the LLM).
        self.description = f"""Load a skill to gain specialized knowledge for a task.

Available skills:
{self.skill_manager.get_skills_xml()}

When to use:
- IMMEDIATELY when user task matches a skill description
- Before attempting domain-specific work
"""

    def forward(self, ctx: RunContext[AgentDeps], skill_name: str) -> str:
        """Load a skill to gain specialized knowledge for a task.

        Use this tool IMMEDIATELY when the user's task matches a skill description,
        before attempting domain-specific work.

        Args:
            ctx: The pydantic-ai run context with agent dependencies.
            skill_name: The name of the skill to load. Check 'Available skills' in the system prompt.
        """
        sm = ctx.deps.skill_manager
        if not sm:
            from suzent.skills import get_skill_manager

            sm = get_skill_manager()

        content = sm.get_skill_content(skill_name)
        if content:
            return content
        return f"Error: Skill '{skill_name}' not found. Available skills: {sm.get_skill_descriptions()}"
