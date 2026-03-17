"""Model factory for creating PydanticAI models from config strings.

Supports:
  - "google-gla:model-name" → native Google provider (handled by PydanticAI)
  - "groq:model-name" → native Groq provider (handled by PydanticAI)
  - "pollinations:model-name" → OpenAI-compatible via Pollinations API
  - "openrouter:model-name" → OpenAI-compatible via OpenRouter API
"""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import get_settings

POLLINATIONS_BASE_URL = "https://gen.pollinations.ai/v1"


def create_model(model_string: str) -> OpenAIChatModel | str:
    """Create a PydanticAI model from a config string.

    For google-gla: and groq: prefixes, returns the string as-is
    (PydanticAI handles these natively).
    For pollinations: prefix, creates an OpenAIChatModel with custom base_url.
    """
    if model_string.startswith("pollinations:"):
        model_name = model_string.removeprefix("pollinations:")
        settings = get_settings()
        provider = OpenAIProvider(
            base_url=POLLINATIONS_BASE_URL,
            api_key=settings.pollinations_api_key,
        )
        return OpenAIChatModel(model_name, provider=provider)

    if model_string.startswith("openrouter:"):
        model_name = model_string.removeprefix("openrouter:")
        settings = get_settings()
        provider = OpenAIProvider(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        return OpenAIChatModel(model_name, provider=provider)

    # google-gla: and groq: are handled natively by PydanticAI
    return model_string
