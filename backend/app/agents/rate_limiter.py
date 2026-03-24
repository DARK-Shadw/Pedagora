"""Per-model rate limiter — process-global singleton.

Gates LLM calls with per-model concurrency caps and cooldown timers
so that multiple concurrent topic extractions don't exceed API limits.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a single model in the pool."""

    name: str  # e.g. "qwen-coder"
    model_string: str  # e.g. "pollinations:qwen-coder"
    max_concurrent: int = 2  # max in-flight calls to this model
    requests_per_minute: float = 10.0  # RPM limit
    priority: int = 0  # lower = preferred


@dataclass
class _ModelState:
    """Runtime state for a single model."""

    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))
    last_call: float = 0.0  # monotonic timestamp
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ModelRateLimiter:
    """Per-model rate limiter using asyncio primitives."""

    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {}
        self._states: dict[str, _ModelState] = {}

    def register(self, config: ModelConfig) -> None:
        """Register a model with its rate-limit configuration."""
        self._models[config.name] = config
        self._states[config.name] = _ModelState(
            semaphore=asyncio.Semaphore(config.max_concurrent),
        )

    @asynccontextmanager
    async def throttle(self, model_name: str):
        """Acquire rate-limit slot for a model, enforce cooldown, then release."""
        config = self._models.get(model_name)
        state = self._states.get(model_name)
        if not config or not state:
            # Unknown model — pass through without throttling
            yield
            return

        # Acquire concurrency semaphore
        await state.semaphore.acquire()
        try:
            # Enforce minimum interval between calls
            min_interval = 60.0 / config.requests_per_minute
            async with state.lock:
                now = time.monotonic()
                elapsed = now - state.last_call
                if elapsed < min_interval:
                    wait = min_interval - elapsed
                    logger.debug(
                        f"Rate limiter: waiting {wait:.1f}s for {model_name}"
                    )
                    await asyncio.sleep(wait)
                state.last_call = time.monotonic()

            yield
        finally:
            state.semaphore.release()


# ── Process-global singleton ──────────────────────────────────────────

_global_limiter: ModelRateLimiter | None = None
_init_lock = asyncio.Lock()


async def get_rate_limiter() -> ModelRateLimiter:
    """Get or create the process-global rate limiter."""
    global _global_limiter
    if _global_limiter is not None:
        return _global_limiter
    async with _init_lock:
        if _global_limiter is None:
            _global_limiter = ModelRateLimiter()
    return _global_limiter
