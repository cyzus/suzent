from smolagents.tools import Tool


class SkillTool(Tool):
    name = "skill_tool"
    description = "Load a skill to gain specialized knowledge for a task."

    inputs = {
        "skill_name": {
            "type": "string",
            "description": "The name of the skill to load. Check 'Available skills' in the tool description.",
        }
    }
    output_type = "string"

    def __init__(self):
        super().__init__()
        from suzent.skills import get_skill_manager

        self.skill_manager = get_skill_manager()
        # Update description with available skills dynamically at instantiation
        self.description = f"""Load a skill to gain specialized knowledge for a task.

Available skills:
{self.skill_manager.get_skills_xml()}

When to use:
- IMMEDIATELY when user task matches a skill description
- Before attempting domain-specific work
"""

    def forward(self, skill_name: str) -> str:
        content = self.skill_manager.get_skill_content(skill_name)
        if content:
            return content
        return f"Error: Skill '{skill_name}' not found. Available skills: {self.skill_manager.get_skill_descriptions()}"
