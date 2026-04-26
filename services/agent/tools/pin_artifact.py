from services.agent.llm.base import ToolDefinition

PIN_ARTIFACT_TOOL = ToolDefinition(
    name="pin_artifact",
    description=(
        "Pin an existing session artifact so it is protected from automatic cleanup. "
        "Use this when the user wants to keep a result around for later or explicitly save it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "artifact_name": {
                "type": "string",
                "description": "The name of an existing artifact in the current session to pin.",
            },
        },
        "required": ["artifact_name"],
    },
)