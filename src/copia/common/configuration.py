from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class CopiaSettings(BaseSettings):
    """Typed runtime configuration loaded from the process environment."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    data_root: Path = Field(default=Path("~/.copia"), validation_alias="COPIA_DATA_ROOT")
    profiles_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_PROFILES_PATH"
    )
    sessions_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_SESSIONS_PATH"
    )
    invariants_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_INVARIANTS_PATH"
    )
    memory_path_override: Path | None = Field(default=None, validation_alias="COPIA_MEMORY_PATH")
    user_profiles_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_USER_PROFILES_PATH"
    )
    expenses_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_EXPENSES_PATH"
    )
    mcp_connections_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_MCP_CONNECTIONS_PATH"
    )
    mcp_artifacts_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_MCP_ARTIFACTS_PATH"
    )
    scheduled_runs_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_SCHEDULED_RUNS_PATH"
    )
    schedules_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_SCHEDULES_PATH"
    )
    scheduler_state_path_override: Path | None = Field(
        default=None, validation_alias="COPIA_SCHEDULER_STATE_PATH"
    )
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    gigachat_auth_key: SecretStr | None = Field(default=None, validation_alias="GIGACHAT_AUTH_KEY")
    gigachat_scope: str = Field(default="GIGACHAT_API_PERS", validation_alias="GIGACHAT_SCOPE")
    allow_local_mcp_value: str = Field(default="true", validation_alias="COPIA_ALLOW_LOCAL_MCP")
    trusted_mcp_endpoint: str | None = Field(
        default=None, validation_alias="COPIA_MCP_TRUSTED_ENDPOINT"
    )
    otel_enabled_value: str = Field(default="false", validation_alias="COPIA_OTEL_ENABLED")
    otel_capture_http_bodies_value: str = Field(
        default="false", validation_alias="COPIA_OTEL_CAPTURE_HTTP_BODIES"
    )
    otel_exporter_endpoint: str = Field(
        default="http://localhost:4317", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_service_name: str = Field(default="copia-backend", validation_alias="OTEL_SERVICE_NAME")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    @property
    def profiles_path(self) -> Path:
        return self.profiles_path_override or self.project_root / "profiles.json"

    @property
    def sessions_path(self) -> Path:
        return self.sessions_path_override or self.data_root / "sessions"

    @property
    def invariants_path(self) -> Path:
        return self.invariants_path_override or self.sessions_path.parent / "invariants.json"

    @property
    def memory_path(self) -> Path:
        return self.memory_path_override or self.data_root / "memory"

    @property
    def user_profiles_path(self) -> Path:
        return self.user_profiles_path_override or self.data_root / "user_profiles.json"

    @property
    def expenses_path(self) -> Path:
        return self.expenses_path_override or self.data_root / "files/finances.xlsx"

    @property
    def mcp_connections_path(self) -> Path:
        return self.mcp_connections_path_override or self.data_root / "mcp_connections.json"

    @property
    def mcp_artifacts_path(self) -> Path:
        return self.mcp_artifacts_path_override or self.data_root / "artifacts"

    @property
    def scheduled_runs_path(self) -> Path:
        return self.scheduled_runs_path_override or self.data_root / "scheduled-runs"

    @property
    def schedules_path(self) -> Path:
        return self.schedules_path_override or self.data_root / "schedules.json"

    @property
    def scheduler_state_path(self) -> Path:
        return self.scheduler_state_path_override or self.data_root / "scheduler-state.json"

    @property
    def allow_local_mcp(self) -> bool:
        return self.allow_local_mcp_value.lower() != "false"

    @property
    def capture_http_bodies(self) -> bool:
        return self.otel_capture_http_bodies_value.lower() == "true"

    @property
    def otel_enabled(self) -> bool:
        return self.otel_enabled_value.lower() == "true"


def get_settings() -> CopiaSettings:
    """Read current environment settings without caching test or runtime overrides."""
    load_dotenv()
    return CopiaSettings()
