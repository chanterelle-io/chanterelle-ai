from services.agent.llm.base import ToolDefinition

INSPECT_ARTIFACT_TOOL = ToolDefinition(
    name="inspect_artifact",
    description=(
        "Inspect an existing session artifact to see its column details and sample rows. "
        "Use this when you need to understand the actual data values in an artifact "
        "before answering a follow-up question, or when the user asks to see the data."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "artifact_name": {
                "type": "string",
                "description": "The name of an existing artifact in the current session.",
            },
            "max_rows": {
                "type": "integer",
                "description": "Number of sample rows to return (default 5, max 20).",
                "default": 5,
            },
        },
        "required": ["artifact_name"],
    },
)
