from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Switching LOCAL <-> CLOUD is configuration only (docs/CLAUDE.md § Two deployment targets)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./huluhilir.db"
    litellm_model: str = "ollama_chat/qwen2.5:14b"
    ollama_api_base: str = "http://localhost:11434"
    api_base_url: str = "http://localhost:8000"
    tts_base_url: str = "http://localhost:8001"

    # CLOUD path only. LITELLM_MODEL="vertex_ai/gemini-2.0-flash" on Cloud Run
    # authenticates via the service's attached service account (Application
    # Default Credentials) -- no API key to manage or leak. gemini_api_key is
    # kept only as an escape hatch if Vertex AI auth misbehaves on deploy day;
    # nothing in application code branches on which of the two is set.
    #
    # Field names/env vars are VERTEXAI_* (not VERTEX_*) because that's what
    # litellm's Vertex AI integration reads directly via os.environ -- see
    # LiteLlm's own docstring in adk-python/src/google/adk/models/lite_llm.py.
    # Getting this wrong doesn't raise; it silently fails to authenticate.
    vertexai_project: str | None = None
    vertexai_location: str = "asia-southeast1"
    gemini_api_key: str | None = None

    # Photos and voice labels. Local disk locally; on Cloud Run this must point
    # at a writable path (/tmp) or Firebase Storage -- see docs/BUILD_LOG.md.
    media_root: str = "./media"

    cnn_model_path: str = "../classifier/best-model/huluhilir_l1.onnx"
    cnn_labels_path: str = "../classifier/best-model/labels.txt"
    cnn_preprocess_path: str = "../classifier/best-model/preprocess.json"
    cnn_model_version: str = "huluhilir_l1_v1"
    confidence_threshold: float = 0.60


settings = Settings()
