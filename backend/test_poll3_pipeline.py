"""
Test: run research pipeline with 3-model Pollinations pool.
qwen-coder + mistral + openai — all cheap, all support structured output.
"""
import os

# Use qwen-coder for decompose/synthesize (cheapest, proven)
os.environ["DECOMPOSE_MODEL"] = "pollinations:qwen-coder"
os.environ["SYNTHESIZE_MODEL"] = "pollinations:qwen-coder"
os.environ["EXTRACT_MODEL"] = "pollinations:qwen-coder"

# 3-model pool for parallel extraction
os.environ["EXTRACT_MODEL_POOL"] = "qwen-coder,mistral,openai"
os.environ["EXTRACT_POOL_MAX_CONCURRENT"] = "2,2,2"
os.environ["EXTRACT_POOL_RPM"] = "10,10,10"
os.environ["EXTRACT_MAX_PARALLEL_TOPICS"] = "5"

# Clear cached settings
import app.config as config_mod
config_mod.get_settings.cache_clear()

# Run the pipeline test
exec(open("test_pipeline.py").read())
