"""Round-robin model selection with automatic fallback on 429s.

The pool rotates across multiple free-tier models so that rate limits
on any single model don't block the pipeline.  It delegates per-call
pacing to the ModelRateLimiter and per-call retries to run_with_retry.
"""

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

from app.agents.rate_limiter import ModelConfig, get_rate_limiter

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ModelPool:
    """Round-robin model pool with 429-aware fallback."""

    def __init__(self, models: list[ModelConfig]) -> None:
        if not models:
            raise ValueError("ModelPool requires at least one model")
        self._models = sorted(models, key=lambda m: m.priority)
        self._index = 0
        self._lock = asyncio.Lock()
        self._failed: set[str] = set()

    @property
    def model_count(self) -> int:
        return len(self._models)

    async def next_model(self) -> ModelConfig:
        """Pick the next model via round-robin, skipping failed ones."""
        async with self._lock:
            # Try each model once before giving up
            for _ in range(len(self._models)):
                model = self._models[self._index % len(self._models)]
                self._index += 1
                if model.name not in self._failed:
                    return model

            # All models failed — reset and try again from the first
            logger.warning("All models in pool marked as failed — resetting")
            self._failed.clear()
            model = self._models[0]
            self._index = 1
            return model

    async def run_with_pool(
        self,
        fn: Callable[[str], Awaitable[T]],
    ) -> T:
        """Execute fn(model_string) with automatic model rotation on 429.

        - fn receives a model_string (e.g. "pollinations:qwen-coder")
        - On 429, the pool rotates to the next model and retries
        - On other errors, raises immediately (let caller/run_with_retry handle it)
        - At most 2 full rotations before giving up
        """
        max_attempts = len(self._models) * 2
        last_error: Exception | None = None
        rate_limiter = await get_rate_limiter()

        for attempt in range(max_attempts):
            model = await self.next_model()
            try:
                async with rate_limiter.throttle(model.name):
                    return await fn(model.model_string)
            except Exception as e:
                error_str = str(e)
                if "429" in error_str:
                    logger.warning(
                        f"Model {model.name} returned 429 "
                        f"(attempt {attempt + 1}/{max_attempts}), rotating..."
                    )
                    last_error = e
                    # Don't permanently mark as failed — just rotate
                    continue
                # Non-429 error: raise immediately
                raise

        raise RuntimeError(
            f"All models exhausted after {max_attempts} attempts. "
            f"Last error: {last_error}"
        )
