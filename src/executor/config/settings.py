from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from executor.schemas.command import ExecutionEnvironment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EXECUTOR_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "executor-service"
    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379/0"
    redis_stream_name: str = "execution:commands"
    redis_group_name: str = "execution-workers"
    redis_execution_key_prefix: str = "execution"
    redis_block_ms: int = Field(default=5_000, gt=0)
    redis_batch_size: int = Field(default=1, gt=0)
    redis_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    redis_pending_idle_ms: int = Field(default=60_000, gt=0)
    redis_claim_interval_seconds: float = Field(default=30.0, gt=0)

    consumer_name_prefix: str = "executor"
    max_concurrency: int = Field(default=1, gt=0)
    shutdown_timeout_seconds: float = Field(default=30.0, gt=0)

    jupyter_base_url: str = "http://localhost:8888"
    jupyter_token: str | None = None
    jupyter_request_timeout_seconds: float = Field(default=30.0, gt=0)
    jupyter_websocket_open_timeout_seconds: float = Field(default=30.0, gt=0)
    jupyter_websocket_ping_interval_seconds: float = Field(default=20.0, gt=0)
    jupyter_websocket_ping_timeout_seconds: float = Field(default=20.0, gt=0)
    jupyter_websocket_protocol: str | None = None
    analysis_kernel_name: str = "analysis-env"
    modeling_kernel_name: str = "modeling-env"

    callback_timeout_seconds: float = Field(default=5.0, gt=0)
    callback_max_attempts: int = Field(default=3, gt=0)
    callback_backoff_seconds: float = Field(default=1.0, gt=0)

    def get_kernel_name(self, environment: ExecutionEnvironment) -> str:
        mapping = {
            ExecutionEnvironment.ANALYSIS: self.analysis_kernel_name,
            ExecutionEnvironment.MODELING: self.modeling_kernel_name,
        }
        try:
            return mapping[environment]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported execution environment: {environment}"
            ) from exc


@lru_cache
def get_settings() -> Settings:
    return Settings()

