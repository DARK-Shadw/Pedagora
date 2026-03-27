"""
Temporary test: run the research pipeline with Groq models in parallel.
No codebase changes — monkey-patches pool config only.
"""
import os

# Override models BEFORE any imports
os.environ["DECOMPOSE_MODEL"] = "groq:meta-llama/llama-4-scout-17b-16e-instruct"
os.environ["EXTRACT_MODEL"] = "groq:meta-llama/llama-4-scout-17b-16e-instruct"
os.environ["SYNTHESIZE_MODEL"] = "groq:meta-llama/llama-4-scout-17b-16e-instruct"

# Pool: 2 reliable Groq models for parallel extraction
os.environ["EXTRACT_MODEL_POOL"] = "scout-17b,qwen-32b"
os.environ["EXTRACT_POOL_MAX_CONCURRENT"] = "3,3"
os.environ["EXTRACT_POOL_RPM"] = "30,30"
os.environ["EXTRACT_MAX_PARALLEL_TOPICS"] = "5"

# Monkey-patch pool config to map names to Groq model strings
import app.config as config_mod
_original_get_pool = config_mod.Settings.get_extract_pool_configs

def _patched_get_pool(self):
    from app.agents.rate_limiter import ModelConfig
    pool_str = self.extract_model_pool.strip()
    if not pool_str:
        return []

    groq_model_strings = {
        "scout-17b": "groq:meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen-32b": "groq:qwen/qwen3-32b",
    }

    names = [n.strip() for n in pool_str.split(",") if n.strip()]
    concurrents = [int(c.strip()) for c in self.extract_pool_max_concurrent.split(",")]
    rpms = [float(r.strip()) for r in self.extract_pool_rpm.split(",")]

    configs = []
    for i, name in enumerate(names):
        model_string = groq_model_strings.get(name, f"groq:{name}")
        configs.append(
            ModelConfig(
                name=name,
                model_string=model_string,
                max_concurrent=concurrents[i] if i < len(concurrents) else 3,
                requests_per_minute=rpms[i] if i < len(rpms) else 30.0,
                priority=i,
            )
        )
    return configs

config_mod.Settings.get_extract_pool_configs = _patched_get_pool

# Clear cached settings
config_mod.get_settings.cache_clear()

# Run the pipeline test
exec(open("test_pipeline.py").read())
