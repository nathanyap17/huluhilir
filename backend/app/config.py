from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Switching LOCAL <-> CLOUD is configuration only (docs/CLAUDE.md § Two deployment targets)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./huluhilir.db"
    litellm_model: str = "ollama_chat/qwen2.5:14b"
    # Upper bound for one agent LLM turn; past it the runner uses the
    # deterministic rules-table fallback (env AGENT_TIMEOUT_S).
    agent_timeout_s: float = 180
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

    # Google Cloud TTS (Block E). Auth is ADC -- the Cloud Run service account
    # on CLOUD, `gcloud auth application-default login` locally. No key here.
    tts_language_default: str = "ms"

    # Which L1 backend serves diagnoses: "onnx" (the trained MobileNetV3) or
    # "gemini" (vision model via LiteLLM). Configuration only -- both return
    # the identical six-class result shape, and neither can reach the rules
    # table. Whichever is deployed, quote the accuracy measured for THAT
    # backend; the CNN's 0.934 macro F1 is a fact about the CNN alone.
    classifier_backend: str = "onnx"
    # Vision model for the gemini classifier backend. Kept separate from
    # litellm_model (the agent's chat model) so changing one cannot silently
    # re-point the other. Verified resolvable in this project by a direct GET
    # against publishers/google/models/<id> -- do that before changing it.
    # gemini-3.7-flash is NOT usable here: the publisher-model metadata
    # endpoint returns 200 for it, but an actual prediction 404s with "not
    # found or your project does not have access to it". A 200 from that GET
    # means the model NAME is known, not that this project can call it --
    # verify with a real inference call before changing this.
    vision_model: str = "vertex_ai/gemini-2.5-flash"

    cnn_model_path: str = "../classifier/best-model/huluhilir_l1.onnx"
    cnn_labels_path: str = "../classifier/best-model/labels.txt"
    cnn_preprocess_path: str = "../classifier/best-model/preprocess.json"
    cnn_model_version: str = "huluhilir_l1_v1"
    confidence_threshold: float = 0.60
    # Minimum gap between the top two classes before a prediction is treated
    # as decided. Guards the "0.40 vs 0.36" case that an absolute threshold
    # alone waves through. See app/tools/diagnose.py.
    confidence_margin: float = 0.15


settings = Settings()
