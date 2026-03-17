from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # Google AI
    google_api_key: str

    # Groq
    groq_api_key: str = ""

    # Pollinations (OpenAI-compatible)
    pollinations_api_key: str = ""

    # Search APIs
    tavily_api_key: str = ""
    serper_api_key: str = ""
    github_token: str = ""
    exa_api_key: str = ""  # Optional, for future use

    # OpenRouter (VLM for figure description)
    openrouter_api_key: str = ""

    # Jina (embeddings)
    jina_api_key: str = ""
    embedding_dimension: int = 768

    # Per-stage LLM models
    decompose_model: str = "google-gla:gemini-2.5-flash"
    extract_model: str = "pollinations:qwen-coder"
    synthesize_model: str = "google-gla:gemini-2.5-flash"

    # RAG pipeline models
    vlm_model: str = "openrouter:nvidia/nemotron-nano-12b-2-vl"
    utility_model: str = "groq:llama-3.3-70b-versatile"
    embedding_provider: str = "jina"

    # Legacy fallback (used if per-stage model fails or for backwards compat)
    gemini_model: str = "google-gla:gemini-2.0-flash"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def effective_extract_model(self) -> str:
        """Returns the extract model, falling back to gemini if provider not configured."""
        if self.extract_model.startswith("groq:") and not self.groq_api_key:
            return self.gemini_model
        if self.extract_model.startswith("pollinations:") and not self.pollinations_api_key:
            return self.gemini_model
        return self.extract_model


@lru_cache()
def get_settings() -> Settings:
    return Settings()
