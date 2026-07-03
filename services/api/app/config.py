from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[1]


def _resolve_repo_root() -> Path:
    """Repo root on host (UniPilot/); in Docker fall back to API root (/app)."""
    config_path = Path(__file__).resolve()
    for parent in config_path.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return _API_ROOT


_REPO_ROOT = _resolve_repo_root()


def _settings_env_files() -> tuple[str, ...]:
    paths: list[str] = []
    for candidate in (_REPO_ROOT / ".env", _API_ROOT / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            resolved = str(candidate.resolve())
            if resolved not in paths:
                paths.append(resolved)
    return tuple(paths) if paths else (".env",)

# Dev-only default for Docker first-run; rejected when ENVIRONMENT=production.
DEV_JWT_SECRET = "unipilot_dev_jwt_secret_change_in_production"
DEV_MONGO_PASSWORD = "unipilot_dev_password"

JWT_SECRET_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "replace_me_with_secure_jwt_secret",
        DEV_JWT_SECRET,
    }
)

MONGO_PASSWORD_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        DEV_MONGO_PASSWORD,
        "password",
        "changeme",
    }
)

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
)


class Settings(BaseSettings):
    service_name: str = "api"
    environment: str = "development"
    auto_seed_catalog: bool = False
    api_port: int = 8000
    mongo_uri: str | None = None
    mongo_root_password: str | None = None
    redis_url: str | None = None
    jwt_secret: str | None = None
    jwt_expires_in: str = "1h"
    bcrypt_salt_rounds: int = 12
    auth_rate_limit_window_ms: int = 60_000
    auth_rate_limit_max: int = 30
    ai_rate_limit_window_ms: int = 60_000
    ai_rate_limit_max: int = 10
    progress_rate_limit_window_ms: int = 60_000
    progress_rate_limit_max: int = 60
    transcript_import_rate_limit_window_ms: int = 60_000
    transcript_import_rate_limit_max: int = 10
    ai_service_url: str | None = None
    ai_advisor_timeout_seconds: int = 120
    mas_queue_name: str = "mas_agent_jobs"
    agent_sessions_collection: str = "agent_sessions"
    agent_conversations_collection: str = "agent_conversations"
    agent_messages_collection: str = "agent_messages"
    agent_runs_collection: str = "agent_runs"
    agent_steps_collection: str = "agent_steps"
    agent_tool_calls_collection: str = "agent_tool_calls"
    agent_action_proposals_collection: str = "agent_action_proposals"
    agent_max_retrieval_attempts: int = 3
    agent_max_tool_calls_per_run: int = 12
    agent_max_workflow_steps: int = 20
    agent_agentic_retrieval_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_AGENTIC_RETRIEVAL_ENABLED",
    )
    agent_llm_validation_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_LLM_VALIDATION_ENABLED",
    )
    agent_llm_explanation_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_EXPLANATION_ENABLED",
    )
    agent_llm_intent_fallback_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_INTENT_FALLBACK_ENABLED",
    )
    agent_llm_preference_extraction_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED",
    )
    agent_assumptions_collection: str = "agent_assumptions"
    transcript_parser_url: str | None = None
    transcript_parser_timeout_seconds: int = 60
    transcript_import_max_upload_bytes: int = 5 * 1024 * 1024
    cors_allowed_origins: str = ",".join(DEFAULT_CORS_ORIGINS)
    internal_service_token: str | None = None
    courses_collection: str = "courses"
    course_offerings_collection: str = "course_offerings"
    degree_programs_collection: str = "degree_programs"
    degree_requirements_collection: str = "degree_requirements"
    catalog_rules_collection: str = "catalog_rules"
    catalog_path_options_collection: str = "catalog_path_options"
    catalog_faculties_collection: str = "catalog_faculties"
    catalog_default_limit: int = 50
    catalog_max_limit: int = 200
    catalog_cache_enabled: bool = True
    catalog_cache_ttl_seconds: int = 300
    catalog_offerings_batch_max: int = 50
    completed_courses_collection: str = "completed_courses"
    semester_plans_collection: str = "semester_plans"
    academic_risks_collection: str = "academic_risks"
    web_app_url: str = "http://localhost:3000"
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    e2e_google_oauth_stub: bool = False
    microsoft_client_id: str | None = None
    microsoft_tenant_id: str = "common"
    microsoft_redirect_uri: str | None = None
    microsoft_scopes: str = "User.Read Mail.Read offline_access"
    microsoft_token_encryption_key: str | None = None
    refresh_token_session_ttl_seconds: int = 24 * 60 * 60
    refresh_token_remember_ttl_seconds: int = 30 * 24 * 60 * 60
    technion_raw_dir: str | None = None
    catalog_vault_wiki_path: str | None = None
    agent_wiki_retrieval_limit: int = 5
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    openai_chat_model: str | None = Field(default=None, validation_alias="OPENAI_CHAT_MODEL")
    embedding_api_key: str | None = Field(default=None, validation_alias="EMBEDDING_API_KEY")
    embedding_base_url: str | None = Field(default=None, validation_alias="EMBEDDING_BASE_URL")
    embedding_model: str | None = Field(default=None, validation_alias="EMBEDDING_MODEL")
    embedding_enabled: bool = Field(default=True, validation_alias="EMBEDDING_ENABLED")
    embedding_index_enabled: bool = Field(default=True, validation_alias="EMBEDDING_INDEX_ENABLED")
    embedding_index_cache_path: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_INDEX_CACHE_PATH",
    )
    embedding_index_batch_size: int = Field(default=64, validation_alias="EMBEDDING_INDEX_BATCH_SIZE")
    embedding_index_cache_backup_count: int = Field(
        default=3,
        validation_alias="EMBEDDING_INDEX_CACHE_BACKUP_COUNT",
    )

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def require_jwt_secret(self) -> str:
        secret = (self.jwt_secret or "").strip()
        if not secret:
            raise RuntimeError(
                "JWT_SECRET is required. Copy .env.example to .env and set a strong secret."
            )
        if self.environment == "production":
            if secret in JWT_SECRET_PLACEHOLDERS:
                raise RuntimeError(
                    "JWT_SECRET must not use the development placeholder in production."
                )
            if len(secret) < 32:
                raise RuntimeError(
                    "JWT_SECRET must be at least 32 characters in production."
                )
        return secret

    def resolved_bcrypt_salt_rounds(self) -> int:
        rounds = int(self.bcrypt_salt_rounds)
        if rounds < 10:
            return 12
        return rounds

    def resolved_cors_origins(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in str(self.cors_allowed_origins).split(",")
            if origin.strip()
        ]
        return origins or list(DEFAULT_CORS_ORIGINS)

    def resolved_web_app_url(self) -> str:
        return str(self.web_app_url).rstrip("/")

    def resolved_transcript_parser_url(self) -> str:
        configured = (self.transcript_parser_url or "").strip()
        if configured:
            return configured.rstrip("/")
        return "http://transcript-parser:8010"

    def resolved_ai_service_url(self) -> str:
        configured = (self.ai_service_url or "").strip()
        if configured:
            return configured.rstrip("/")
        return "http://ai:3001"

    def resolved_embedding_api_key(self) -> str:
        return (self.embedding_api_key or "").strip()

    def resolved_embedding_base_url(self) -> str:
        configured = (self.embedding_base_url or "").strip()
        if configured:
            return configured.rstrip("/")
        return "https://api.llmod.ai/v1"

    def resolved_embedding_model(self) -> str:
        configured = (self.embedding_model or "").strip()
        if configured:
            return configured
        return "MB5R2CF-azure/text-embedding-3-small"

    def embeddings_available(self) -> bool:
        return bool(self.embedding_enabled and self.resolved_embedding_api_key())

    def resolved_embedding_index_cache_path(self) -> str:
        configured = (self.embedding_index_cache_path or "").strip()
        local_default = str(_API_ROOT / "data" / "cache" / "wiki_embedding_index.json")
        if configured:
            if configured.startswith("/app/") and self.environment != "production":
                return local_default
            return configured
        if self.environment == "production":
            return "/app/data/cache/wiki_embedding_index.json"
        return local_default

    def wiki_vector_index_enabled(self) -> bool:
        return bool(self.embedding_index_enabled and self.embeddings_available())

    def resolved_embedding_index_cache_backup_count(self) -> int:
        return max(0, int(self.embedding_index_cache_backup_count or 3))

    def is_agentic_retrieval_enabled(self) -> bool:
        return bool(self.agent_agentic_retrieval_enabled)

    def is_agent_llm_validation_enabled(self) -> bool:
        return bool(self.agent_llm_validation_enabled)

    def is_agent_llm_explanation_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_explanation_enabled)

    def is_agent_llm_intent_fallback_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_intent_fallback_enabled)

    def is_agent_llm_preference_extraction_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_preference_extraction_enabled)

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()

    def resolved_google_oauth_redirect_uri(self) -> str:
        configured = (self.google_oauth_redirect_uri or "").strip()
        if configured:
            return configured
        return f"{self.resolved_web_app_url()}/api/auth/google/callback"

    def google_oauth_enabled(self) -> bool:
        client_id = (self.google_oauth_client_id or "").strip()
        client_secret = (self.google_oauth_client_secret or "").strip()
        return bool(client_id and client_secret)

    def e2e_google_oauth_stub_enabled(self) -> bool:
        if self.environment == "production":
            return False
        return bool(self.e2e_google_oauth_stub and self.google_oauth_enabled())

    def resolved_microsoft_redirect_uri(self) -> str:
        configured = (self.microsoft_redirect_uri or "").strip()
        if configured:
            return configured
        return f"{self.resolved_web_app_url()}/api/integrations/outlook/callback"

    def resolved_microsoft_scopes(self) -> list[str]:
        return [scope.strip() for scope in self.microsoft_scopes.split() if scope.strip()]

    def microsoft_oauth_enabled(self) -> bool:
        client_id = (self.microsoft_client_id or "").strip()
        encryption_key = (self.microsoft_token_encryption_key or "").strip()
        return bool(client_id and encryption_key)

    def require_microsoft_token_encryption_key(self) -> bytes:
        raw = (self.microsoft_token_encryption_key or "").strip()
        if not raw:
            raise RuntimeError(
                "MICROSOFT_TOKEN_ENCRYPTION_KEY is required for Outlook token storage."
            )
        return raw.encode("utf-8")

    @field_validator("mongo_root_password", mode="before")
    @classmethod
    def normalize_mongo_root_password(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    def validate_production_settings(self) -> None:
        self.require_jwt_secret()

        if self.environment != "production":
            return

        mongo_password = (self.mongo_root_password or "").strip()
        if not mongo_password or mongo_password in MONGO_PASSWORD_PLACEHOLDERS:
            raise RuntimeError(
                "MONGO_ROOT_PASSWORD must be a strong, unique value in production."
            )

        if self.auth_rate_limit_max > 10:
            raise RuntimeError(
                "AUTH_RATE_LIMIT_MAX must be <= 10 in production (recommended: 5)."
            )

        if self.ai_rate_limit_max > 10:
            raise RuntimeError(
                "AI_RATE_LIMIT_MAX must be <= 10 in production (recommended: 5)."
            )

        if self.transcript_import_rate_limit_max > 10:
            raise RuntimeError(
                "TRANSCRIPT_IMPORT_RATE_LIMIT_MAX must be <= 10 in production (recommended: 5)."
            )

        internal_token = self.resolved_internal_service_token()
        if not internal_token or len(internal_token) < 32:
            raise RuntimeError(
                "INTERNAL_SERVICE_TOKEN must be at least 32 characters in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
