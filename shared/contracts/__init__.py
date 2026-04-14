from shared.contracts.artifact import (
    ArtifactRecord,
    ArtifactType,
    ArtifactStatus,
    RetentionClass,
    TableSchema,
    SchemaColumn,
    ArtifactStatistics,
    ArtifactLineage,
    CreateArtifactRequest,
)
from shared.contracts.connection import ConnectionRecord, ConnectionConfig
from shared.contracts.execution import (
    ExecutionRequest,
    ExecutionResult,
    ToolInvocation,
    ExecutionTarget,
    ExecutionArtifactInput,
    ExpectedOutput,
)
