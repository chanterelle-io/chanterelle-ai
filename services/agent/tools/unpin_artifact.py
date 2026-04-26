from services.agent.llm.base import ToolDefinition

UNPIN_ARTIFACT_TOOL = ToolDefinition(
    name="unpin_artifact",
    description=(
        "Remove cleanup protection from an existing session artifact. "
        "Use this when the user says a saved artifact no longer needs to be kept."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "artifact_name": {
                "type": "string",
                "description": "The name of an existing artifact in the current session to unpin.",
            },
        },
        "required": ["artifact_name"],
    },
)