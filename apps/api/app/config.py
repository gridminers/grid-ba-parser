from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=default_data_dir, alias="API_DATA_DIR")
    enable_vlm: bool = Field(default=True, alias="API_ENABLE_VLM")
    low_confidence_threshold: float = Field(default=0.62, alias="API_LOW_CONFIDENCE_THRESHOLD")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_vision_model: str = Field(default="gpt-5.5", alias="OPENAI_VISION_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    vlm_provider: str = Field(default="openai", alias="VLM_PROVIDER")
    local_vllm_base_url: str = Field(
        default="http://127.0.0.1:8001/v1", alias="LOCAL_VLLM_BASE_URL"
    )
    local_vllm_api_key: str = Field(default="local-token", alias="LOCAL_VLLM_API_KEY")
    local_vllm_model: str = Field(
        default="Qwen/Qwen2.5-VL-3B-Instruct", alias="LOCAL_VLLM_MODEL"
    )
    local_vllm_temperature: float = Field(default=0.0, alias="LOCAL_VLLM_TEMPERATURE")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5vl", alias="OLLAMA_MODEL")
    ollama_temperature: float = Field(default=0.0, alias="OLLAMA_TEMPERATURE")

    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket: str = Field(default="documents", alias="SUPABASE_STORAGE_BUCKET")

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def vlm_available(self) -> bool:
        if self.vlm_provider == "local_vllm":
            return bool(self.local_vllm_base_url and self.local_vllm_model)
        if self.vlm_provider == "ollama":
            return bool(self.ollama_base_url and self.ollama_model)
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
