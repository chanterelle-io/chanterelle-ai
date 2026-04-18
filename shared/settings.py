from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://chanterelle:chanterelle@localhost:5432/chanterelle"

    # Object storage (MinIO / S3)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "artifacts"

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"

    # Inter-service URLs
    execution_service_url: str = "http://localhost:8001"
    artifact_service_url: str = "http://localhost:8002"
    sql_runtime_url: str = "http://localhost:8010"
    python_runtime_url: str = "http://localhost:8011"

    model_config = {"env_prefix": "CHANTERELLE_", "env_file": ".env"}


settings = Settings()
