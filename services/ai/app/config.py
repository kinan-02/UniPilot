"""AI service configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_ROOT = Path(__file__).resolve().parents[1]


def _resolve_repo_root() -> Path:
    """Repo root on host (UniPilot/); in Docker fall back to the app root (/app).

    Ported from `services/api/app/config.py`'s identical fix -- pydantic-
    settings' `env_file` is resolved relative to cwd, which silently misses
    the real root `.env` (and falls back to wrong defaults) whenever this
    service is run from a cwd other than its own package root, e.g. `pytest`
    invoked from `services/ai/`.
    """
    config_path = Path(__file__).resolve()
    for parent in config_path.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return _APP_ROOT


_REPO_ROOT = _resolve_repo_root()


def _settings_env_files() -> tuple[str, ...]:
    paths: list[str] = []
    for candidate in (_REPO_ROOT / ".env", _APP_ROOT / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            resolved = str(candidate.resolve())
            if resolved not in paths:
                paths.append(resolved)
    return tuple(paths) if paths else (".env",)


class Settings(BaseSettings):
    service_name: str = "ai"
    environment: str = "development"
    ai_service_port: int = 3001
    internal_service_token: str | None = None

    academic_wiki_path: str = "/app/data/academic/wiki"
    academic_technion_raw_dir: str = "/app/data/raw/technion"
    academic_default_semester_file: str = "courses_2025_201.json"
    academic_catalog_json: str = "/app/data/raw/technion/courses_2025_201.json"

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_chat_model: str = "gpt-5-mini"
    advisor_max_retrieval_iterations: int = 5

    # -- Retrieval port (services/agent/app/retrieval) additions below --

    mongo_uri: str | None = None
    completed_courses_collection: str = "completed_courses"
    semester_plans_collection: str = "semester_plans"

    api_service_url: str | None = None
    internal_api_timeout_seconds: int = 60

    agent_wiki_retrieval_limit: int = 5

    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    embedding_enabled: bool = True
    embedding_index_enabled: bool = True
    embedding_index_cache_path: str | None = None
    embedding_index_batch_size: int = 64
    embedding_index_cache_backup_count: int = 3

    # -- agent_core reasoning port (services/agent/app/agent/reasoning) additions below --

    agent_reasoning_structured_output_enabled: bool = False
    agent_reasoning_adaptive_iterations_enabled: bool = False
    agent_reasoning_adaptive_confidence_threshold: float = 0.75
    agent_llm_thinking_enabled: bool = True
    agent_llm_reasoning_effort: str | None = None
    # Which provider's wire format `llm_client._cached_chat_llm` should
    # translate abstract reasoning-control params (thinking_enabled/
    # reasoning_effort) into -- the ONE setting that needs to change, along
    # with openai_api_key/openai_base_url/openai_chat_model above, when the
    # foundation model is swapped. Defaults to "deepseek" to match the
    # provider actually configured today; no other file needs editing for a
    # provider swap unless the new provider's mechanism is genuinely novel.
    agent_llm_provider: Literal["deepseek", "openai"] = "deepseek"

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()

    def resolved_technion_raw_dir(self) -> str:
        raw = (self.academic_technion_raw_dir or "").strip()
        if raw:
            return raw
        catalog = Path(self.academic_catalog_json)
        if catalog.is_file():
            return str(catalog.parent)
        return raw

    def resolved_default_semester_file(self) -> str | None:
        explicit = (self.academic_default_semester_file or "").strip()
        if explicit:
            return explicit
        catalog = Path(self.academic_catalog_json)
        if catalog.is_file():
            return catalog.name
        return None

    def is_graph_configured(self) -> bool:
        wiki = (self.academic_wiki_path or "").strip()
        raw = self.resolved_technion_raw_dir()
        return bool(wiki and raw)

    def resolved_api_service_url(self) -> str:
        configured = (self.api_service_url or "").strip()
        if configured:
            return configured.rstrip("/")
        return "http://api:8000"

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
        local_default = str(_APP_ROOT / "data" / "cache" / "wiki_embedding_index.json")
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

    def is_agent_reasoning_structured_output_enabled(self) -> bool:
        return bool(self.agent_reasoning_structured_output_enabled)

    def is_agent_reasoning_adaptive_iterations_enabled(self) -> bool:
        return bool(self.agent_reasoning_adaptive_iterations_enabled)

    def resolved_agent_reasoning_adaptive_confidence_threshold(self) -> float:
        value = float(self.agent_reasoning_adaptive_confidence_threshold)
        return max(0.0, min(1.0, value))

    def is_agent_llm_thinking_enabled(self) -> bool:
        return bool(self.agent_llm_thinking_enabled)

    def resolved_agent_llm_reasoning_effort(self) -> str | None:
        value = (self.agent_llm_reasoning_effort or "").strip()
        return value or None

    def resolved_agent_llm_provider(self) -> str:
        return self.agent_llm_provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
