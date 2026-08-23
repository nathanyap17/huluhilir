from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Switching LOCAL <-> CLOUD is configuration only (docs/CLAUDE.md § Two deployment targets)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./huluhilir.db"
    litellm_model: str = "ollama_chat/qwen2.5:14b"
    ollama_api_base: str = "http://localhost:11434"
    api_base_url: str = "http://localhost:8000"
    tts_base_url: str = "http://localhost:8001"
    gemini_api_key: str | None = None
    cnn_model_path: str = "../classifier/best-model/huluhilir_l1.onnx"
    cnn_labels_path: str = "../classifier/best-model/labels.txt"
    cnn_preprocess_path: str = "../classifier/best-model/preprocess.json"
    cnn_model_version: str = "huluhilir_l1_v1"
    confidence_threshold: float = 0.60


settings = Settings()
