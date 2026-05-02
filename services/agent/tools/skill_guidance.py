from services.agent.llm.base import ToolDefinition

GET_SKILL_GUIDANCE_TOOL = ToolDefinition(
    name="get_skill_guidance",
    description=(
        "Fetch full instructions for an active skill. Use this when a matched skill looks "
        "relevant and you need its detailed recommended steps, do/don't guidance, or output expectations."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": (
                    "The active skill name, title, or id exactly as shown in the active skills list."
                ),
            },
        },
        "required": ["skill_name"],
    },
)
