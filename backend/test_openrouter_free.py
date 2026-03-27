"""
Temporary test: run the research pipeline with openrouter/free for all stages.
No codebase changes — just env var overrides before import.
"""
import os

# Override BEFORE any imports that read settings
os.environ["DECOMPOSE_MODEL"] = "openrouter:openrouter/free"
os.environ["EXTRACT_MODEL"] = "openrouter:openrouter/free"
os.environ["SYNTHESIZE_MODEL"] = "openrouter:openrouter/free"
os.environ["EXTRACT_MODEL_POOL"] = ""  # disable pool, use sequential single-model

# Now run the regular test
exec(open("test_pipeline.py").read())
