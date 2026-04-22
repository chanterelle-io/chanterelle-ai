from services.agent.llm.base import ToolDefinition

CHECK_JOB_STATUS_TOOL = ToolDefinition(
    name="check_job_status",
    description=(
        "Check the status of a deferred (background) job. Use this when the user asks "
        "about a pending analysis, or when a previous request was deferred and you need "
        "to check if it has completed. Returns the job status and results if available."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "The ID of the job to check. This was returned when the job was submitted.",
            },
        },
        "required": ["job_id"],
    },
)
