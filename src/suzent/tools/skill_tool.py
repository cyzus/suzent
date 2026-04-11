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

    def forward(self, ctx: RunContext[AgentDeps], skill_name: str) -> str:
        """Load a skill to gain specialized knowledge for a task.

        Use this tool IMMEDIATELY when the user's task matches a skill description,
        before attempting domain-specific work. The available skills are listed in
        the system prompt under 'Available Skills'.

        Args:
            skill_name: The name of the skill to load.
        """
        sm = ctx.deps.skill_manager
        if not sm:
            from suzent.skills import get_skill_manager

            sm = get_skill_manager()

        content = sm.get_skill_content(
            skill_name, sandbox_enabled=ctx.deps.sandbox_enabled
        )
        if content:
            return content
        return f"Error: Skill '{skill_name}' not found. Available skills: {sm.get_skill_descriptions()}"
