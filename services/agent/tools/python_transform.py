from services.agent.llm.base import ToolDefinition

PYTHON_TRANSFORM_TOOL = ToolDefinition(
    name="transform_with_python",
    description=(
        "Transform, filter, or aggregate data using Python code. "
        "This tool operates on existing session artifacts (loaded as pandas DataFrames). "
        "Use this when the user wants to refine, combine, or analyze data that was previously retrieved. "
        "Your code must assign the final result to a variable called `result` (a pandas DataFrame)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "input_artifacts": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of artifact names from the current session to use as input. "
                    "Each artifact will be available as a pandas DataFrame variable with the same name."
                ),
            },
            "code": {
                "type": "string",
                "description": (
                    "Python code to execute. Input artifacts are available as pandas DataFrames "
                    "with variable names matching the artifact names. "
                    "The code must assign the final output to a variable called `result` (a DataFrame). "
                    "pandas is available as `pd`. Example:\n"
                    "result = customers_last_6_months[customers_last_6_months['status'] == 'inactive']"
                ),
            },
            "artifact_name": {
                "type": "string",
                "description": (
                    "A short, descriptive snake_case name for the resulting table artifact "
                    "(e.g. 'inactive_customers', 'revenue_summary')."
                ),
            },
        },
        "required": ["input_artifacts", "code", "artifact_name"],
    },
)
