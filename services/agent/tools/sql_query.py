from services.agent.llm.base import ToolDefinition

SQL_QUERY_TOOL = ToolDefinition(
    name="query_sql_source",
    description=(
        "Execute a SQL query against a connected data source. "
        "The query results will be saved as a reusable table artifact in the session. "
        "Use this tool when the user asks for data from a connected database."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "connection_name": {
                "type": "string",
                "description": "The name of the connection to query.",
            },
            "query": {
                "type": "string",
                "description": "The SQL query to execute against the data source.",
            },
            "artifact_name": {
                "type": "string",
                "description": (
                    "A short, descriptive snake_case name for the resulting table artifact "
                    "(e.g. 'customers_last_month', 'revenue_by_product')."
                ),
            },
            "estimated_row_count": {
                "type": "integer",
                "description": (
                    "Optional estimate of how many rows this query will return. "
                    "The execution service may still route large queries to background processing."
                ),
            },
        },
        "required": ["connection_name", "query", "artifact_name"],
    },
)
