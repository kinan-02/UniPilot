from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MICROSOFT_SCOPES = "User.Read Mail.Read offline_access"
MAX_RESULTS_CAP = 25
DEFAULT_MAX_RESULTS = 10
ATTACHMENT_MAX_BYTES = 256 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = frozenset({".txt", ".md", ".csv"})


class Settings(BaseSettings):
    service_name: str = "outlook-mcp"
    environment: str = "development"
    mongo_uri: str | None = None
    microsoft_client_id: str | None = None
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str | None = None
    microsoft_scopes: str = DEFAULT_MICROSOFT_SCOPES
    microsoft_token_encryption_key: str | None = None
    internal_service_token: str | None = None
    graph_request_timeout_seconds: float = 15.0
    graph_rate_limit_max_per_minute: int = 60
    outlook_mcp_log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolved_microsoft_scopes(self) -> list[str]:
        return [scope.strip() for scope in self.microsoft_scopes.split() if scope.strip()]

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()

    def require_token_encryption_key(self) -> bytes:
        raw = (self.microsoft_token_encryption_key or "").strip()
        if not raw:
            raise RuntimeError(
                "MICROSOFT_TOKEN_ENCRYPTION_KEY is required for Outlook token storage."
            )
        return raw.encode("utf-8")

    def microsoft_oauth_enabled(self) -> bool:
        client_id = (self.microsoft_client_id or "").strip()
        encryption_key = (self.microsoft_token_encryption_key or "").strip()
        return bool(client_id and encryption_key)

    @field_validator("microsoft_tenant_id", mode="before")
    @classmethod
    def normalize_tenant_id(cls, value: str | None) -> str:
        stripped = str(value or "common").strip()
        return stripped or "common"


@lru_cache
def get_settings() -> Settings:
    return Settings()
