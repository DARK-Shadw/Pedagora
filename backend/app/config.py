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

    # Extract model pool — round-robin across multiple free-tier models
    extract_model_pool: str = "qwen-coder,mistral,openai"  # comma-separated names
    extract_pool_max_concurrent: str = "2,2,2"  # per-model concurrency caps
    extract_pool_rpm: str = "10,10,10"  # per-model RPM limits
    extract_max_parallel_topics: int = 7  # max topics extracted concurrently

    # Course Planner models
    planner_structure_model: str = "pollinations:mistral"
    planner_detail_model: str = "pollinations:mistral"
    planner_model_pool: str = "mistral"
    planner_pool_max_concurrent: str = "2"
    planner_pool_rpm: str = "10"
    planner_max_parallel_lessons: int = 2

    # Animation Agent
    animation_model: str = "pollinations:kimi"
    animation_search_enabled: bool = True
    animation_max_retries: int = 3
    animation_render_quality: str = "h"
    manim_output_dir: str = "media/animations"
    animation_storage_bucket: str = "animations"

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

    def get_extract_pool_configs(self) -> list:
        """Parse pool config strings into a list of ModelConfig objects.

        Returns an empty list if extract_model_pool is empty/blank,
        which signals the pipeline to fall back to single-model sequential mode.
        """
        from app.agents.rate_limiter import ModelConfig

        pool_str = self.extract_model_pool.strip()
        if not pool_str:
            return []

        names = [n.strip() for n in pool_str.split(",") if n.strip()]
        concurrents = [int(c.strip()) for c in self.extract_pool_max_concurrent.split(",")]
        rpms = [float(r.strip()) for r in self.extract_pool_rpm.split(",")]

        # Name-to-model-string mapping for known free-tier models
        model_strings = {
            "qwen-coder": "pollinations:qwen-coder",
            "claude-fast": "pollinations:claude-fast",
            "kimi": "pollinations:kimi",
            "openai": "pollinations:openai",
            "deepseek": "pollinations:deepseek",
            "mistral": "pollinations:mistral",
        }

        configs = []
        for i, name in enumerate(names):
            model_string = model_strings.get(name, f"pollinations:{name}")
            configs.append(
                ModelConfig(
                    name=name,
                    model_string=model_string,
                    max_concurrent=concurrents[i] if i < len(concurrents) else 2,
                    requests_per_minute=rpms[i] if i < len(rpms) else 10.0,
                    priority=i,
                )
            )
        return configs

    def get_planner_pool_configs(self) -> list:
        """Parse planner pool config strings into ModelConfig objects."""
        from app.agents.rate_limiter import ModelConfig

        pool_str = self.planner_model_pool.strip()
        if not pool_str:
            return []

        names = [n.strip() for n in pool_str.split(",") if n.strip()]
        concurrents = [int(c.strip()) for c in self.planner_pool_max_concurrent.split(",")]
        rpms = [float(r.strip()) for r in self.planner_pool_rpm.split(",")]

        model_strings = {
            "qwen-coder": "pollinations:qwen-coder",
            "claude-fast": "pollinations:claude-fast",
            "kimi": "pollinations:kimi",
            "openai": "pollinations:openai",
            "deepseek": "pollinations:deepseek",
            "mistral": "pollinations:mistral",
        }

        configs = []
        for i, name in enumerate(names):
            model_string = model_strings.get(name, f"pollinations:{name}")
            configs.append(
                ModelConfig(
                    name=name,
                    model_string=model_string,
                    max_concurrent=concurrents[i] if i < len(concurrents) else 2,
                    requests_per_minute=rpms[i] if i < len(rpms) else 10.0,
                    priority=i,
                )
            )
        return configs


@lru_cache()
def get_settings() -> Settings:
    return Settings()
