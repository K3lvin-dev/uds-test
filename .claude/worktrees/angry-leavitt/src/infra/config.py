from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str = Field(default=...)
    aws_endpoint_url: str = Field(default=...)
    aws_default_region: str = "us-east-1"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    s3_bucket: str = Field(default=...)
    sqs_queue_url: str = Field(default=...)
    gemini_api_key: str = Field(default=...)


settings = Settings()
