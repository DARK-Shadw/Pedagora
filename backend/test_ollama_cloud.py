"""
Temporary test: run the research pipeline with Ollama Cloud models in parallel.
No codebase changes — monkey-patches model factory + pool config.
"""
import os

_ollama_key = "02a657a748dd4b2e8253d4d441ed5fe4.bsseCGzKujpfJKq2mznGc31G"

# Override models — decompose/synthesize use single fast model
os.environ["DECOMPOSE_MODEL"] = "ollama-cloud:qwen3-coder:480b"
os.environ["EXTRACT_MODEL"] = "ollama-cloud:qwen3-coder:480b"
os.environ["SYNTHESIZE_MODEL"] = "ollama-cloud:qwen3-coder:480b"

# Pool config: 5 models, parallel extraction
os.environ["EXTRACT_MODEL_POOL"] = "oc-qwen3coder,oc-qwen35,oc-deepseek,oc-devstral,oc-glm"
os.environ["EXTRACT_POOL_MAX_CONCURRENT"] = "2,2,2,2,2"
os.environ["EXTRACT_POOL_RPM"] = "15,15,15,15,15"
os.environ["EXTRACT_MAX_PARALLEL_TOPICS"] = "5"

# Monkey-patch model factory to support ollama-cloud: prefix
import app.agents.models as models_mod
_original_create = models_mod.create_model

def _patched_create(model_string):
    if model_string.startswith("ollama-cloud:"):
        model_name = model_string.removeprefix("ollama-cloud:")
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        provider = OpenAIProvider(
            base_url="https://ollama.com/v1",
            api_key=_ollama_key,
        )
        return OpenAIChatModel(model_name, provider=provider)
    return _original_create(model_string)

models_mod.create_model = _patched_create

# Monkey-patch pool config to map our pool names to ollama-cloud: model strings
import app.config as config_mod
_original_get_pool = config_mod.Settings.get_extract_pool_configs

def _patched_get_pool(self):
    from app.agents.rate_limiter import ModelConfig
    pool_str = self.extract_model_pool.strip()
    if not pool_str:
        return []

    # Map pool names to Ollama Cloud model strings
    oc_model_strings = {
        "oc-qwen3coder": "ollama-cloud:qwen3-coder:480b",
        "oc-qwen35": "ollama-cloud:qwen3.5:397b",
        "oc-deepseek": "ollama-cloud:deepseek-v3.1:671b",
        "oc-devstral": "ollama-cloud:devstral-small-2:24b",
        "oc-glm": "ollama-cloud:glm-4.7",
    }

    names = [n.strip() for n in pool_str.split(",") if n.strip()]
    concurrents = [int(c.strip()) for c in self.extract_pool_max_concurrent.split(",")]
    rpms = [float(r.strip()) for r in self.extract_pool_rpm.split(",")]

    configs = []
    for i, name in enumerate(names):
        model_string = oc_model_strings.get(name, f"ollama-cloud:{name}")
        configs.append(
            ModelConfig(
                name=name,
                model_string=model_string,
                max_concurrent=concurrents[i] if i < len(concurrents) else 2,
                requests_per_minute=rpms[i] if i < len(rpms) else 15.0,
                priority=i,
            )
        )
    return configs

config_mod.Settings.get_extract_pool_configs = _patched_get_pool

# Clear cached settings so new env vars take effect
config_mod.get_settings.cache_clear()

# Now run the regular test
exec(open("test_pipeline.py").read())
