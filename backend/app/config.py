from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # Google AI
    google_api_key: str

    # Gemini key pool for Animation Agent v2.
    # Comma-separated list of API keys. Falls back to google_api_keys, then google_api_key.
    gemini_api_keys: str = ""
    google_api_keys: str = ""

    # Paid Gemini key — automatic fallback when free keys hit 429/503.
    gemini_paid_api_key: str = ""
    gemini_paid_model: str = "gemini-2.5-flash"

    # NVIDIA NIM
    nvidia_api_key: str = ""
    nvidia_api_keys: str = ""

    # Groq
    groq_api_key: str = ""

    # Pollinations (OpenAI-compatible)
    pollinations_api_key: str = ""

    # OpenRouter (used by model factory for LLM calls)
    openrouter_api_key: str = ""

    # Animation Agent
    animation_model: str = "pollinations:kimi"
    animation_search_enabled: bool = True
    animation_max_retries: int = 3
    animation_render_quality: str = "l"
    animation_use_opengl: bool = False
    manim_output_dir: str = "media/animations"
    animation_storage_bucket: str = "animations"

    # Teacher Agent
    teacher_model: str = "groq:llama-3.3-70b-versatile"
    teacher_fast_model: str = "groq:meta-llama/llama-4-scout-17b-16e-instruct"

    # Frontend
    frontend_url: str = "http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_gemini_api_keys(self) -> list[str]:
        """Parse GEMINI_API_KEYS into a list. Falls back to GOOGLE_API_KEYS, then GOOGLE_API_KEY."""
        raw = (self.gemini_api_keys or "").strip()
        if not raw:
            raw = (self.google_api_keys or "").strip()
        if not raw:
            return [self.google_api_key] if self.google_api_key else []
        return [k.strip() for k in raw.split(",") if k.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
